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

### Or decide by hand

Zotero's type cannot always be trusted, and a book that is only a secondary source should not look like a historical
object. Then claim no types: every item comes in as a `ZoteroObject`, and a person decides which ones are a `Book`.

```python
class Book(ZoteroBacked):
    pages: int | None = None
```

In the interface, with `pangloss_zotero` installed:

- **From Zotero**, on the form of a new `Book`: pick an item; the form is filled in from it; Save makes that item the
  `Book`. It is the same entity (its id, its address, and whatever already cited it), and it stays an item of the
  library: the sync keeps its Zotero fields up to date.
- **Link to Zotero**, on a `Book` made by hand: pick an item. If the item is already an entry, the two become one,
  keeping the one that something refers to; if both are referred to, it is refused and says what refers to each.
- **Unlink from Zotero**: the `Book` keeps its own fields and what refers to it; the item is a `ZoteroObject` again.

## Run

```bash
pangloss zotero sync            # once: fetches what changed since the version last synced (a second run changes nothing)
pangloss zotero watch           # follow the stream until stopped
pangloss zotero status          # --remote also asks Zotero
pangloss zotero check           # the library against the database
```

Or just run the server: it watches. The sync is idempotent and runs by version, so a restart catches up.

A first sync of a large library takes a while (Zotero gives 50 items at a time, with their citations). It can be
stopped: the version it has reached is stored every half minute, and the next run goes on from there.
`pangloss zotero status --remote` says how far it is (`version 6883 of 16006 (behind), first sync not finished`).

An item that cannot be written is named in `last error` (in `status`), and does not stop the others. The watcher
tries it again by itself, after longer each time; so does any later `pangloss zotero sync`. While
`pangloss migrate` runs nothing can be written, and the sync waits for it.

## What the nodes are

`zotero_url` (also the entity's id, `https://www.zotero.org/groups/2556736/items/ABCD1234`), `zotero_library`,
`zotero_key`, `zotero_version`, `item_type`, `title`, `short_title`, `language`, `abstract`, `date` (as Zotero has it, text),
`creators` (`Last, First; …`) and `zotero_data` (every field of its type, as JSON). **These fields are read-only in the
API**: a person cannot edit what the sync owns; your own extra fields stay editable. A text object made by hand can be
linked to an item afterwards (above).

Then use it as any entity: `Factoid.source` can point at an `Atlas`, a statement can be about one, and the SDK and search
find it.

## Not yet

A `check` that finds duplicates or items that left the library; a lease so that several server workers do not all sync;
merging two entities; a bulk first import (each item is written one at a time: measure on a real library); attachments and
notes; parsing Zotero's text dates; a search of the library in a source field of a form; the Zotero fields shown read-only
on a form.
[Zotero](../../docs/zotero.md) and [Zotero items as sources and subjects](../../docs/zotero-sources.md) have the design.
