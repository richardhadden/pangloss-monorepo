"""The real `Store`: items and library records written through the models.

The sync writes as its own user (`ZOTERO_SYNC_USER`), so that `created_by` and the history say who made a
change, and so that a *person's* edit can be told from the sync's: the entity's `meta.version` is compared with
`zotero_synced_entity_version`, which the sync sets to the version its own write makes.

Only the fields the sync owns are written. An item is read for editing and written back with the new fields on
it, against the version read (a person's edit in between is retried over, not lost), so the item's own
relations and fields that a person added stay.
"""

import contextlib
import logging
import secrets
from collections.abc import Generator
from typing import Any, get_origin

from pangloss_models.exceptions import (
    PanglossNotDeletedError,
    PanglossNotFoundError,
    PanglossVersionConflictError,
)
from pangloss_models.model_registry import ModelRegistry
from pangloss_users import current_request_username, service
from pangloss_users.exceptions import PanglossUserExistsError
from pydantic import AnyHttpUrl

from pangloss_zotero import convert
from pangloss_zotero.mapping import concrete_classes
from pangloss_zotero.models import ZoteroBacked, ZoteroLibrary
from pangloss_zotero.sync import Existing, LibraryState

logger = logging.getLogger("pangloss.zotero.store")

ATTEMPTS = 3


class ZoteroModelError(Exception):
    """A model of the project that the sync cannot write"""


def with_required_lists(model: type, data: dict[str, Any]) -> dict[str, Any]:
    """`data` for a `Create` of the model, with `[]` for each relation to many (they are required, though they
    may be empty). Raises `ZoteroModelError` if another field is required that the sync cannot give"""
    filled = dict(data)
    missing = []
    supplied = {*data, "id", "create_new", "type"}
    for name, field in model.Create.model_fields.items():  # type: ignore[attr-defined]
        if name in supplied or not field.is_required():
            continue
        if get_origin(field.annotation) is list:
            filled[name] = []
        else:
            missing.append(name)
    if missing:
        raise ZoteroModelError(
            f"{model.__name__} cannot be made from a Zotero item: {', '.join(missing)} is required. "
            "Make it optional (`X | None = None`), or a list"
        )
    return filled


async def ensure_sync_user(username: str) -> None:
    """The user the sync writes as. It must exist (a write by one that does not is refused); it is made
    with a password nobody is told, so nobody logs in as it"""
    if await service.get_user(username) is not None:
        return
    with contextlib.suppress(PanglossUserExistsError):
        await service.create_user(
            username,
            f"{username}@example.com",
            secrets.token_urlsafe(48),
            full_name="Zotero sync",
        )
    logger.info("Made the user %s, which the Zotero sync writes as", username)


@contextlib.contextmanager
def acting_as(username: str) -> Generator[None]:
    token = current_request_username.set(username)
    try:
        yield
    finally:
        current_request_username.reset(token)


def edit_data(edit: Any, fields: dict[str, Any], version: int) -> dict[str, Any]:
    """What to save to change `fields` on an item that was read for editing"""
    data = edit.model_dump(exclude={"meta"})
    data.update(fields)
    data["zotero_synced_entity_version"] = version + 1
    return data


