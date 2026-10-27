# Zotero: keeping a library in the database ⏳

**Status: a plan, not built.** It brings the earlier plugin
([`richardhadden/pangloss-zotero`](https://github.com/richardhadden/pangloss-zotero), for the first Pangloss, on
Neo4j) to this version as an optional package, `pangloss-zotero`. What the nodes are, and how a Zotero item is
both the source of a factoid and what a factoid is about, is in [Zotero items as sources and as
subjects](zotero-sources.md); this page assumes its recommendation (option C). Facts about Zotero's API are from
memory of its documentation and **must be checked against the current docs** before they are built on (marked
*to check*).

## What the old plugin did, and what is kept

| Old | Now |
|-----|-----|
| `ZoteroEntry` node (Zotero key, group, version, URL, CSL JSON, bibliography, citation), a node that cannot be subclassed and is not editable | The fields move to an abstract `ZoteroBacked` entity that the project's own class builds on (see [the modelling page](zotero-sources.md)) |
| A `ZoteroConfig` node holds the library version synced to | A record of each library's synced version (below) |
| On start: fetch what changed since that version; write each item with a Cypher `MERGE` on the key | The same sequence, written through the models (below) |
| A websocket to `wss://stream.zotero.org`; on `topicUpdated`, sync again | Kept. As a loop, not a recursive restart |
| Authentication that hangs: wait 10 s, then reconnect and catch up | Kept as a timeout and a reconnect with a growing delay |
| `ZOTERO_API_KEY`, `ZOTERO_GROUP`, `ZOTERO_RUN_IN_DEV` in the settings | `ZOTERO_API_KEY`, `ZOTERO_LIBRARIES` (a list: a group or a user library), and `ZOTERO_WATCH` (on by default, so the watcher runs whenever the server does) |
| `translations/` of its own | The model texts are made by [the translation framework](translations.md) like any app's; a `ui.jsonc` only if it adds interface text |

Not kept: the raw items written to a local `zotero_items/` folder, the group number written into the code,
`TypedDict`s that were never checked (the response is read with a model that validates), and `Neo4j`-specific
queries.

Faults found in the old code, so as not to be carried over: a failed request left `r` unset and the code went
on to use it; `latest_version` and `updated_keys` could be used before they had a value; log calls passed extra
arguments the format string does not show; a restart by calling itself again, which grows the stack for every
disconnect.

## Package

An optional package in this repository, like `pangloss-history` and `pangloss-sdk-server`: `packages/pangloss-zotero`,
installed by adding `"pangloss_zotero"` to `INSTALLED_APPS`. It uses what an installed app can already add:

| File | Uses |
|------|------|
| `models.py` | `ZoteroBacked` (abstract), `ZoteroObject` (concrete, the default `ZOTERO_MODEL`), and the record of a library |
| `cli.py` | `pangloss zotero sync`, `watch`, `status`, `check` |
| `api.py` | `configure_app(app, settings)`: registers the watcher as a background task, and a small router (`/api/zotero/status`, and the search of items the interface needs) |
| `config.py` | The settings, read from the project's settings as `pangloss-history` does |

**Needs a change to the API's lifespan.** `app.state.startup_hooks` exists (awaited at start, after the migration
check); nothing runs at shutdown, and there is no way to run something for as long as the server does. Add
**background tasks** to the API: registered by an app, started and supervised by the lifespan, and cancelled before
the database disconnects (see "Background tasks" below). A small, general change that other packages need too.

