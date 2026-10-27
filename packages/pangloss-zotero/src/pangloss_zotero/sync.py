"""One sync of a library: what Zotero has changed since the version held, written to the database.

The order matters for being safe to stop at any point: the library's version is stored **last**, after every
write succeeded, so a sync that fails half-way is done again from the old version (writing an item twice
changes nothing). The database is reached through a `Store`, so the sync can be tried without one.
"""

import datetime
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID

from pangloss_zotero import config, convert
from pangloss_zotero.client import ZoteroClient, ZoteroError
from pangloss_zotero.mapping import TypeTable

logger = logging.getLogger("pangloss.zotero.sync")


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


async def sync_library(
    client: ZoteroClient,
    store: Store,
    table: TypeTable,
    library: str,
    *,
    full: bool = False,
    skip_types: set[str] | None = None,
    clock: Callable[[], datetime.datetime] = lambda: datetime.datetime.now(
        datetime.UTC
    ),
) -> Report:
    """Bring a library up to date. Raises nothing for a single item that cannot be written (it is in
    `report.errors`, and the version is then not stored, so it is tried again); a failure to reach Zotero
    is raised as `ZoteroError`, after it is recorded in the library's state."""
    skipped_types = set(config.DEFAULT_SKIP_TYPES if skip_types is None else skip_types)
    state = await store.library_state(library)
    since = 0 if full else state.synced_version
    report = Report(library, version=since)
    now = clock()
    try:
        versions, latest = await client.item_versions(library, since)
        for batch in chunks(sorted(versions), config.BATCH_SIZE):
            for item in await client.items(library, batch):
                item_type = item.get("data", {}).get("itemType", "")
                if item_type in skipped_types:
                    report.skipped[item_type] = report.skipped.get(item_type, 0) + 1
                    continue
                try:
                    await apply_item(store, table, library, item, report, now)
                except Exception as error:
                    logger.exception("Could not write %s", item.get("key"))
                    report.errors.append(
                        f"{item.get('key')}: {type(error).__name__}: {error}"
                    )
        if since:
            for key in await client.deleted_items(library, since):
                try:
                    await apply_deletion(store, library, key, report, now)
                except Exception as error:
                    logger.exception("Could not remove %s", key)
                    report.errors.append(f"{key}: {type(error).__name__}: {error}")
    except ZoteroError as error:
        state.last_error = str(error)
        await store.save_library_state(library, state)
        raise

    if report.errors:
        state.last_error = f"{len(report.errors)} items could not be written; first: {report.errors[0]}"
    else:
        state.synced_version = latest
        state.last_error = None
        report.version = latest
    state.last_sync = now
    await store.save_library_state(library, state)
    return report