class ModelStore:
    def __init__(self) -> None:
        self._classes: list[type[ZoteroBacked]] | None = None

    @property
    def classes(self) -> list[type[ZoteroBacked]]:
        if self._classes is None:
            # (a class before its parents: `TextObject.get` finds a node that is an `Atlas`, and then cannot
            # read it as a `TextObject`, so the most specific class is asked first)
            self._classes = sorted(concrete_classes(), key=lambda c: -len(c.__mro__))
        return self._classes

    def model(self, name: str) -> type[ZoteroBacked]:
        model = ModelRegistry.all_models().get(name)
        if model is None or not issubclass(model, ZoteroBacked):
            raise LookupError(f"{name} is not a Zotero model")
        return model

    # --- items ------------------------------------------------------------------------------------

    async def _read(self, url: AnyHttpUrl) -> tuple[type[ZoteroBacked], Any] | None:
        for model in self.classes:
            found = await model.get(url)  # type: ignore[misc]
            if found is not None:
                return type(found)._owner, found  # type: ignore[attr-defined]
        return None

    async def find(self, url: str) -> Existing | None:
        address = AnyHttpUrl(url)
        restored = False
        found = await self._read(address)
        if found is None:
            # (deleted, perhaps: a deleted item is not found, and is restored when it is in Zotero again)
            for model in self.classes:
                try:
                    await model.undelete(address)  # type: ignore[misc]
                except PanglossNotFoundError, PanglossNotDeletedError:
                    continue
                restored = True
                break
            if not restored:
                return None
            found = await self._read(address)
            if found is None:
                return None
        model, view = found
        incoming = model._meta.field_definitions.incoming_fields
        return Existing(
            id=view.id,
            model=model.__name__,
            version=view.meta.version,
            zotero_version=view.zotero_version,
            synced_entity_version=view.zotero_synced_entity_version,
            removed_from_zotero=bool(view.removed_from_zotero),
            referenced=any(getattr(view, name, None) for name in incoming),
            restored=restored,
        )

    async def create(self, model: str, fields: dict[str, Any]) -> None:
        cls = self.model(model)
        data = with_required_lists(cls, {**fields, "zotero_synced_entity_version": 1})
        await cls.Create(  # type: ignore[call-arg]
            id=AnyHttpUrl(fields["zotero_url"]), create_new=True, **data
        ).save()

    async def update(self, existing: Existing, fields: dict[str, Any]) -> None:
        cls = self.model(existing.model)
        for attempt in range(1, ATTEMPTS + 1):
            edit = await cls.get_for_edit(existing.id)  # type: ignore[misc]
            if edit is None:
                raise PanglossNotFoundError(f"{existing.model} {existing.id} has gone")
            data = edit_data(edit, fields, edit.meta.version)
            try:
                await cls.Update(**data).save(expected_version=edit.meta.version)  # type: ignore[call-arg]
                return
            except PanglossVersionConflictError:
                if attempt == ATTEMPTS:
                    raise
                logger.info("%s was edited meanwhile; trying again", existing.id)

    async def delete(self, existing: Existing) -> None:
        await self.model(existing.model).delete(existing.id)  # type: ignore[misc]

    # --- libraries --------------------------------------------------------------------------------

    async def library_state(self, library: str) -> LibraryState:
        found = await ZoteroLibrary.get(AnyHttpUrl(convert.library_url(library)))  # type: ignore[misc]
        if found is None:
            return LibraryState()
        return LibraryState(
            found.synced_version or 0, found.last_sync, found.last_error
        )

    async def save_library_state(self, library: str, state: LibraryState) -> None:
        fields = {
            "label": library,
            "library": library,
            "synced_version": state.synced_version,
            "last_sync": state.last_sync,
            "last_error": state.last_error,
        }
        url = AnyHttpUrl(convert.library_url(library))
        for attempt in range(1, ATTEMPTS + 1):
            edit = await ZoteroLibrary.get_for_edit(url)  # type: ignore[misc]
            if edit is None:
                await ZoteroLibrary.Create(id=url, create_new=True, **fields).save()  # type: ignore[call-arg]
                return
            data = edit.model_dump(exclude={"meta"})
            data.update(fields)
            try:
                await ZoteroLibrary.Update(**data).save(
                    expected_version=edit.meta.version
                )  # type: ignore[call-arg]
                return
            except PanglossVersionConflictError:
                if attempt == ATTEMPTS:
                    raise


class DryRunStore(ModelStore):
    """Reads like the real store and writes nothing (`--dry-run`): what would be done is counted by the sync"""

    async def find(self, url: str) -> Existing | None:
        found = await self._read(AnyHttpUrl(url))
        if found is None:
            return None
        model, view = found
        incoming = model._meta.field_definitions.incoming_fields
        return Existing(
            id=view.id,
            model=model.__name__,
            version=view.meta.version,
            zotero_version=view.zotero_version,
            synced_entity_version=view.zotero_synced_entity_version,
            removed_from_zotero=bool(view.removed_from_zotero),
            referenced=any(getattr(view, name, None) for name in incoming),
        )

    async def create(self, model: str, fields: dict[str, Any]) -> None:
        return None

    async def update(self, existing: Existing, fields: dict[str, Any]) -> None:
        return None

    async def delete(self, existing: Existing) -> None:
        return None

    async def save_library_state(self, library: str, state: LibraryState) -> None:
        return None
