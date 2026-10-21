# History: tracking changes and restoring earlier versions ⏳

**Status: a design, not built.** Nothing here exists yet. Numbers marked *measured* come from a throwaway
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
(*to check:* what the write payload holds for such an entity, and where the "was it created by this write?"
information is known).

Decisions:

- **Snapshots, not diffs.** An update is already a complete document, so a snapshot is exactly what was written,
  and any version can be read alone. A diff would depend on the order of replay and on the structure of the
  document staying the same, which is what migrations change. **Differences are computed when asked for**, from
  two snapshots.
- **The post-image (what was written), not the pre-image.** The payload is already in hand, validated, when the
  write is made: no extra read. The first record is the creation.
- **Content-addressed.** Identical content (a restore, a revert, a re-save with no changes) is stored once.
- *To check:* that the payload has everything a restore needs, in particular the **ids given to nested nodes
  during the write** (whether they are made before or by the query), and whether nested nodes keep their ids
  across updates. If the query makes them, the payload has to be completed after the write, or the ids kept out of
  what restoring needs.

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

An optional package, `pangloss-history`, added to `INSTALLED_APPS` like `pangloss_interface`:

- registers a function to be called after each committed write (a small `after_write` hook list in the database
  layer; the package is a no-op when not installed);
- adds `pangloss history <command>` (see below) and the endpoints under each model;
- settings: `HISTORY_DB_PATH` (default `.pangloss/history.sqlite3`), `HISTORY_QUEUE_SIZE`,
  `HISTORY_BATCH_SIZE`, `HISTORY_BATCH_MS`.

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

1. **Record and read.** `pangloss-history` with the SQLite store, the hook, the queue and worker, the listing, the
   single version and the diff, and `pangloss history show|diff`. Read-only; immediately useful; no migration
   interplay. Includes recording the schema position, which cannot be added later.
2. **Restore at the same schema position.** The restore as a new version, the entity undeletion, the conflict
   checks, and `POST .../restore`.
3. **The document interpreter and the draft.** The function per change, the equivalence tests, the `problems`
   list, `GET .../draft`, and the interface's form for it.
4. **Interactions.** The `cleanmigrations` warning, the purge rule, and deciding about `keep=True`.

## Open questions

- **Entities created by a document's write** (named by UUID or URL, with `create_new`): are they recorded as their own `create`, and held in the document's snapshot as references only? (*to check*)
- **The payload:** does it contain everything a restore needs (ids of nested nodes)? Do nested nodes keep ids
  across updates? (*to check*, in `build_attached_nodes` and the `Update` path.)
- **The hook:** one `after_write` list in `pangloss_memgraph`, or in `pangloss_models` so a second backend gets it?
- **Where the schema position comes from at write time** when the server and `migrate` are different processes
  (read at start and after a migration, or each time with a short cache).
- **Per-model opt-out:** some models (high-volume, or not worth keeping) might not want history; a flag in `_meta`
  or in the history package's own config (see [meta slots](meta-slots.md)).
- **Which operations count as versions:** a delete and an undelete change no content; are they versions of the
  head node? (They are in the `PGUpdate` count today only for updates.)
- **Storage of very large documents**: a size limit, or storing only a hash and keeping the body out.
- **Erasure policy** (above), and whether history is exposed to every reader or only to some (it is the old
  content of documents, so it is as sensitive as they were at the time).
