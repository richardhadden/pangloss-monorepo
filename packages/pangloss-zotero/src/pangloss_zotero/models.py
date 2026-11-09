"""The models: `ZoteroBacked` (what a project builds its text class on), `ZoteroObject`, and `ZoteroLibrary`.

An item is **one entity**, whatever else it is for the project: the project's text class builds on
`ZoteroBacked`, so that it is both what a factoid cites and what a factoid is about. The id of an item is its
Zotero URL (`https://www.zotero.org/groups/2556736/items/ABCD1234`), so a document can name an item before it
has been synced, and the sync fills it in.

The fields that Zotero gives are **read-only** in the API (`Protection`): they are kept up to date by the sync,
which writes through Python. See docs/zotero-sources.md.
"""

import datetime

from pangloss_models import Entity, Protection

from pangloss_zotero.item_types import SLOT, ZoteroMeta

# The fields the sync writes. A person changes none of them (the API refuses), except `item_type_override`.
OWNED_FIELDS = (
    "zotero_url",
    "zotero_library",
    "zotero_key",
    "zotero_version",
    "zotero_synced_entity_version",
    "item_type",
    "title",
    "short_title",
    "creators",
    "date",
    "language",
    "abstract",
    "zotero_data",
    "citation",
    "bibliography",
    "csl_json",
    "synced_when",
)


def _override_unless_typed(model: type) -> tuple[str, ...]:
    """`item_type_override` is asked only of a class that names the Zotero types it stands for (`accepts`): the forms
    of the others do not show it"""
    meta = getattr(model, SLOT, None)
    return () if meta is not None and meta.item_types else ("item_type_override",)


def _only_used_at_first(model: type) -> bool:
    """A list of what the sync brings in is mostly of what nothing cites yet: those classes (the fallback, and any that
    claim item types), and the list of every item, show what is used at first. A class that is only made by hand (no
    Zotero types: the demo's Book) lists what people made"""
    return model.__name__ == "ZoteroBacked" or getattr(model, SLOT, None) is not None


def interface_meta() -> dict:
    """What the forms do not show, and the page of an item, if the interface is installed"""
    try:
        from pangloss_interface import InterfaceMeta
    except ImportError:
        return {}
    return {
        "_interface_meta": InterfaceMeta(
            hide_on_forms=_override_unless_typed,
            item_page="pangloss_zotero:ZoteroItemPage",
            list_used_only=_only_used_at_first,
        )
    }


class ZoteroBacked(Entity):
    """A text that is (or may be) an item in a Zotero library. Everything is optional, so one made by hand has
    none of it. Build your class on this: `class TextObject(ZoteroBacked)`."""

    _meta = Entity.Meta(
        abstract=True, create_with_id=True, create_inline=True, accept_url_as_id=True
    )
    _protect_meta = Protection(
        read_only=(*OWNED_FIELDS, "removed_from_zotero"),
        delete_only_if="removed_from_zotero",
    )
    locals().update(interface_meta())

    # where it is from
    zotero_url: str | None = None
    zotero_library: str | None = None  # "groups/2556736"
    zotero_key: str | None = None  # "ABCD1234" (unique in a library)
    zotero_version: int | None = None  # the item's version in Zotero
    zotero_synced_entity_version: int | None = (
        None  # `meta.version` the sync made: more is a person's edit
    )
    # the fields that (nearly) every type has, to list and search by
    item_type: str | None = None  # "letter", "book" ...
    title: str | None = None
    short_title: str | None = None
    creators: str | None = (
        None  # "Last, First; Last, First", in Zotero order (a list would be required in every Create; roles are in `zotero_data`)
    )
    date: str | None = None  # as Zotero has it (text)
    language: str | None = None
    abstract: str | None = None
    # the rest
    zotero_data: str | None = (
        None  # the item's `data` as JSON: every field of its type, as Zotero gives it
    )
    citation: str | None = None  # the formatted citation, as plain text
    bibliography: str | None = None  # the formatted entry, as plain text
    csl_json: str | None = None  # the item as CSL JSON
    removed_from_zotero: bool | None = (
        None  # in the trash, or deleted for good, but kept
    )
    synced_when: datetime.datetime | None = None
    # what a person says: "Zotero has this as a document, but it is a book"
    item_type_override: str | None = None


class ZoteroObject(ZoteroBacked):
    """A Zotero item that no class of the project stands for"""

    _meta = Entity.Meta(
        abstract=False, create_with_id=True, create_inline=True, accept_url_as_id=True
    )
    _zotero_meta = ZoteroMeta()


class ZoteroLibrary(Entity):
    """How far a library has been synced. The id is its URL (`https://www.zotero.org/groups/2556736`)."""

    _meta = Entity.Meta(create_with_id=True, accept_url_as_id=True)
    _protect_meta = Protection(
        read_only=("library", "synced_version", "last_sync", "last_error")
    )

    library: str | None = None  # "groups/2556736"
    synced_version: int | None = None
    last_sync: datetime.datetime | None = None
    last_error: str | None = None
