# Zotero: keeping a library in the database 🚧

**Status: built and tested against a fake Zotero; never run against the real one.** `pangloss-zotero` brings the
earlier plugin ([`richardhadden/pangloss-zotero`](https://github.com/richardhadden/pangloss-zotero), for the first
Pangloss, on Neo4j) to this version, as an optional package, **one way: from Zotero into the database** (nothing is
written back). 65 tests: the sync, the client, the watcher, the class table, the real store against a live Memgraph,
the commands and the routes. A smoke run used the real `pangloss` command and server on the test database with a
small fake Zotero: sync, a second sync (no change), `status --remote`, the watcher inside the server (reconnecting to
a stream that was down), and the refusals of the API.

What the nodes are, and how a Zotero item is both the source of a factoid and what a factoid is about, is in
[Zotero items as sources and as subjects](zotero-sources.md). **What is not checked:** Zotero's API and stream are
written from memory of its documentation (marked *to check*), and have not met the real service: the first step
with a real library is `pangloss zotero sync --dry-run`.

```python
from pangloss_zotero import ZoteroBacked, ZoteroItemType, ZoteroMeta

class TextObject(ZoteroBacked):
    """Anything that is a text"""
    shelfmark: str | None = None            # (every field of such a class must be optional: see below)

class Atlas(TextObject):
    _zotero_meta = ZoteroMeta(item_types=[ZoteroItemType.BOOK])
```

`INSTALLED_APPS` gets `"pangloss_zotero"`; the settings get `ZOTERO_API_KEY` and `ZOTERO_LIBRARIES = ["groups/2556736"]`.
Then `pangloss zotero sync` (once), or just run the server: it watches.

## What the old plugin did, and what is kept

| Old | Now |
|-----|-----|
| `ZoteroEntry` node, not subclassable and not editable | `ZoteroBacked`, an abstract entity that the project's own class builds on; its Zotero fields are read-only in the API |
| A `ZoteroConfig` node holds the library version synced to | `ZoteroLibrary`, a model (so it has migrations and can be read like any entity) |
| On start: fetch what changed since that version; write each item with a Cypher `MERGE` on the key | The same sequence, written through the models |
| A websocket to `wss://stream.zotero.org`; on `topicUpdated`, sync again | Kept, as a loop with a growing delay (not a recursive restart) |
| Authentication that hangs: wait 10 s, then reconnect and catch up | A timeout on the answer, then a reconnect and a sync |
| `ZOTERO_API_KEY`, `ZOTERO_GROUP`, `ZOTERO_RUN_IN_DEV` | `ZOTERO_API_KEY`, `ZOTERO_LIBRARIES`, `ZOTERO_WATCH` (on whenever the server runs, if a key and a library are set) |
| `translations/` of its own | None: the model texts come from [the translation framework](translations.md) like any app's |

Not kept: the raw items written to a local folder, the group number written into the code, unchecked `TypedDict`s,
and the Neo4j queries. Faults in the old code that are not carried over: a failed request left a variable unset and
the code went on to use it; `latest_version` and `updated_keys` could be used before they had a value; log calls
passed arguments the format did not show; a restart by calling itself, which grows the stack at every disconnect.

## The package

`packages/pangloss-zotero`, like `pangloss-history` and `pangloss-sdk-server`:

| File | What |
|------|------|
| `models.py` | `ZoteroBacked` (abstract), `ZoteroObject` (concrete: the class for items that no class of the project stands for), `ZoteroLibrary` |
| `item_types.py` | `ZoteroItemType` (an enum of Zotero's types, taken from its schema) and `ZoteroMeta`, registered as the meta slot `_zotero_meta` |
| `mapping.py` | The table from Zotero type to class (`build_table`), and `accepts` (can a class be of this type) |
| `convert.py` | A Zotero item as the fields of a model (no database) |
| `client.py` | Zotero's web API: versions, items, deletions, `Backoff` and `Retry-After`, `If-Modified-Since-Version` |
| `sync.py` | One sync of a library, on a `Store`; no database or network of its own |
| `store.py` | The real `Store` (through the models), the sync's user, a dry-run store |
| `watch.py` | `sync_libraries` (once) and `watch` (the stream and the sync loop) |
| `link.py` | Making a text object made by hand an item of the library |
| `api.py`, `cli.py`, `checks.py`, `config.py` | `configure_app` (the watcher as a background task) and the routes; the commands; the checks; the settings |

It needed three small general things in other packages, built first: [meta slots](meta-slots.md) (`_zotero_meta`),
**protection** (`_protect_meta`: fields the API will not let a person change, and a model it will not delete by
hand), and **background tasks** in the API (below).

## Models

```python
class ZoteroBacked(Entity):                  # abstract; create_with_id, create_inline, URLs as ids
    zotero_url: str | None                   # the Zotero address, which is also the id: https://www.zotero.org/groups/2556736/items/ABCD1234
    zotero_library: str | None               # "groups/2556736"
    zotero_key: str | None                   # "ABCD1234" (unique in a library)
    zotero_version: int | None               # the item's version in Zotero
    zotero_synced_entity_version: int | None # the entity's meta.version that the sync made (see "Fields the sync owns")
    item_type: str | None                    # "letter", "book" ...
    title, short_title, language, abstract, date: str | None   # `date` as Zotero has it, as text
    creators: str | None                     # "Last, First; Last, First", in Zotero's order
    zotero_data: str | None                  # the item's `data` as JSON: every field of its type, as Zotero gives it
    citation, bibliography: str | None       # as plain text (the HTML removed)
    csl_json: str | None
    removed_from_zotero: bool | None         # in the trash, or deleted for good but kept
    synced_when: datetime | None
    item_type_override: str | None           # what a person says it is, when Zotero has the type wrong (the only one a person edits)
```

- **Everything is optional**, so a text made by hand has none of it. The `label` is the citation, or the title, or
  the key.
- **The id is the Zotero URL.** A document can name an item before the sync has seen it (`create_new`), and the sync
  finds that node by the URL and fills it in; what cited the stub cites the item (tested).
- **One class for all item types.** About 37 types and 90 fields, which Zotero changes; a model each would be a set
  of generated models and migrations broken by Zotero's changes, and a node would have to change class when an
  item's type did. So: the fields every type has are properties (a map cannot be listed, searched or sorted), the rest
  stays in `zotero_data`, and what a text *means* is in statements about it.
- `zotero_data` is **JSON text**, not a map: a `TypedDict` is stored as a map whose values must be literals or lists of
  literals, and Zotero's `data` has lists of maps. Whether a plain `dict` field is allowed was not checked.
- `creators` is **text**, not a list: a list field is *required* in every `Create` (an empty list must be given),
  which a text made by hand and a stub named by a document would then all have to say. The roles (author, editor,
  recipient) are in `zotero_data`.
- **Every field of a class the sync writes must be optional**, or a list (a relation to many: the sync fills in `[]`).
  A required field that is not a list cannot be given by the sync: the item is reported as an error (not written),
  and `pangloss zotero check` finds the class beforehand. This is how Pangloss makes `Create`, not a choice here;
  it also means a document can name a stub only by giving its lists (`"written_in": []`).

### Choosing the class

`_zotero_meta = ZoteroMeta(item_types=[...], default=False, fallback=False)` on a class says which Zotero types it
stands for. **Nothing is guessed** (`build_table`, which raises `PanglossMetaError` naming the classes):

- Only a class that *declares* the slot counts. A subclass that merely inherits it (`AtlasOfCities(Atlas)`) does
  not claim `book` too ([`declared_slots`](meta-slots.md)).
- A type claimed by two classes needs exactly one of them to say `default=True`; none, or two, is an error.
- A type no class claims is written as the class with `fallback=True` (at most one), or else as the package's
  `ZoteroObject`. Every item is imported; none is skipped for lack of a class.
- A class that says nothing, or is abstract, is an error.
- **A wrong type in Zotero** (a book entered as a document): the person sets `item_type_override` on the node, and
  that is what a class is asked about when a node is linked (below). The class of an existing node is not changed:
  **a node's class is fixed when it is created**, so an item whose type later changes in Zotero keeps its class and
  takes the new `item_type`, and a stub made from a document keeps the class that document gave it.

### Fields the sync owns

`ZoteroBacked` has `_protect_meta = Protection(read_only=<all but item_type_override>, delete_only_if="removed_from_zotero")`.
The **API** refuses (403, saying which) a create that sets those fields, an update that changes them (leaving one out
counts), and a delete of an item that is not `removed_from_zotero`. A subclass keeps this and may add its own. The sync
writes through Python and is not stopped. The remote SDK goes through the API and is covered.

**Zotero wins**: a sync sets the fields again whenever the item's version changed. Everything else a person added
(their own fields, relations, the statements about the item) is kept, because the sync does not use a bare `Update`
(which replaces the whole tree): it reads the item for editing, sets its fields, and writes it back against the
version read, and tries again (up to three times) if a person edited in between.

The sync is a user, `zotero_sync` (made on first use with a password nobody is told; a disabled user cannot write), so
that `created_by` and the history say who made a change. It also lets the sync tell **a person's edit from its own**:
each write sets `zotero_synced_entity_version` to the version it makes, and a `meta.version` that differs means a
person has edited since. (Linking, below, sets it to 0, so a node made by hand counts as edited.)

### Deletion

Deleting in Pangloss only flags a node, and an entity that is referred to is only *marked*. So, **whatever the class**:

| In Zotero | Here |
|-----------|------|
| In the trash | Flagged `removed_from_zotero`; unflagged if it comes back |
| Deleted for good; nothing refers to it; no person has edited it | Deleted (flagged deleted, hidden) |
| Deleted for good; something refers to it, or a person edited it | Kept, flagged `removed_from_zotero`; the citation still reads |
| A deleted item is in Zotero again (restored, or the key reused) | Undeleted, and written again (the id is still taken) |

A person cannot delete a synced item through the API until it is flagged. (The sync checks whether something refers
to an item by reading it, so it never marks an item for deletion by trying.)

## Sync

`sync_library(client, store, table, library, full=False)`, for each library:

1. Read the library's `synced_version` (0 if new, or with `--full`).
2. `GET /<library>/items/top?format=versions&since=V&includeTrashed=1` with `If-Modified-Since-Version: V`: `{key:
   version}` and the library's version (`Last-Modified-Version`); `304` is nothing changed. *To check:* that `/items/top`
   takes `includeTrashed` and `since` as used.
3. Fetch the items in batches of 50 (`itemKey=`, `include=data,citation,bib,csljson`, `includeTrashed=1`). Skipped,
   and counted: `ZOTERO_SKIP_TYPES` (attachments, notes, annotations).
4. Write each (`apply_item`): create it as the class for its type, or set the fields of the node with that URL
   (found as any class, the most specific first). An item whose version and trash state are as held is left alone.
5. If a version was held: `GET /<library>/deleted?since=V` and deal with each key as in the table above.
6. Store the new version **only if every item was written**. A failure to write one item is in `report.errors` (and
   `last_error`), the others are written, and the next sync does it all again from the old version (writing an item
   twice changes nothing). A failure to reach Zotero is recorded and raised.

Zotero asks for: `Zotero-API-Key` and `Zotero-API-Version: 3`; waiting for `Retry-After` (on 429 and 503) and
`Backoff`; and `If-Modified-Since-Version`. The client does all of it (up to 5 attempts; a wrong key, 401 or 403, is not
tried again); a refused key is `ZoteroAuthError`.

**Finding a node by its URL.** `Model.get(url)` on a class gives a node of a subclass as that subclass (this was
not so at first: it raised, and was fixed with this package: see [Defining models](models.md)), so the store asks only
the concrete classes that have no concrete parent. A deleted node is not found by `get`; it is found by trying
`undelete`, which is also what is wanted.

### Linking a text object made by hand

The Zotero fields cannot be set through the API, so `POST /api/zotero/link` `{model, id, zotero_url}` (logged in) is how
a node made by hand becomes an item (`link.py`). It refuses (with the reason): a model that is not a Zotero class
(422); an address that is not `https://www.zotero.org/{groups|users}/N/items/KEY` or in a library that is not synced
(422); a node that is already linked (409); an item that is **already a node** (409: "use that one", since two nodes
cannot be joined yet); an item that is not in the library (404); a class that cannot be of the item's type (422:
the type is `item_type_override` if the node has one, else Zotero's; a class with no `_zotero_meta` accepts any). Then
it writes the item's fields and adds the address to the node's URLs.

### Watching

`watch(settings)`: sync every library, then hold the stream (`wss://stream.zotero.org`): wait for `connected`, send
`createSubscriptions` with the key and the topics (`/groups/N`), wait for `subscriptionsCreated` (10 s, then connect
again; errors in the answer are reported), and on `topicUpdated` sync that library. *To check:* the message shapes.
Events that arrive during a sync make **one** more sync. After any failure it connects again after 5 s, doubling to
5 minutes (back to 5 after a connection that lasted a minute), and syncs after each connection (what was missed is
caught up by the version). A stream that cannot be reached is one warning line, not a traceback. A library that cannot
be synced is logged and tried again after a delay (a refused key: every 5 minutes), and recorded as `last_error`.

## Background tasks (in `pangloss-api`)

The question was a thread at startup, an `asyncio` task on the server's loop, or a worker with a queue. **An
`asyncio` task, supervised**: the database driver, the HTTP client and the websocket are all async and bound to
the server's loop, so a thread would need a loop and connection of its own, and a queue adds a service (Redis) for one
long-running loop. CPU-heavy work, if it turns up, goes to `asyncio.to_thread`.

`pangloss_api/background.py`: an app's `api.py` adds `BackgroundTask(name, run)` to `app.state.background_tasks` in
`configure_app`. The lifespan starts each after the migration check and the startup hooks, and before the database
disconnects it cancels them and waits (5 s, then a warning for one that will not stop). A task that raises is logged
with the traceback and started again after a delay that doubles from 1 s to 60 s (back to 1 s after a run that lasted a
minute); one that returns or is cancelled is not restarted. A write refused during a migration is an error like any
other, so it is tried again after the delay. `app.state.supervisor.status()` says each task's state, restarts and
last error (`GET /api/zotero/status` includes the watcher's). `pangloss dev` restarting the server cancels and
starts the task; the sync catches up from the stored version. (Tested: restart with growing delay, a long run resets
it, a task that returns, cancel leaves none running, a task that will not stop, duplicate names, and a whole app
started and stopped with the server.)

**More than one server process.** `pangloss run` is one process. With `--workers N` each would watch, and write
the same items. Set `ZOTERO_WATCH = False` in the server and run `pangloss zotero watch` (the same function) as one
process. A *lease* (a claim with an expiry on `ZoteroLibrary`) is the general answer and is **not built**; a sync run
by hand beside the server's is safe, as writes are against the version read (the worst case is a retry).

## Commands and settings

| Command | Does |
|---------|------|
| `pangloss zotero sync [-l LIBRARY] [--full] [--dry-run]` | One sync now. `--dry-run` reads and counts, and writes nothing (not the library's version either); exit 1 if an item could not be written |
| `pangloss zotero watch` | The watcher, until stopped (for a server with several workers) |
| `pangloss zotero status [--remote]` | For each library: the version held, Zotero's with `--remote`, when it was synced, the last error; and the class for each item type |
| `pangloss zotero check` | The settings (key, libraries), the `_zotero_meta` declarations (the errors above), and the classes the sync cannot write (a required field that is not a list). Exit 1 if anything is wrong |

| Setting | Meaning |
|---------|---------|
| `ZOTERO_API_KEY` | A key that can read each library (from the environment, not the settings file) |
| `ZOTERO_LIBRARIES` | `["groups/2556736"]`; a user library is `users/N` |
| `ZOTERO_WATCH` | Run the watcher in the server (default `True`, if the key and libraries are set) |
| `ZOTERO_SKIP_TYPES` | Types not imported (default attachment, note, annotation) |
| `ZOTERO_SYNC_USER` | The user the sync writes as (default `zotero_sync`) |
| `ZOTERO_API_URL`, `ZOTERO_STREAM_URL` | Zotero's addresses (to point at a fake) |

## Not built

- **The read-only flag in the exported models**, so that the interface shows the fields read-only
  ([meta slots](meta-slots.md)). The interface itself is untouched: a search of the library for a source field, and a
  "link to Zotero" action that offers the imported items, are for when it is built.
- **`check` for the database**: duplicates (two nodes for one work), a node whose class is not the one the table now gives,
  a node whose item is not in the library any more. It needs reading every item.
- A **lease** for several workers (above); a **merge of two entities** (re-point relations, URLs and history, delete the
  second), which the duplicate case needs; the first import in a **bulk** way (each item is written one at a time:
  measure on a real library before deciding; the bulk loader needs an empty database).
- Attachments and notes (skipped); parsing Zotero's text dates (the [dates design](dates.md)).

## Open questions

1. **A real library**: the API calls and the stream are as remembered. Zotero's terms of use for the stream and the rate
   were not read.
2. **Several libraries with different classes**: the table is global, so a type is one class in all of them.
3. **Who can see what**: a private group's items are visible to anyone who can read the API (reads need no login). That
   is for the project, and is the [access control](../TODO.md) question.
