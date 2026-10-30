# Zotero: a library kept in the database

`pangloss-zotero` keeps a Zotero library (a user's or a group's) in the database, **one way: from Zotero**. Nothing is
written back. Each Zotero item becomes an entity that can be **the source of a factoid** and also **what a factoid is
about**, as one node.

> It is tested against a fake Zotero and the test database. It has **not been run against the real Zotero**: Zotero's API
> and stream are as remembered, and its rate rules were not read. Try it on a small group library first.

## Set up

Add `"pangloss_zotero"` to `INSTALLED_APPS`, and to the settings:

| Setting | |
|---|---|
| `ZOTERO_API_KEY` | A key from zotero.org that can read the libraries |
| `ZOTERO_LIBRARIES` | `["groups/2556736"]` or `["users/12345"]` |
| `ZOTERO_WATCH` | Default `True`: the server follows the library's stream, in a background task, while it runs |
| `ZOTERO_SKIP_TYPES` | Item types not imported (default attachment, note, annotation) |
| `ZOTERO_SYNC_USER` | The user the sync writes as (default `zotero_sync`) |

## Choose the class of each item

`ZoteroBacked` is an abstract entity that your own class builds on. Which class an item becomes is decided by the item
types a class says it accepts:

```python
from pangloss_zotero import ZoteroBacked, ZoteroItemType, ZoteroMeta


class TextObject(ZoteroBacked):
    """Anything that is a text"""
    shelfmark: str | None = None            # extra fields of your own must be optional


class Atlas(TextObject):
    _zotero_meta = ZoteroMeta(item_types=[ZoteroItemType.BOOK])
```

An item whose type no class claims becomes a `ZoteroObject`, the package's own plain class. Run `pangloss makemigrations`
and `migrate` as for any model.

## Run

```bash
pangloss zotero sync            # once: fetches what changed since the version last synced (a second run changes nothing)
pangloss zotero watch           # follow the stream until stopped
pangloss zotero status          # --remote also asks Zotero
pangloss zotero check           # the library against the database
```

Or just run the server: it watches. The sync is idempotent and runs by version, so a restart catches up.

## What the nodes are

`zotero_url` (also the entity's id, `https://www.zotero.org/groups/2556736/items/ABCD1234`), `zotero_library`,
`zotero_key`, `zotero_version`, `item_type`, `title`, `short_title`, `language`, `abstract`, `date` (as Zotero has it, text),
`creators` (`Last, First; …`) and `zotero_data` (every field of its type, as JSON). **These fields are read-only in the
API**: a person cannot edit what the sync owns; your own extra fields stay editable. A text object made by hand can be
linked to an item afterwards.

Then use it as any entity: `Factoid.source` can point at an `Atlas`, a statement can be about one, and the SDK and search
find it.

## Not yet

A `check` that finds duplicates or items that left the library; a lease so that several server workers do not all sync;
merging two entities; a bulk first import (each item is written one at a time: measure on a real library); attachments and
notes; parsing Zotero's text dates; the interface (a library search, a "link to Zotero" action).
[Zotero](../../docs/zotero.md) and [Zotero items as sources and subjects](../../docs/zotero-sources.md) have the design.