**Needs the models to run the same way outside the server.** The sync writes with `Model.Create` and
`Model.Update`, which need the database module connected. `pangloss zotero sync` must make the connection as the
server does (the history package's CLI is the precedent).

## Models

```python
class ZoteroBacked(Entity):          # abstract
    # where it is from
    zotero_url: str | None           # the id, too: https://www.zotero.org/groups/2556736/items/ABCD1234
    zotero_library: str | None       # "groups/2556736"
    zotero_key: str | None           # "ABCD1234" (unique within a library)
    zotero_version: int | None       # the item's version in Zotero
    # the fields that (nearly) every item type has, as properties: to list, search and sort by
    item_type: str | None            # "letter", "book" ...
    title: str | None
    short_title: str | None
    creators: list[str]              # "Last, First", in Zotero's order (the roles are in zotero_data)
    date: str | None                 # as Zotero has it (text); parsed dates are the dates package's business
    language: str | None
    abstract: str | None
    # the rest
    zotero_data: str | None          # the item's `data` as JSON text: every field of its type, as Zotero gives it
    citation: str | None             # the formatted citation, HTML removed
    bibliography: str | None         # the formatted entry
    csl_json: str | None             # the item as CSL JSON, kept as text
    removed_from_zotero: bool = False
    synced_when: datetime | None
```

- The **label** is the citation (the plain text), so that lists and searches show something a person can read.
- **The id is the Zotero URL.** `create_with_id` and `accept_url_as_id` are on, so a document can name an item before
  the sync has seen it. The sync looks an item up by that URL and takes a node that is only a stub.
- **One class for all item types, not one model each.** [Zotero's item types and fields](https://www.zotero.org/support/kb/item_types_and_fields)
  are about 37 types and 90 fields, and Zotero adds and renames them. A model for each would be a set of generated
  models, labels and migrations for each, broken by a change that Zotero makes and not you, and it would make the type
  of a node something that has to change when an item's type does. Instead:
  - the fields every type shares (title, creators, date, language, abstract, short title, and the type itself) are
    properties, because lists and searches use them and a map cannot be searched or sorted;
  - everything else (publisher, volume, DOI, the field a letter has that a book has not) stays in `zotero_data`, as
    Zotero gives it, so a field Zotero adds needs no migration;
  - what a text *means* (who sent it, who signed it) is in statements about it, not in its Zotero fields.
  The interface can show `zotero_data` as a list of labelled fields, using Zotero's own labels for the type.
- **`zotero_data` is JSON text**, not a map field. A `TypedDict` is stored as a map, but its values may only be
  literals or lists of literals, and Zotero's `data` has lists of maps (the creators). Whether a plain `dict` field is
  allowed was not checked: if it is, and the database holds nested maps, it could be a real map; the text costs
  nothing now and can be changed by a migration.
- `creators` is `list[str]` for the same reason: a list of embedded objects is rejected at `initialise()`. The roles
  (author, editor, recipient: the last matters for a letter) are in `zotero_data`.
- `ZoteroObject(ZoteroBacked)` is concrete, for projects that want only the sync's own class.
- **A record of each library** (`ZoteroLibrary`: `library` id, `synced_version`, `last_sync`, `last_error`) is a model,
  so that it has a migration and an interface of its own like any entity, instead of a node the migrations cannot
  see (the old `ZoteroConfig` was one). Choosing between this and a small file in `.pangloss/` as history does:
  the model, so that it follows the database it describes (a restored database is then synced from the version it
  has, not the version a file elsewhere remembers).

### Fields the sync owns

The sync owns the `zotero_*`, `citation`, `bibliography` and `csl_json` fields and **Zotero wins**: they are set on
every sync, whatever a user has changed. The user's relations and fields (their `language`, what the item is
about, the statements that refer to it) are not touched. That is why the sync does **not** use a bare `Update`
(which replaces the whole tree, including relations the sync does not know of):

- **Preferred:** read the item (`get`), change only its owned fields, write it back with `expected_version`, and
  retry on a conflict (the user edited at the same moment; at most a few attempts, then report). It keeps
  validation, the history of the item, and the user's data.
- **Not for bulk:** a first sync of a library of tens of thousands of items does this once per item, so the
  first import creates the nodes in batches (`Create` for what does not exist), and only a later change uses the
  read-and-write path.
- **Alternative:** a direct query that sets just the owned properties (fast, no conflict, but outside the
  models: no history, no version). The write path would need a function in the database module for it. Not the
  first version.

Protecting the fields from a user's edit is a question for the models, not this package: see "Open questions" in
[the modelling page](zotero-sources.md). Until it is decided the interface shows them as read-only and the next
sync restores them.

The sync is a user: it writes as `zotero_sync` (a `PGUser` that must exist, as every writer must; the CLI
creates it, disabled for login), so that the history and `created_by` say who made a change.

## Sync

For each library in `ZOTERO_LIBRARIES` (*to check* each detail):

1. Read the library's `synced_version` (0 if new).
2. Ask Zotero for the keys of the items changed since it (`GET /<library>/items?since=<version>&format=versions`
   returns `{key: version}`; `Last-Modified-Version` is the library's new version).
3. Fetch them in batches of up to 50 (`itemKey=A,B,...`, with `include=data,csljson,bib,citation`), skipping
   attachments, notes and annotations (decision below).
4. Write each: create it as the configured class, or update the owned fields of the one that is there (found
   by its URL id).
5. Ask for what was deleted since the version (`GET /<library>/deleted?since=`), and flag each as
   `removed_from_zotero` (never delete: a factoid probably cites it, and `delete` of a referred entity only marks
   it anyway).
6. Set `synced_version` to the new library version **only after** the writes succeeded. A sync that stops
   half-way is repeated from the old version; writing an item twice is harmless (same fields).

Rules to follow, because Zotero asks for them: send the API key as `Zotero-API-Key`, send
`Zotero-API-Version: 3`, honour `Retry-After` and `Backoff` headers (wait; do not retry at once), and send
`If-Modified-Since-Version` so that nothing is sent when nothing has changed.

An item fetched while it is being edited can change between steps 2 and 3: its version in the response is the one
written, and a later `topicUpdated` fetches it again.

### Watching

`wss://stream.zotero.org`: connect, send a subscription with the API key and the topics (`/groups/<id>`,
`/users/<id>`), wait for the confirmation (timeout, then reconnect: the case that hung before), and on
`topicUpdated` run the sync of that library (*to check* the message shapes). One loop, with a growing delay
between reconnects, and a sync after every reconnect (events missed while away are caught up by the version).
Events that arrive while a sync runs set a flag: one more sync follows, not one for each. A library that cannot
be synced (a wrong key, a withdrawn permission) is logged once, recorded as `last_error`, and not retried every
second.

**Where it runs: in the server, as a background task** (below). The watcher is one function, `watch(settings)`,
which the server runs as a task and `pangloss zotero watch` runs on its own, so a deployment that cannot run it in
the server (several workers) has the other way without a second implementation.

| Mode | How | For |
|------|-----|-----|
| In the server | A background task (below), started with the server; on by default when `ZOTERO_API_KEY` and `ZOTERO_LIBRARIES` are set | `pangloss run` and `pangloss dev`, and a single-process deployment |
| `pangloss zotero watch` | The same function, in a process of its own (and `ZOTERO_WATCH = False` in the server) | A deployment with several server workers |
| One shot | `pangloss zotero sync [--library X] [--full]` | A first import, a cron job, or after a long stop |

## Background tasks

The question: a thread started at startup, an `asyncio` task on the server's event loop, or a separate worker with a
queue. The same need is in [the dates design](dates.md) (a worker that derives the calendar edges, "a task in
`pangloss run`, or `pangloss calendar worker`") and in the TODO item for derived nodes written later; so this is
worth building once, in the API, and not in the Zotero package.

| | A task on the event loop | A thread | A queue and workers (Celery, arq, ...) |
|---|---|---|---|
| Fits this code | **Yes.** The database driver (`neo4j` async), the Zotero requests and the websocket are all `async`, and `Model.Create` and `.save()` are coroutines on that loop | The driver's connections belong to one event loop: the thread would need its own loop and its own connection, and `Database.default` is the server's | Needs a broker (Redis) that nothing else here uses |
| What it costs the server | Nothing while it waits for the network, which is nearly all of its time. A long blocking step would stall requests, so any CPU-bound piece goes to `asyncio.to_thread` | A second loop; shared state to lock | A service to run |
| Stopping it | `task.cancel()` in the lifespan, which is what the shutdown is for | Cooperative flags; a thread cannot be cancelled | The queue's own |
| Crash | Caught by a supervisor that logs and restarts it with a delay | Same | The queue's own |
| Several server processes | Each has one: needs a lease | Same | One by design |

**Recommended: an `asyncio` task, supervised, and nothing more.** There is no job to hand over, only one
long-running loop per library, so a queue adds a service for no use. A thread has the disadvantages of both. (If
something CPU-heavy turns up, `asyncio.to_thread` or a process pool handles that piece without changing this.)

**The mechanism, in the API (a small general feature, written first):**

- An installed app's `api.py` registers a background task: `app.state.background_tasks.append(Task(name, run, ...))`,
  next to `startup_hooks`. `run` is `async def run(settings)` that loops until cancelled.
- The lifespan, after the migration check and the startup hooks, starts each as an `asyncio` task **inside a
  supervisor**: if the task raises, log it (with the traceback), wait (a delay that doubles to a limit, back to the
  start after a run that lasted), and start it again. A task that returns is not restarted. A cancelled task is not
  restarted.
- In the `finally` of the lifespan, before the database disconnects, cancel every task and wait for it (with a
  timeout, and a warning for a task that does not stop). This is why there must be a shutdown step: a task left
  running would use a closed connection.
- A task is not started if the migration check failed or while a migration runs (writes are refused then), and
  starts when it is clear. For `warn` and `off` it starts.
- `pangloss dev` restarts the server when a file changes; the task is cancelled and started again, and the sync
  catches up from the stored version, so nothing is lost by a restart.
- A task is named and reported: `/api/zotero/status` (and, in general, `pangloss status`) can say which are running,
  when they last did something and the last error.

**More than one server process.** `pangloss run` is one uvicorn process, so there is one task. A production setup
with `--workers N` or several containers would have N, writing the same items. Two answers, both small:

1. Run the watcher apart (`pangloss zotero watch`, `ZOTERO_WATCH = False` in the server): one process by construction.
   This is the documented way for that setup.
2. A **lease**: before it syncs, a task claims the library by setting `lease_holder` and `lease_until` on its
   `ZoteroLibrary` in one conditional write (compare and set), and renews it as it works; one that cannot claim it
   waits and tries again. A process that dies lets the lease run out. The same mechanism serves any background task, so
   it belongs to the general feature if a second task needs it (the calendar worker's batches claim the same way).
   Not in the first version: a single process is the case that exists now.

A sync that is also running by `pangloss zotero sync` while the server's task runs is safe in the same way: writes
are of the owned fields with `expected_version`, so the worst case is a retry; the lease makes it a refusal.

## Commands

| Command | Does |
|---------|------|
| `pangloss zotero sync [--library X] [--full] [--dry-run]` | One sync now; `--full` ignores the stored version; `--dry-run` says what would be created and changed |
| `pangloss zotero watch` | Sync, then listen and sync on each change |
| `pangloss zotero status` | For each library: the stored version, Zotero's current one, the time of the last sync and the last error, and the counts (items, flagged removed) |
| `pangloss zotero check` | Reports items with likely duplicates (same title and creators) in the database, nodes whose Zotero URL is not in the library any more, and a `ZOTERO_MODEL` that does not exist |

## Settings

| Setting | Meaning |
|---------|---------|
| `ZOTERO_API_KEY` | A key with read access to each library (a secret: from the environment, not the settings file) |
| `ZOTERO_LIBRARIES` | For example `["groups/2556736"]`; a user library is `users/<id>` |
| `ZOTERO_MODEL` | The class items are written as (default `"ZoteroObject"`) |
| `ZOTERO_WATCH` | Run the watcher in the server (default `True` if the key and libraries are set; `False` when it runs apart with `pangloss zotero watch`) |
| `ZOTERO_SKIP_TYPES` | Item types not imported (default `["attachment", "note", "annotation"]`) |

## Interface

Nothing in the interface changes in this plan. When it is built: a source field that **searches the library**
(citation text, creators, key) over the entities of the class and shows the citation; a "link to Zotero" action
on a text object that offers the imported items; and the Zotero fields shown read-only. Texts it needs are in the
package's `translations`.

## Tests

- The Zotero side is faked: a small server (or recorded responses) for the versions, the items and the deletions,
  with `Backoff` and a failure half-way; the websocket by a fake that sends `topicUpdated` and drops.
- A sync twice makes no change; a sync after a failure half-way makes the same database as one that did not
  fail; a change in Zotero changes only the owned fields and keeps a relation added by a user in between;
  a conflicting edit is retried; a deleted item is flagged, not removed.
- A factoid that names an item by its URL before the sync, then the sync: one node, now with the Zotero fields.
- The listener: reconnects after a drop, after an authentication timeout, and stops on shutdown with no task left.
- Nothing needs a real Zotero account; one manual check against a real library is a step of the build, not of the
  test suite.

## Order of work

1. **Decide** [the modelling question](zotero-sources.md) and what is wanted of a read-only field and of a merge of
   entities (its open questions 1 and 2).
2. **Background tasks in the API** (registration, supervisor with restart and delay, cancel on shutdown, not during a
   migration), with tests of their own: a task that raises is restarted; one that is cancelled stops; shutdown
   leaves none running.
3. The package skeleton, models and settings; a migration for them.
4. `sync` once (create and update, versions, deletions), against the fake.
5. `watch`, run as the server's task and by its own command.
6. `status` and `check`.
7. Try it on a real library, and on the demo (its `Source` brought onto `ZoteroBacked`).

## Open questions

1. The modelling ones in [zotero-sources.md](zotero-sources.md).
2. **Attachments and notes.** Skipped by default. Whether a link to the PDF is wanted (a `links` field), and where
   file storage would live, is not decided and is not part of this.
3. **The first import of a large library.** Time and rate: a group of tens of thousands of items takes many
   requests; whether the first import should be a file the bulk loader can read (it needs an empty database) or the
   batches above is for after measuring.
4. **Dates.** Zotero's `date` is text, in any format. It is kept as text. Reading it as a date belongs to the
   [dates design](dates.md) once that exists.
5. **Who can see what.** A group library may be private; the node is visible to anyone who can read the API (reads
   need no login). Whether that is acceptable for a particular library is for the project, and links to [access
   control](../TODO.md), which is undecided.
6. **Zotero's terms of use for the stream and the rate.** To read before building the watcher.
