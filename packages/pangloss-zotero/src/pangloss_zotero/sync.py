"""One sync of a library: what Zotero has changed since the version held, written to the database.

The version stored for a library says "everything up to here is written", so that a sync can stop at any point
and the next goes on from there (writing an item twice changes nothing). To keep that true while storing it more
often than once at the very end:

- what Zotero deleted for good is dealt with first, and then the items in the order of their versions, so that
  after each batch the version just below the next item's can be stored (not more often than
  `CHECKPOINT_SECONDS`): a first sync of 15,000 items that is stopped at 5,000 goes on from 5,000, and
  `pangloss zotero status` says how far it is;
- an item that cannot be written holds the stored version just below its own, and the rest are still written.
  A process that syncs again and again (the watcher) remembers how far it read and which items failed
  (`Progress`), so its next sync asks Zotero only for what is new and for those items; a new process starts from
  the stored version and so tries them again too;
- a database that is being migrated refuses every write: the sync stops there (`SyncPostponed`), to go on later,
  instead of failing item after item.

The database is reached through a `Store`, so the sync can be tried without one.
"""

import datetime
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any, Protocol
from uuid import UUID

from pangloss_models import PanglossReadOnlyError

from pangloss_zotero import config, convert
from pangloss_zotero.client import ZoteroClient, ZoteroError
from pangloss_zotero.mapping import TypeTable

logger = logging.getLogger("pangloss.zotero.sync")

# How often, at most, the version reached is stored during a long sync (seconds). Each time is a write of the
# library's entity (and a version of it in the history), so not after every batch of 50
CHECKPOINT_SECONDS = 30.0


class SyncPostponed(ZoteroError):
    """The database cannot be written to now (it is being migrated): the sync stopped, and goes on from the version
    it had reached when it is run again"""


@dataclass
class Progress:
    """What a process that syncs a library again and again keeps between its syncs: how far it has read (which
    is further than the version stored, while an item cannot be written), and the items to try again, each with
    the version it had"""

    read_to: int = 0
    failed: dict[str, int] = field(default_factory=dict)
    # (items deleted for good in Zotero whose removal here failed, each with the version to hold the stored one at)
    undeleted: dict[str, int] = field(default_factory=dict)


@dataclass
class LibraryState:
    synced_version: int = 0
    last_sync: datetime.datetime | None = None
    last_error: str | None = None


@dataclass
class Existing:
    """An item that is in the database already"""

    id: UUID
    model: str
    version: int  # `meta.version` of the entity
    zotero_version: int | None
    synced_entity_version: int | None  # the `meta.version` that the sync made last
    removed_from_zotero: bool
    referenced: bool  # something refers to it
    restored: bool = False  # it had been deleted, and is not now

    @property
    def edited_by_person(self) -> bool:
        return (
            self.synced_entity_version is not None
            and self.version != self.synced_entity_version
        )


class Store(Protocol):
    async def library_state(self, library: str) -> LibraryState: ...

    async def save_library_state(self, library: str, state: LibraryState) -> None: ...

    async def find(self, url: str) -> Existing | None:
        """The item with this URL (restoring it, if it had been deleted)"""
        ...

    async def create(self, model: str, fields: dict[str, Any]) -> None: ...

    async def update(self, existing: Existing, fields: dict[str, Any]) -> None:
        """Set these fields on the item, and leave the rest"""
        ...

    async def delete(self, existing: Existing) -> None: ...


@dataclass
class Report:
    library: str
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    restored: int = 0
    removed: int = 0  # in the trash, or deleted for good but kept
    deleted: int = 0
    skipped: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    version: int = 0

    def summary(self) -> str:
        parts = [
            f"{self.created} created",
            f"{self.updated} updated",
            f"{self.unchanged} unchanged",
        ]
        for name in ("restored", "removed", "deleted"):
            if value := getattr(self, name):
                parts.append(f"{value} {name}")
        if self.skipped:
            parts.append(
                "skipped "
                + ", ".join(f"{n} {t}" for t, n in sorted(self.skipped.items()))
            )
        if self.errors:
            parts.append(f"{len(self.errors)} errors")
        return f"{self.library}: " + ", ".join(parts)


def chunks(keys: list[str], size: int):
    for start in range(0, len(keys), size):
        yield keys[start : start + size]


async def apply_item(
    store: Store,
    table: TypeTable,
    library: str,
    item: dict[str, Any],
    report: Report,
    now: datetime.datetime,
) -> None:
    fields = convert.stamp(convert.convert(item, library), now)
    existing = await store.find(fields["zotero_url"])
    if existing is None:
        model = table.class_for(fields["item_type"] or "").__name__
        await store.create(model, fields)
        report.created += 1
        if fields["removed_from_zotero"]:
            report.removed += 1
        return
    if existing.restored:
        report.restored += 1
    unchanged = (
        not existing.restored
        and existing.zotero_version == fields["zotero_version"]
        and existing.removed_from_zotero == bool(fields["removed_from_zotero"])
    )
    if unchanged:
        report.unchanged += 1
        return
    await store.update(existing, fields)
    report.updated += 1
    if fields["removed_from_zotero"] and not existing.removed_from_zotero:
        report.removed += 1


async def apply_deletion(
    store: Store, library: str, key: str, report: Report, now: datetime.datetime
) -> None:
    """An item deleted for good in Zotero: deleted here if nothing refers to it and no person has edited
    it, and otherwise kept, flagged"""
    existing = await store.find(convert.item_url(library, key))
    if existing is None:
        return
    if existing.referenced or existing.edited_by_person:
        if not existing.removed_from_zotero or existing.restored:
            await store.update(
                existing, {"removed_from_zotero": True, "synced_when": now}
            )
            report.removed += 1
        return
    await store.delete(existing)
    report.deleted += 1


