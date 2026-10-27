"""The models: `ZoteroBacked` (what a project builds its text class on), `ZoteroObject`, and `ZoteroLibrary`.

An item is **one entity**, whatever else it is for the project: the project's text class builds on
`ZoteroBacked`, so that it is both what a factoid cites and what a factoid is about. The id of an item is its
Zotero URL (`https://www.zotero.org/groups/2556736/items/ABCD1234`), so a document can name an item before it
has been synced, and the sync fills it in.

The fields that Zotero gives are **read-only** in the API (`Protection`): they are kept up to date by the sync,
which writes through Python. See docs/zotero-sources.md.
"""

import datetime

from pangloss_models.model_bases.entity import Entity
from pangloss_models.protection import Protection

from pangloss_zotero.item_types import ZoteroMeta

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
