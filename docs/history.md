# History: tracking changes and restoring earlier versions ✅

**Status: built (phases 0 to 4; see the "As built" sections and [the guide](../guide/history/README.md)).** The sections down to "Phases" are the design as first written, and "What exists now" describes the code before it was built. Not built: the interface's form for a draft, upgrading across wrap/unwrap, annotated-value and embedded changes, enum values inside annotated values and edge properties, and a purge command with an erasure policy. Not yet run against a long-lived project. Numbers marked *measured* come from a throwaway
benchmark on a laptop (2026-10-21); *to check* marks a fact about the existing code that the design depends on and
that has not been verified.

The aim: keep every version of every Document and Entity (a *head node*), so that one can be looked at, compared
with another, and **restored**, including after the models have changed in the meantime.

**It is best effort.** A change is recorded after the write has succeeded; if recording fails or the server stops
at the wrong moment, the write stands and the history has a gap. Nobody is promised a complete history. This
keeps the write path as fast and as simple as it is now.

## What exists now

- An update **replaces the whole tree** under the head node (`build_update_query.py`: delete everything below it
  except entities, then write the new tree as a creation). An update is therefore always a complete document: no
  diffs are needed to know a version's content.
- A `PGCreation` / `PGUpdate` node records *who* and *when*. `meta.version` is the number of `PGUpdate` nodes
  plus one. Nothing records *what* changed.
- A delete only **flags** a node (`PGDeletion`; `PGUndeletion` to undo). Entities are never removed by an update
  (they belong to no document). So an entity that an older version refers to is still there, or can be undeleted.
- Updates can be made conditional on a version (`expected_version`, the `If-Match` of the API).
- Migrations are files of structured changes (`AddField` with a default, `RemoveField`, `RenameModel`, a type
  change, ...), applied to the database by Cypher, with a reverse for each (`migrations/reverse.py`).

## Goals and non-goals

Goals:

- List the versions of a head node (version, who, when, what kind of change); show any version; show the
  difference between two.
- Restore a version as a new version.
- Still work after model changes where that can be done (see "When the models have changed").

Non-goals:

- A guarantee that history is complete (best effort, above).
- Restoring the whole graph to a moment in time. A restore is of **one head node**; the entities it refers to are
  referred to as they are *now*.
- History in Memgraph. See "Where it is kept".
- Undoing a migration's effect on data: that is `migrate ... zero` and backups ([migrations guide](../guide/migrations/README.md)).
  (History does help: it keeps what a lossy migration removed. See "Interactions".)
- A policy for erasing history (below: only a promise not to design it out).

## What is stored

For each write to a head node, one **record**:

| | |
|---|---|
| `head_id`, `version` | The head node and the version that this write made (the primary key) |
| `op` | `create`, `update`, `delete`, `undelete` or `restore` |
| `at`, `who` | When, and the username |
| `schema_position` | Which migrations the database had had: the last applied migration of each app, as JSON (`{"letters": "0002_addfield_letter_year", "pangloss_memgraph": "0001_initial"}`). Without it, nothing could be upgraded later; it cannot be added afterwards |
| `content_hash`, `content` | The version's content: the **complete write-form payload** (the validated `CreateDB` / `UpdateDB` shape: values, nested documents with their ids, references to entities by type and id), as JSON, compressed with zstd. Empty for `delete` / `undelete`, which change no content |
| `restored_from` | For `restore`: the version it was copied from |

