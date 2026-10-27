"""Linking a text object made by hand to a Zotero item.

The Zotero fields cannot be set through the API (they are read-only), so this is the one way a node made by hand
becomes an item: the item is fetched, the class is asked whether it can be of that type, and the node is
written with the item's fields and its Zotero URL. If the item was already synced, there is a node for it
already, and this refuses (there is no way yet to join two nodes: use that one).

Zotero may have the type wrong (a book entered as a document): the person says what it is on the node
(`item_type_override`) before linking, and that is what the class is asked about."""

import re
from uuid import UUID

from pangloss_models.model_registry import ModelRegistry
from pydantic import AnyHttpUrl

from pangloss_zotero import config, convert
from pangloss_zotero.client import ZoteroClient
from pangloss_zotero.mapping import accepts
from pangloss_zotero.models import ZoteroBacked
from pangloss_zotero.store import ModelStore

ITEM_URL = re.compile(
    r"^https://www\.zotero\.org/((?:groups|users)/\d+)/items/([A-Za-z0-9]+)/?$"
)


class LinkError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


async def link_item(
    settings, client: ZoteroClient, model_name: str, id: UUID, zotero_url: str
) -> None:
    cls = ModelRegistry.all_models().get(model_name)
    if cls is None or not issubclass(cls, ZoteroBacked) or cls._meta.abstract:
        raise LinkError(
            422, f"{model_name} is not a model that can be linked to Zotero"
        )
    match = ITEM_URL.match(zotero_url.strip())
    if match is None:
        raise LinkError(
            422,
            "A Zotero item's address looks like https://www.zotero.org/groups/123/items/ABCD1234",
        )
    library, key = match.groups()
    if library not in config.libraries(settings):
        raise LinkError(422, f"{library} is not one of the libraries that are synced")

    edit = await cls.get_for_edit(id)  # type: ignore[misc]
    if edit is None:
        raise LinkError(404, f"There is no {model_name} with id {id}")
    if edit.zotero_key:
        raise LinkError(409, f"This is already linked to {edit.zotero_url}")

    address = convert.item_url(library, key)
    elsewhere = await ModelStore()._read(AnyHttpUrl(address))
    if elsewhere is not None:
        raise LinkError(
            409,
            f"{address} is already in the database, as {elsewhere[1].type} {elsewhere[1].id}: use that "
            "one (two entries cannot be joined yet)",
        )

    item = await client.item(library, key)
    if item is None:
        raise LinkError(404, f"{library} has no item {key}")
    fields = convert.stamp(convert.convert(item, library), _now())
    if fields["item_type"] in config.skip_types(settings):
        raise LinkError(
            422, f"A Zotero {fields['item_type']} is not a text that can be linked"
        )
    effective = edit.item_type_override or fields["item_type"]
    if not accepts(cls, effective):
        raise LinkError(
            422,
            f"A {model_name} cannot be a Zotero {effective}. If Zotero has the type wrong, set "
            "item_type_override to what it is, and link again",
        )

    data = edit.model_dump(exclude={"meta"})
    data.update(fields)
    # (0: not a version the sync made, so the node counts as edited by a person, which it has been)
    data["zotero_synced_entity_version"] = 0
    data["urls"] = [*edit.urls, AnyHttpUrl(address)]
    await cls.Update(**data).save(expected_version=edit.meta.version)  # type: ignore[call-arg]


def _now():
    import datetime

    return datetime.datetime.now(datetime.UTC)