def stored_version(held: int, read_to: int, *failed: dict[str, int]) -> int:
    """The version to store: everything up to it is written. It is as far as was read, but below every item that
    could not be written (or removed); and never less than what was held"""
    below = [version - 1 for group in failed for version in group.values()]
    return max(held, min([read_to, *below]))


async def sync_library(
    client: ZoteroClient,
    store: Store,
    table: TypeTable,
    library: str,
    *,
    full: bool = False,
    skip_types: set[str] | None = None,
    progress: Progress | None = None,
    checkpoint_seconds: float = CHECKPOINT_SECONDS,
    clock: Callable[[], datetime.datetime] = lambda: datetime.datetime.now(
        datetime.UTC
    ),
) -> Report:
    """Bring a library up to date. Raises nothing for a single item that cannot be written: it is in
    `report.errors`, the version stored stays below it, and it is tried again by the next sync (with `progress`,
    without the rest being asked for again). A failure to reach Zotero is raised as `ZoteroError`, after it is
    recorded in the library's state; a database that takes no writes now, as `SyncPostponed`."""
    skipped_types = set(config.DEFAULT_SKIP_TYPES if skip_types is None else skip_types)
    state = await store.library_state(library)
    progress = progress if progress is not None else Progress()
    if full:
        progress.read_to, progress.failed, progress.undeleted = 0, {}, {}
    since = 0 if full else max(state.synced_version, progress.read_to)
    report = Report(library, version=since)
    now = clock()
    failed, undeleted = dict(progress.failed), dict(progress.undeleted)
    saved = time.monotonic()

    async def checkpoint(read_to: int, done: int, of: int) -> None:
        nonlocal saved
        version = stored_version(state.synced_version, read_to, failed, undeleted)
        if version == state.synced_version:
            return
        state.synced_version = version
        await store.save_library_state(library, replace(state))
        saved = time.monotonic()
        logger.info(
            "%s: %s of %s items read, up to version %s", library, done, of, version
        )

    try:
        versions, latest = await client.item_versions(library, since)
        # (first: the version stored during the items below must not pass a deletion that was not dealt with)
        deleted = await client.deleted_items(library, since) if since else []
        for key in sorted({*undeleted, *deleted}):
            try:
                await apply_deletion(store, library, key, report, now)
                undeleted.pop(key, None)
                failed.pop(key, None)
            except PanglossReadOnlyError:
                raise
            except Exception as error:
                logger.exception("Could not remove %s", key)
                report.errors.append(f"{key}: {type(error).__name__}: {error}")
                # (it holds the version where it was, so that a new process is told of the deletion again)
                undeleted.setdefault(key, since + 1)

        # (the items to try again first, then what has changed, the oldest change first)
        retried = sorted(key for key in failed if key not in versions)
        ordered = sorted(versions, key=lambda key: (versions[key], key))
        todo = retried + ordered
        done = 0
        for batch in chunks(todo, config.BATCH_SIZE):
            found = await client.items(library, batch)
            for key in set(batch) - {item.get("key") for item in found}:
                # (no longer in Zotero: nothing to try again)
                failed.pop(key, None)
            for item in found:
                key = str(item.get("key"))
                item_type = item.get("data", {}).get("itemType", "")
                if item_type in skipped_types:
                    report.skipped[item_type] = report.skipped.get(item_type, 0) + 1
                    failed.pop(key, None)
                    continue
                try:
                    await apply_item(store, table, library, item, report, now)
                    failed.pop(key, None)
                except PanglossReadOnlyError:
                    raise
                except Exception as error:
                    logger.exception("Could not write %s", key)
                    report.errors.append(f"{key}: {type(error).__name__}: {error}")
                    failed[key] = versions.get(key, failed.get(key, since + 1))
            done += len(batch)
            # (every item of a version below the next one's is done; `retried` have no place in this order)
            next_version = next(
                (versions[key] for key in todo[done:] if key in versions), None
            )
            if (
                next_version is not None
                and time.monotonic() - saved >= checkpoint_seconds
            ):
                await checkpoint(next_version - 1, done, len(todo))

        progress.read_to, progress.failed, progress.undeleted = (
            latest,
            failed,
            undeleted,
        )
        state.synced_version = stored_version(
            state.synced_version, latest, failed, undeleted
        )
        report.version = state.synced_version
        waiting = sorted({*failed, *undeleted})
        if waiting:
            names = ", ".join(waiting[:5]) + (", ..." if len(waiting) > 5 else "")
            first = f"; first: {report.errors[0]}" if report.errors else ""
            state.last_error = (
                f"{len(waiting)} items could not be written ({names}): the version stored stays below them, "
                f"and they are tried again{first}"
            )
        else:
            state.last_error = None
        state.last_sync = now
        await store.save_library_state(library, replace(state))
    except PanglossReadOnlyError as error:
        # (what was done stays done: the versions stored so far, and what this run could not write)
        progress.failed, progress.undeleted = failed, undeleted
        raise SyncPostponed(
            f"{library}: the database takes no writes now ({error}); the sync goes on from version "
            f"{state.synced_version} when it is run again"
        ) from error
    except ZoteroError as error:
        state.last_error = str(error)
        await store.save_library_state(library, replace(state))
        raise
    return report