**Only head nodes have versions.** An update replaces the tree under a head node (`:HeadNode {id: ...}`); nested
documents, embedded objects, reified relations, semantic spaces, conjunctions and edge properties cannot be updated
on their own, and nothing else refers to a nested document (only entities are referred to by id). One snapshot of
the head node's payload therefore holds all of them, and a nested document has no history of its own. **Entities are
their own head nodes**, each with its own history. (There are no "inline entities": see the note at the top of
[Entity](models.md#entity). A document's payload may *name* an entity by a UUID or URL, with `create_new`, so that
batches of data from other sources can be uploaded without creating each entity first. If the entity does not
exist, the same write creates it, as a separate head node, exactly as `Entity.Create(...).save()` would.) That
entity needs its own `create` record (version 1), or its history would begin with a gap. The document's snapshot
holds only the reference to it, which is all restoring needs, since an entity that exists is used as it is
(*checked:* `write_head_node` / `replace_head_node` find which of these entities exist already
(`find_existing_entities`) and build the query from that, so "created by this write" is known inside the write
function, and not after it. It has to be **returned** from the write (as `existing_head` is for updates) and put
in the event as `created_entities`.)

Decisions:

- **Snapshots, not diffs.** An update is already a complete document, so a snapshot is exactly what was written,
  and any version can be read alone. A diff would depend on the order of replay and on the structure of the
  document staying the same, which is what migrations change. **Differences are computed when asked for**, from
  two snapshots.
- **The post-image (what was written), not the pre-image.** The payload is already in hand, validated, when the
  write is made: no extra read. The first record is the creation.
- **Content-addressed.** Identical content (a restore, a revert, a re-save with no changes) is stored once.
- **The payload has what a restore needs** (*checked in the code, 2026-10-23*): the ids are made **before** the
  write, not by the query. `CreateDB` gives every node an `id` in a `before` validator (`ensure_id`, in
  `base_models.py`), and `UpdateDB` has `id` as a required field, so the client supplies the ids of nested nodes
  and the update query writes them as they are (`previous_meta` is looked up by node id, so a node that keeps its
  id keeps its `meta`). So the validated DB model, dumped, is a complete snapshot, with ids, and a restore is the
  ordinary update with it. Nested nodes **keep their ids across updates only if the client sends them back**;
  that is the client's concern, and history stores whatever was written.
- **Which model to dump:** the `CreateDB` / `UpdateDB` instance at the point of the write, after
  `_to_db_model()` (in `create_head_node` and `update_head_node`), not the client's `Create`/`Update`: it has the
  ids and the propagated context types. (For a `Fulfils` write, the instance is the *fulfilled* class: dump it as
  it is, with its `type`.) A restore feeds the snapshot back through `Update` validation, which also catches a
  payload that no longer fits (the "upgrade" and "draft" sections).

## Where it is kept

**A `HistoryStore` interface, with SQLite as the default.** The interface is small (`append`, `versions(head_id)`,
`get(head_id, version)`, `latest_version(head_id)`, `purge(...)` later) so that others can use what they like.

Why not Memgraph: the memory is the lesser reason. Historic nodes would have to be excluded from every query, would
swell the indexes and the label text index, and would slow reads. History is cold, append-mostly data.

Why SQLite: no extra server, one file, transactional, enough for a single `pangloss run`. Run on a backed-up
server, it is backed up with it; a project with several server processes can write a store for Postgres or
object storage.

SQLite settings: WAL mode, `synchronous=NORMAL` (best effort; durability is not worth a flush per write). One table,
`history`, as above, with an index on `(at)` and on `(who)`; blobs in a second table keyed by `content_hash` if
deduplication is wanted.

## Recording (the write path)

After the Memgraph write has **committed**:

1. The writer (`write_head_node`, `replace_head_node`, delete, undelete in `exposed_functions.py`) builds the
   record: the version it made, the user, the time, the schema position, and the payload serialised to bytes.
   Serialising here (about 0.01 to 0.1 ms, *measured*) makes the snapshot immutable even if the caller changes
   the object afterwards.
2. The record is put on a **bounded in-memory queue**, and the write returns.
3. **One worker thread** owns the SQLite connection (SQLite has one writer anyway, and blocking calls stay off
   the event loop). It takes records in batches (up to 100, or whatever arrived in 50 ms), compresses them, and
   commits once per batch.
4. If the queue is full, the record is **dropped**, logged, and the gap is counted. If the process stops, what is
   in the queue is lost. A failing store never fails or slows the user's write.
5. On a clean shutdown the queue is drained, with a timeout.

The schema position is read when the server starts and again after a migration. (Writes are refused while a
migration runs, so there is a clean moment to do so.)

### Gaps

The graph keeps the version count (`PGUpdate` nodes plus one), so a gap is **detectable**: the history of a head
node whose latest recorded version is below the graph's has a gap. The listing says so ("versions 4 and 5 were not
recorded"), and nothing else is done about it. It is information, not an error.

### Hook, and where the code lives

**A separate package, `pangloss-history`, is possible and is the recommendation.** Nothing in history needs to be
inside `pangloss-models`: a snapshot is the write-form payload, which the writer already has; the store, the
queue, the endpoints and the commands are all additions. What it needs from the rest is **one small seam**, which is
in the code that writes, not in the models.

*Checked in the code (2026-10-23):*

- Writes go through four functions in the database module's `exposed_functions.py`: `create_head_node`,
  `update_head_node`, `soft_delete_node` (`delete_document`/`delete_entity`) and `undelete_node`. The models only
  *bind* them (`_bind_database_functions` in `model_registry.py` assigns `save`, `delete` and `undelete`). The
  `@write_transaction` functions (`write_head_node`, `replace_head_node`) run inside a transaction, and may be run
  again by `write_with_retries`, so a hook placed there would fire before the commit and perhaps twice. The
  right place is **in `create_head_node` / `update_head_node` / the delete and undelete wrappers, after the
  transaction has returned**.
- Apps are found by `INSTALLED_APPS`: the API includes `{app}.api.router`, the CLI loads `{app}.cli`, and models
  come from `{app}.models`. `pangloss-history` fits this with no change: `history.api` (endpoints),
  `history.cli` (commands), and a `history.models` only if it needs any. What is *missing* is a way for an app to
  react to a write.

So the seam is a **write event**, defined in `pangloss_models` (not in `pangloss_memgraph`, so a second backend
emits the same event and history works on it):

```python
@dataclass(frozen=True)
class WriteEvent:
    op: Literal["create", "update", "delete", "undelete"]
    model: type[Document | Entity]
    id: UUID
    version: int  # the version this write made; for delete and undelete, the version at the time
    user: str
    at: datetime
    payload: (
        _CreateDBBase | _UpdateDBBase | None
    )  # the validated write form; None for delete / undelete
    created_entities: tuple[
        _EntityCreateDBBase, ...
    ]  # entities this write made (see "What is stored")


after_write: list[Callable[[WriteEvent], None]]  # `pangloss_models.hooks`
```

The backend calls the listeners, after the commit, **synchronously and cheaply** (the listener only serialises
and puts the record on the queue, as under "Recording"); a listener that raises is logged and ignored, since
history is best effort and must not fail a write. `pangloss_history` registers its listener when it is imported
as an installed app. When it is not installed, the list is empty and the cost is nothing.

Why not the alternative of putting history in `pangloss-models`/`pangloss-memgraph` itself: it would make
SQLite, a worker thread and a growing set of endpoints part of the core for everyone, and tie the document
upgrader (phase 3) to the core's release. The one thing that does tie `pangloss-history` to another package is
phase 3: the structured migration operations live in `pangloss_memgraph.databases.memgraph.migrations` (with
their Cypher), so the document-upgrade functions either live in `pangloss-history` and depend on that, or the
operation *data* (not the Cypher) is split out of the memgraph package first. (*Resolved when phase 3 was built:* the
changes are plain data in `pangloss_models.migrations.changes`, with the snapshot replay in `...migrations.state`;
only the Cypher is in `pangloss_memgraph`. `pangloss-history` depends on `pangloss-models` alone.) That is a phase 3 decision and
does not affect phases 1 and 2.

Settings: `HISTORY_DB_PATH` (default `.pangloss/history.sqlite3`), `HISTORY_QUEUE_SIZE`, `HISTORY_BATCH_SIZE`,
`HISTORY_BATCH_MS`. Commands: `pangloss history <command>` (see "Reading").

### Cost (*measured*, laptop, synthetic documents)

| | |
|---|---|
| A `Create` or `Update` through Pangloss to a local Memgraph (small document) | 14 to 17 ms |
| Serialise and compress a 12 KB document (zstd; stored ≈ 3 KB) | ≈ 0.03 ms |
| Serialise and compress a 123 KB document (stored ≈ 25 KB) | ≈ 0.24 ms |
| SQLite insert and commit, WAL, `synchronous=NORMAL` | 0.015 to 0.06 ms |
| SQLite insert and commit, WAL, `synchronous=FULL` | ≈ 0.1 ms |
| The same, many inserts in one transaction | 0.001 to 0.06 ms each |

The request pays for the serialisation only. The SQLite numbers are optimistic for `FULL`, because macOS does not
flush to disk on `fsync`; on a Linux server, expect 1 to 10 ms per commit, which is why records are batched and
written off the request path. Storage: a few KB per version; a million versions is gigabytes at most.

## Reading

Under each model that has history:

| Endpoint | |
|---|---|
| `GET /api/<Model>/{id}/history` | The versions: version, op, who, when, schema position, and any gaps |
| `GET /api/<Model>/{id}/history/{v}` | Version *v*, **upgraded to the current models** (below), as a read view |
| `GET /api/<Model>/{id}/history/{v}/diff?to={w}` | The differences between two versions (computed from the snapshots; `to` defaults to the current one) |
| `GET /api/<Model>/{id}/history/{v}/draft` | A restore as a draft to reconcile (see "Restore as a draft") |
| `POST /api/<Model>/{id}/history/{v}/restore` | Restore it; only if it can be done without anyone's decisions |

and `pangloss history show|diff|restore <model> <id> <version>` on the command line.

## Restoring

A restore **never rewrites history**: it writes the old content as a **new version** (`op = restore`,
`restored_from = v`), through the ordinary update, with `expected_version` so that a stale page cannot overwrite a
newer change.

Rules:

- **Scope is one head node.** Its nested documents come with it. The entities it refers to are **references**,
  so a restored document refers to those entities as they are now, not as they were.
- **Incoming relations are not touched.** They belong to other documents. Restoring an entity restores its own
  values and its own outgoing relations.
- **Entities that were deleted since are undeleted** (`PGUndeletion` records), in the same transaction, since an
  older version may refer to them. An entity that cannot be found at all (see "Interactions") is a problem to
  resolve (below), not a silent skip.
- **Unique values may have been taken** since (an entity's URL, a supplied id): that is a conflict, reported,
  and nothing is written.
- Deleted head node: restoring a *content* version of a deleted node undeletes it as well. (Undeleting without
  changing content is the existing undelete.)

## When the models have changed

A version is in the shape of the models **as they were**, which may not be the shape of the models now. The
snapshot carries its `schema_position`; the migrations applied since are known (the migration files, in order,
with squashes mapped to their originals). Two things follow.

### Upgrading a snapshot

A snapshot is **upgraded on read**, never rewritten (the original stays as it was, and an upgraded copy can be
cached). Each change in a migration gets a pure function that applies it to a **document** in the same way as the
Cypher operation applies it to the database:

| Change | On a stored document |
|---|---|
| `AddField` | put the migration's default (the answer given at `makemigrations`) |
| `RemoveField` | drop the value, **and record that it was dropped** (the original is still in history) |
| `RenameField`, `RenameModel` | rename the key, or the `type` |
| Type change | convert; where it cannot be (the migration's `on_failure`), leave the value and report it |
| `AddModel`, `RemoveModel` | a removed model cannot be upgraded: reported |
| Enum and `Fulfils` changes | enum values mapped; labels are not stored in the payload |

This is real work: a function per change (the changes are structured data, so each has a clear meaning), tested the
way `test_migration_batch_equivalence.py` tests batches: the same data through the Cypher operation and through the
document function must come to the same thing.

**Hand-written migrations** (`RunCypher`, `RunPython`) cannot be run on a stored document. A version older than
one is **not automatically restorable**: the structural changes around it are still applied, and the result is
marked "a hand-written migration, `<name>`, is between this version and now". (A later option is an optional
document-transform hook on `RunPython`.) The `makemigrations --empty` template should say so.

### Restore as a draft: reconcile in the frontend

When a version **cannot be restored cleanly**, it is not refused outright. Everything that can be reconciled with
the current models is, and what cannot is handed to the person, in the interface, to decide.

`GET .../history/{v}/draft` returns:

```json
{
  "fromVersion": 3,
  "schemaPosition": {"letters": "0001_initial"},
  "draft": { "...": "an Update-shaped document, upgraded as far as it can be; may be incomplete or invalid" },
  "problems": [
    {"path": "year", "kind": "missing-required", "message": "Letter.year was added after this version; no value"},
    {"path": "nickname", "kind": "removed-field", "oldValue": "Ada", "message": "Person.nickname no longer exists"},
    {"path": "born", "kind": "type-changed", "oldValue": "unknown", "message": "was str, is int; could not convert"},
    {"path": "sentTo", "kind": "reference-missing", "oldValue": {"type": "Person", "id": "..."}, "message": "…"},
    {"kind": "hand-written-migration", "migration": "letters.0004_move_dates", "message": "…"}
  ]
}
```

`kind` is one of: `missing-required` (a field added since, with nothing to put), `removed-field` (the value is
kept for reference), `type-changed` (the old value could not be converted), `model-removed` (there is no draft:
only the raw old content, read-only), `reference-missing` (an entity that cannot be found), `unique-conflict`,
`hand-written-migration` (structure after it may not mean what it did), `validation` (anything else the current
`Update` model rejects).

The frontend (using the exported model definitions, which it already has) shows the **edit form** filled with
the draft; fields with a problem are marked, and a **panel of old values** beside them lets the person copy an
old value into a field, drop it, or type something else. Saving is an ordinary update (so an ordinary new
version, with `expected_version`). `POST .../restore` is the same operation without a person: it succeeds only if
`problems` is empty, and otherwise answers `409` with the draft and the problems, so a script gets the same
information.

This turns "cannot restore" into "restore with help", and it needs nothing the interface does not already need
(an edit form that can show a value and a problem for a field, and a reference to an old value).

### Squashing and cleaning

A squashed migration is one unit, so a snapshot taken **part way through** the squashed range cannot be upgraded
once the originals are gone. This is the same rule as for a database part way through a squash. `cleanmigrations`
should **warn** (and, if the history store is reachable, say how many versions are inside the range) before
deleting. It does not refuse: history is best effort.

## Interactions

- **`pangloss restore` (a Memgraph snapshot)** puts the graph back to an earlier moment. The history store may
  then be **ahead** of the graph. The extra versions are kept and marked as a branch ("recorded after the
  database was restored"); nothing is deleted or reconciled.
- **"Remove deleted nodes for good"** ([TODO.md](../TODO.md), Data and the Memgraph backend) would break
  restoring, since a snapshot may refer to an entity that has been removed. Rule: a purge does not remove a node
  that a retained version still refers to, or it removes the references from history first (a `reference-missing`
  problem is the fallback).
- **`keep=True`** (the migration spec's way of saving what a lossy change removes) is largely answered by history:
  the removed values are in the earlier snapshots. Decide whether to build `keep` at all once history exists.
- **Migrations and history** are otherwise independent: migrating does not write history (that would touch every
  document); the snapshot's `schema_position` is what links them.

## Erasure

Not decided, and **not designed out**. History keeps what a document held before a correction, so "delete this"
(a flag today) does not remove it from history. A project that must honour a request to erase something has to be
able to remove versions. So: rows are individually deletable, there is **no hash chain** across versions (it would
make a purge break the rest), and a purge leaves a tombstone ("version 3 removed by X on date") so the gap is
explained. The policy, and a `pangloss history purge` command, wait until someone needs them.

## Testing

- Recording: a write makes a record with the right version, user, position and content; a failing store does not
  fail the write; a full queue drops and counts; a gap is reported; shutdown drains.
- Round trip: for every kind of model in the test models, a snapshot read back equals what was written; a
  restore of version *v* gives content equal to *v*, as a new version, and `expected_version` is honoured.
- Entities: restoring undeletes what the old version refers to; a missing entity and a unique conflict are
  problems, with nothing written.
- Upgrading: each change type, with the document function checked against the Cypher operation on the same data
  (the equivalence-test pattern); hand-written migrations are marked; a removed model gives no draft.
- Draft: each `kind` of problem is produced by a constructed history; the draft, once its problems are fixed, saves.
- Squash: a snapshot inside a squashed range, and the `cleanmigrations` warning.

## Phases

0. **The seam (in the core). Done (2026-10-23):** `pangloss_models/hooks.py`; `announce` in
   `exposed_functions.py`; `packages/pangloss-memgraph/tests/test_write_events.py`. `WriteEvent` and `after_write` in `pangloss_models`; the four write wrappers
   in `pangloss_memgraph` emit it after the commit; the write functions return the entities they created. A test
   with a listener, and with a listener that raises. Small, and useful on its own.
1. **Record and read. Done (2026-10-23), see "As built".** `pangloss-history` with the SQLite store, the hook, the queue and worker, the listing, the
   single version and the diff, and `pangloss history show|diff`. Read-only; immediately useful; no migration
   interplay. Includes recording the schema position, which cannot be added later.
2. **Restore at the same schema position. Done (2026-10-23), see "As built (phase 2)".** The restore as a new version, the entity undeletion, the conflict
   checks, and `POST .../restore`.
3. **The document interpreter and the draft. Done (2026-10-23), see "As built (phase 3)".** The function per change, the equivalence tests, the `problems`
   list, `GET .../draft`, and the interface's form for it.
4. **Interactions. Done (2026-10-23), see "As built (phase 4)".** The `cleanmigrations` warning, the purge rule, and deciding about `keep=True`.

## Decisions

Settled by checking the code (2026-10-23):

- **A separate package, `pangloss-history`**, optional, in `INSTALLED_APPS`, with one seam in the core: a
  `WriteEvent` and an `after_write` list in `pangloss_models` (see "Hook"). Called after the commit, from
  `create_head_node`, `update_head_node`, and the delete and undelete wrappers.
- **The payload is complete** (ids are made before the write); dump the `CreateDB` / `UpdateDB` instance.
- **Entities created by a document's write** get their own `create` record; the document's snapshot holds only the
  reference. The write function must return which entities it created.

Still to decide. Each has a recommendation; none blocks phase 1 except the first two, which are about the record.

1. **Do delete and undelete get a version number?** Today only updates make a version (`PGUpdate` count + 1).
   *Recommend:* a record per operation, keyed by `(head_id, seq)` with `seq` counting records of that head, and
   `version` the head node's version *at the time* (unchanged by a delete). This keeps the "gap" check simple
   (compare the highest recorded `version`) and lets the listing show "deleted by X".
2. **What the record keeps for the graph's own `meta`** (created_by, created_when): nothing; it is derived from
   the first record. *Recommend:* leave it out.
3. **Where the schema position comes from.** The server already checks at start-up that the database matches the
   migrations (`MIGRATION_CHECK`), and a migration run while the server is up is already unsupported for writes.
   *Decided:* the last migration of each app **in the migration files**, read once (not from the database, so no
   async read in a synchronous listener). It is right whenever the start-up check passed; with `MIGRATION_CHECK = "off"`
   it is only as right as the project.
4. **Per-model opt-out.** *Recommend:* on by default; `HISTORY_EXCLUDE = ["ModelName", ...]` in the settings, and
   a `_meta` slot later if [meta slots](meta-slots.md) are built.
5. **Large documents.** *Recommend:* no limit at first (zstd gives ≈ 5:1; the cost table above), count sizes in
   the listing, and revisit when there is a document that is a problem.
6. **Who may read history.** It is the old content, so as sensitive as the document was. Access control is open in
   [TODO.md](../TODO.md); *recommend:* history endpoints need a logged-in user for now, and use whatever the
   decision there is for reading the model itself.
7. **Erasure policy** (above): wait until needed; rows individually deletable, no hash chain.

## As built (phase 1)

`packages/pangloss-history`, in `INSTALLED_APPS` as `"pangloss_history"`. Its `models` module (imported as the
server and commands start) registers the listener; it has no models of its own.

| | |
|---|---|
| `store.py` | `HistoryRecord`, the `HistoryStore` protocol, and `SqliteStore` (WAL, `synchronous=NORMAL`, a `history` table keyed `(head_id, seq)` and a `blobs` table by content hash, zstd). A short-lived connection for each operation, so any thread may use it |
| `recorder.py` | The bounded queue and the one worker thread (started on first use, daemon, drained at exit). A full queue drops and counts; a failing store is counted and logged |
| `listener.py` | `on_write`: serialises the payload at once (`model_dump_json`), adds a `create` record for each entity the write made, and puts the records on the queue. `HISTORY_EXCLUDE` skips models |
| `schema_position.py` | `{app: last migration}`, from the migration files |
| `diff.py`, `gaps.py` | The structural diff (nested objects with an `id` are compared by id, other lists by place); the versions with no record |
| `api.py` | `GET /api/{Model}/{id}/history`, `.../history/{v}`, `.../history/{v}/diff?to=` (logged-in users). Not yet upgraded to the current models (phase 3), and no `draft` or `restore` |
| `cli.py` | `pangloss history list <id>`, `show <id> <version>`, `diff <id> <version> [--to N]` (these read only the store: they need no database) |

Known limits, on purpose: the endpoints take an **id** (an entity at a URL is not looked up); the `missing` list
needs the node to be in the graph (a deleted node shows its history with `currentVersion: null`); there is no
`pangloss history purge`; the `model` of a record is the class that was written (a `Fulfils` write is recorded as
the class it was written as).

Tests: `packages/pangloss-history/tests` (store, recorder, listener, diff and gaps, API, CLI, schema position) and
`pangloss-memgraph/tests/test_history_records.py` (real writes to Memgraph).

## As built (phase 2)

`restore.py` in `pangloss-history`; `POST /api/{Model}/{id}/history/{v}/restore` (needs `If-Match`, as an update
does; answers `{id, version, restoredFrom}` and an `ETag`); `pangloss history restore <Model> <id> <version> --user NAME
[--expected-version N]` (connects to the database itself; the user is required, since the new version has an author).

In order, and nothing is written until the checks have passed:

1. the version must be recorded for this model, **at the schema position the database is at now**, or `409` with the
   problem `schema-changed` (an older one needs the upgrade of phase 3);
2. its content must still validate as the model's `Update` (else `validation`);
3. the entities it refers to must exist: any deleted since are **undeleted**; one that is gone is `reference-missing`;
4. a deleted head node is undeleted;
5. the update is made with `expected_version` (the `If-Match`, or the version just read for `*`), and told to
   listeners with `restored_from`, which the listener records as `op = restore`.

Errors are `PanglossRestoreError` (a `PanglossConflictError`, so `409`, with `problems` of `{kind, message}`), a
stale version is the usual `412`, and a taken URL or id is the usual conflict from the update.

Differences from the design above, all deliberate:

- The undeletions of step 3 and 4 are **separate transactions from the update**, not one. They write no content and
  are harmless if the update then fails (a later restore finds them already done). One transaction would have needed a
  restore written inside the database module.
- The schema position is compared **exactly**: any migration between then and now blocks a restore, even one that
  would change nothing in this model, until phase 3 can say that.
- A restore through the API names the version only; there is no `draft` yet.
- `restored_from` is carried by the event (`WriteEvent.restored_from`) and by `update_head_node(..., restored_from=)`,
  which exists only for listeners.

Tests: `pangloss-memgraph/tests/test_history_restore.py` (against Memgraph: new version and content; stale version
refused and nothing written; deleted document; entity deleted since, and one that is gone; a URL taken since; an
entity; unrecorded version, wrong model, changed schema position) and, in `pangloss-history/tests`, the route and the
command.

## As built (phase 3)

`upgrade.py` and `draft.py` in `pangloss-history`.

**The upgrade.** `upgrade(data, position, apps)` finds the migrations after the version's `schema_position`
(`migrations_after`: those not at or before the position of each app, in the order of the migration graph, with the
snapshot of the models as they were at the position, from `states_around`), and applies each change in turn to a
copy of the document (`apply_migrations`), keeping the snapshot up to date change by change, so that a field or a
parent class means what it did at that point. A node gets a change to model `M` if `M` is in the `labels` of its
type (so parents and traits count). An entity that the document refers to is a reference, not part of it, and is
not walked.

| Change | On the document |
|---|---|
| `AddField` | the migration's default; `[]` for a list; `None` for a nullable field; else the problem `missing-required` |
| `RemoveField` | dropped; the problem `removed-field` with the old value (**not blocking**: it is in history) |
| `RenameField`, `RenameModel` | the key; the `type` of the node, and of every reference to the model |
| `AlterLiteralType`, `AlterListItemType` | converted as `conversion.py` converts it in Cypher (`on_failure` `null` / `default`); otherwise `type-changed` |
| `AlterNullability` (to not null) | the migration's default, else `missing-required` |
| `AlterEnumMemberValue`, `RemoveEnumMember` | values mapped (the replacement, else `type-changed`) |
| `AlterRelationTarget` (narrowing), `AlterCardinality` | `reference-not-allowed` (or removed, with `on_narrowing = "remove"`); a list made single keeps the first (`keep = "first"`), else `cardinality-changed` |
| `DeleteModel` | `model-removed` |
| `RunCypher`, `RunPython` | `hand-written-migration`: the structure around it is still upgraded |
| Enum creation, renames, model labels and options, indexes, constraints, reverse names, parent fields, `RecomputeFulfils`, `StateOnly` | nothing: not in the stored document, or worked out again on write |
| Everything else (wrapping and unwrapping relations, annotated values, embedded objects and literals into each other, edge models) | `unsupported-change`: **not applied yet** |

Each `Problem` is `{kind, message, path?, oldValue?, migration?, blocking}`. The equivalence tests
(`pangloss-memgraph/tests/test_history_upgrade.py`) write data with the old models, then migrate the database with
the real operations and read it with the new models, **and** upgrade the stored version and validate it as the new
`Update`: they must agree. They cover add, remove, rename (field and model), type conversion (with each
`on_failure`), nullability, enum value changes and removal, and cardinality. The unit tests
(`test_history_upgrade_unit.py`) cover the rest of the table (positions, squashes, hand-written, problems).

**The draft.** `make_draft(record, model)` upgrades the version if its position is not the current one, and adds the
`validation` problems of the model's `Update` on the result. `GET .../history/{v}` now returns the upgraded content
by default (`?upgrade=false` for what was written), with `upgraded` and `problems`; `GET .../history/{v}/draft`
returns the document of "Restore as a draft" (`fromVersion`, `schemaPosition`, `draft`, `problems`).

**Restore** now upgrades first: it refuses (`409`) only if there is a *blocking* problem, and says which. A version
whose only problems are non-blocking (a removed field) is restored, and the values dropped are in the earlier
version. (This differs from the design above, where every problem blocked: a removed field blocking every restore
across it would make the restore of an old version impossible without the interface, and nothing is lost.)
`unknown-position` (the position is a migration that is gone, as part way through a squash) blocks and returns the
version as written.

Known limits:

- **The interface's form for a draft is not built** (it is the interface's phase, not this package's).
- **Enum values inside annotated values and edge properties** are not mapped (only those of literal and list
  fields); nor are those fields upgraded at all when annotated values change (`unsupported-change`).
- `RecomputeFulfils` is not applied: the labels of a restored node come from its content when written.
- A migration that **changes nothing for this model** still counts as "after" the version; it is applied (as nothing).
- Cases not in the table are reported, never guessed.

## As built (phase 4)

- **`pangloss cleanmigrations` warns.** `pangloss_history.cleanup` counts the recorded versions that were written
  part way through what a squashed migration replaces (their `schema_position` is an original other than the last;
  one at the last original is fine, since the squash stands for it). The command prints it in yellow before it asks to
  delete (`History: 3 recorded versions were written part way through what 0001_squashed_0003 replaces, and could
  not be upgraded or restored once the originals are gone`). It does not refuse. Nothing is said if
  `pangloss_history` is not installed or has no store yet. (`pangloss-cli` finds it by `INSTALLED_APPS`, with a soft
  import, so it does not depend on it.) `HistoryStore` has a new method, `position_counts()`, for this.
- **`keep=True` is not built, and will not be.** History keeps what a lossy change removes (the earlier versions have
  it, and `removed-field` problems carry the old value), and `migrate --backup` keeps the whole database. It is
  taken out of `docs/migrations.md`. (A lossy migration still loses it *from the graph*: history is best effort and
  starts when it is installed, so for data from before that, `--backup` is the way.)
- **Purge: the rule is recorded, nothing is built, because nothing removes deleted nodes yet** ([TODO.md](../TODO.md)).
  When something does, it must not remove a node that a **retained version still refers to**: before removing an
  entity, ask the history store for the versions that refer to it (a restore would then report `reference-missing`,
  which is the fallback and is already handled). `pangloss history purge` and the policy for erasure still wait for
  someone who needs them.

## Run against the demo project (2026-10-23)

`"pangloss_history"` was added to `INSTALLED_APPS` of `pangloss-demo`, and a real server was started
(`pangloss run`) against its Memgraph. Through the HTTP API and the command line:

- **Worked as designed:** create, update, delete, undelete and restore of an entity (`Person`) and of a nested
  document (`Factoid`, with statements, an `AtPage` relation and a source written inline); the listing, a version, the
  diff, the draft; `428` without `If-Match`; `401` without a login; `pangloss history list|show|diff|restore` (the
  restore from the command line is itself recorded, as the command imports the models and drains the queue on exit);
  the history file made at `.pangloss/history.sqlite3` of the project (now in the demo's `.gitignore`); the queue
  drained when the server is stopped; the source written inline in the factoid had its own `create` record.
- **Found, and fixed:** (1) the factoid's snapshot held the *whole* inline entity (its fields, `create_new`), so a diff
  between its creation and its update showed the entity's fields as removed. Now an entity written in a document is
  kept there as the reference to it (`{id, type, label: null}`, with `edge_properties` if it has them), and its own
  record has the content, as the design said. (2) A diff between a creation and an update showed `create_new`,
  `context_labels` and `db_labels`, which are only the bookkeeping of the write form: they are left out of a diff.
- **Not caused by history, found on the way:** the demo database had been filled before the change to store enums as
  plain values, so reading the old factoids and people fails (`mg_enum` values): the demo needs its data made again
  (`populate.py` on an empty database). And `pangloss_memgraph.0001_initial` was not recorded as applied, so the server
  refused to start until `pangloss migrate --fake` (as `demo-setup.md` says).
- **Not tried:** a schema change with real old versions in a running project (covered by the equivalence tests, not
  by hand), more than one user, a large document, and a server killed without a clean stop (the queue is then lost, by
  design).
