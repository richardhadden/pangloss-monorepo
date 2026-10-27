# Large data

What happens when Pangloss holds a lot of data: how long a load and a migration take, what to turn up, and what to look out for. The numbers are from a smoke test on 2026-10-26; the way to repeat it is at the end.

**What was measured.** The demo's models, with 100,000 entities (60,000 people, 15,000 groups, 20,000 places, 5,000 sources) and 30,000 factoids with 2 or 3 statements each (some wrapped in `Negative`, `Hypothetical` or `Causes`): 642,549 nodes and 1,649,526 edges. One local Memgraph (Docker, `memgraph/memgraph-mage`), on a laptop, and the history recorder on.

## Loading

Every `.save()` is one transaction. Written through the models, one process:

| Writers at once | Entities a second |
|---|---|
| 1 | 140 |
| 4 | 158 |
| 16 | 30 |

**Use four or fewer.** With 16 writers the throughput falls to a fifth, with Memgraph at several hundred per cent CPU. The whole load at four writers:

| | Time |
|---|---|
| 100,000 entities | 764 s (150 a second at the start, 119 at the end) |
| 30,000 factoids | 518 s (58 a second) |
| Total | 1,283 s (21 minutes) |

Throughput falls slowly as the database grows. A factoid is written, with its statements, in a single statement.

With 16 writers many `write_head_node` transactions take over 500 ms, and **`SLOW_QUERY_MS` (default 500) fills the log with warnings.** Raise it for the load ([Logging](logging.md)); `bulk-load` (below) does that itself.

### Why: the text index is paid for at every commit

It is not the user node, the unique constraints, or transactions conflicting. Raw Cypher against a Memgraph, 800 nodes created one transaction each:

| | 1 writer | 16 writers |
|---|---|---|
| A plain node | 1,553 a second | 3,803 |
| The same, with a unique constraint on its id | 1,498 | 3,834 |
| The same, in the text index (`label_text`, which every document and entity is in) | 208 | 20 |
| Writes of the models, 16 writers sharing one user, and 16 writers with 16 users | 174 | 31, and 27 |

The text index costs about 4.5 ms **a commit**, not a node, and it makes writers wait for one another. So writing more in one transaction is the way round it:

| Nodes created in one transaction (text-indexed) | Nodes a second |
|---|---|
| 1 | 221 |
| 10 | 1,167 |
| 100 | 10,685 |
| 1,000 | 62,044 |

Pangloss writes a document, with the documents and embedded objects inside it, as one transaction, and one document per `.save()`. A way to write many documents in one transaction (a batch) would be the way to load faster into a database that already has data, where `bulk-load` cannot be used; there is not one yet. (In Memgraph's analytical mode the text index costs nothing, at 1,588 a second against 1,504 for a plain node, which is part of why `bulk-load` is fast.)

## Migrating

Each change below ran against the full dataset, after a dry run, with `--backup`:

| Migration | Dry run | Whole run, with `--backup` and the read-back | Records read back |
|---|---|---|---|
| A: rename a field (15,000 nodes), change an enum value (11,100), add a required field with a default (55,035), add an optional field, remove a field (5,000) | 1 s | 34 min, reading one at a time | 105,035 |
| B: rename the model `Place` to `Location` (20,000 nodes relabelled) | 1.4 s | 1 min | 20,000 |
| C: wrap `Statement.places` in a new reified relation (78,640 nodes made, 330,000 edge operations) | 2 min 24 s | 14 min 28 s | 128,640 |

- **The change is quick, and the check afterwards is most of the time.** A's change ran in a few seconds (its dry run took one); the other 34 minutes were the check. After a migration that could have made data unreadable, `migrate` reads every record it could have affected, through the models (`--no-check` skips it; `--check-all` reads everything). **The three runs above read one record at a time.** The reading is now 16 at a time by default (`check-data --parallel N` to change it). Measured on the factoids alone, from one at a time to 64: 103, 208 (4), 312 (8), 410 (16), 455 (32) and 466 (64) a second. Over the whole database (208,640 records: factoids, statements and entities), `check-data` took 31 min 28 s one at a time and 18 min 49 s with 16: 1.7 times as fast, because the entities, which are small, gain less. For an unattended run, `--no-check` and then `pangloss check-data` later is the same work, with the choice of when. Each read over 500 ms is a warning (`SLOW_QUERY_MS`), and with 16 at once a lot of them are.
- **A migration is one transaction**, so it fails whole or not at all. Memgraph held the 330,000 edge operations of C in one without trouble (1.5 GiB of memory for the whole database).
- **Dry runs are cheap and exact.** `--dry-run` runs the changes in a transaction that is rolled back, and reports what Memgraph counted. It took as long as the real change (so 2 minutes for C). A removed property was counted as nothing when this was first measured, because Memgraph reports `REMOVE n.x` with no count, so removing `Source.author` from 5,000 nodes said "no change to the data". Properties are now taken away with `SET n.x = null`, which it does count, and a removal is reported as "properties set" (the number it took away).
- **The snapshot from `--backup` does not last.** Memgraph keeps three snapshots, taking one every 300 seconds, so the one `--backup` takes is gone in about 15 minutes. A migration whose check takes longer than that has no restore point by the end. `migrate` says so at the end if the database no longer lists the backup it took (`The backup ... is no longer there`). Copy the snapshot from the server, or raise `--storage-snapshot-retention-count` ([Migrations guide](../guide/migrations/04-safety.md)).
- **Nothing else may write while a migration runs.** The lock refuses other writers (`PanglossReadOnlyError`, "The database is being migrated"), which is right, but a loader running at the time stops with an error. `migrate --fake` also takes the lock.

## Repeating it

```bash
docker run -d --name pangloss-memgraph-smoke -p 7689:7687 memgraph/memgraph-mage
cp -R pangloss-demo /tmp/smoke && cd /tmp/smoke      # then set DB_URL to bolt://localhost:7689 in its settings
pangloss migrate
pangloss users create --username demo --email demo@example.org --password … --no-admin
PYTHONPATH=. python bulk_load.py 100000 30000 4      # entities, factoids, writers
```

`bulk_load.py` is in `pangloss-demo/`. It writes with fixed URLs, so it is not for running twice, and **it must not be pointed at a database you want to keep.** Clearing the scratch database between tries: `MATCH (n) WHERE NOT n:PGUser AND NOT n:PGMigration DETACH DELETE n` (without that `WHERE`, the record of the migrations goes with it, and the next `migrate` starts again).

Then change the models, `pangloss makemigrations`, and `pangloss migrate --dry-run`, `migrate --backup`. To try [`bulk-load`](#bulk-load-a-file-into-an-empty-database) instead of the script, make a JSON Lines file of the same data (entities with ids of their own, then the factoids) and clear the database first.

## Bulk load a file into an empty database

For the **first load of a database that has nothing else in it**, Memgraph's analytical storage mode is much faster. It drops transactions (no versions, no conflicts, no rollback), so it is for a load you can repeat, and not for anything running alongside. Memgraph's own account of what it gives up is in [its documentation](https://memgraph.com/docs/fundamentals/storage-memory-usage). `pangloss memgraph bulk-load` does the load, and makes it safe.

### The command

```bash
pangloss migrate                                   # indexes, constraints: as usual
pangloss users create --username loader ...        # what is written is written by a user
pangloss memgraph bulk-load data.jsonl --user loader [--concurrency 4] [--validate-only]
```

`data.jsonl` is [JSON Lines](https://jsonlines.org/): a record a line, each a JSON object with the `type` of a model and the fields of that model's `Create`, as in a request to the API:

```json
{"type": "Person", "id": "https://example.org/person/1", "create_new": true, "label": "Ann"}
{"type": "Factoid", "label": "...", "year": 800, "source": {"type": "AtPage", "page": "1", "target": [{"type": "Source", "id": "https://example.org/source/1"}]}, "statements": [...]}
```

- **What a record refers to must be earlier in the file**, and be written by an `id` the file gives it, so the entities that records refer to need `_meta = Entity.Meta(create_with_id=True)` (an entity with no id of its own gets one from the database, which a file cannot know). Documents nested in a document go inside it, as in the API.
- **Records are written in file order.** Those that follow each other with the same `type` are written `--concurrency` at a time (4 by default); the next type begins when they have all finished. So entities, then documents, is the order. A type whose records refer to each other has to be written one at a time: `--concurrency 1`.
- **The file is checked first, all of it**, as `Create` would (`--validate-only` does only that): a record that is not valid is reported by its line before the database is touched. A record that cannot be *written* (it refers to an entity that is not there, or repeats an id) stops the load at that line; what came before it stays written, and the database is put back as below.

### What it does

1. Refuses unless the database is **empty**: nothing but users and the record of migrations (`pangloss migrate` first).
2. Takes the **migration lock**: `migrate` and the API cannot write until it is done (the load's own writes are let through).
3. **Drops the unique constraints**, which Memgraph will not allow in analytical mode (Pangloss has twelve: ids, URLs, users, tokens, the migration record). Their definitions are kept on the lock.
4. Switches to `IN_MEMORY_ANALYTICAL`, and writes the records.
5. However that went: switches back to `IN_MEMORY_TRANSACTIONAL`, **makes the constraints again**, makes the text index again, and releases the lock.

During the load the "slow transaction" warnings are raised to 10 seconds (`SLOW_QUERY_MS` is for the usual running), because with several writers most writes are over 500 ms. If `pangloss_history` is installed, it records each record written, as it does any write (250 records gave 250 history entries).

With the constraints gone nothing stops a duplicate id or URL during the load; making them again is the check. If the file had one, the command says which constraint failed, and **the database stays read-only** (the lock is kept) until the duplicate is removed and `pangloss memgraph bulk-recover` is run. `bulk-recover` is also what to run after a load that was killed (the lock has what is needed to put everything back).

From code: `async with pangloss_memgraph.databases.memgraph.bulk.bulk_ingest(): ...` around any writes made with the models, and `pangloss_models.bulk_upload.upload(records)` for the file.

### How fast

The same data (100,000 entities and 30,000 factoids), on the same laptop:

| | Time |
|---|---|
| Written as usual (`.save()`, four writers, transactional) | 1,283 s |
| The same, in analytical mode (a script of my own, four writers) | 463 s (2.8 times as fast) |
| `bulk-load`, four writers | 210 s of writing; 3 min 32 s with checking the file, the switches and the constraints |
| `bulk-load`, sixteen writers | 173 s of writing; 2 min 57 s altogether |

(The `bulk-load` figures are for a file of the same shape, but with the groups and places given ids, which makes 35,000 more `PGUrl` nodes: 678,472 nodes and 1,688,226 edges, against 642,549 and 1,649,526.) After it, the database was in the usual mode with all twelve constraints and no lock, and `check-data` read a sample of 3,000 of each model. Four and sixteen writers gave the identical database, so nothing was lost to a race. Sixteen is not much faster than four because the loader, one Python process, is then the limit.

How writers at once behave, 600 people each, by hand:

| Writers | Transactional | Analytical |
|---|---|---|
| 1 | 140 a second | 430 |
| 4 | 158 | 860 |
| 16 | 30 | 860 |

With no transactions there is nothing to conflict, so the slowdown with many writers goes.

### What it costs

- **No rollback.** A write that fails part way can leave half a document, and another connection sees writes before they are done. Nothing else may use the database, and **never `migrate` in this mode** (`--dry-run` depends on rolling back, and would change the data). The command holds the lock so that Pangloss does not; a bare Memgraph client still could.
- **Nothing is written to disk** in analytical mode (no write-ahead log, no periodic snapshots). A crash during the load loses it; load again. Switching back writes a snapshot.
- **Only an empty database.** There is no "add to what is there" mode: the constraints that would catch a clash with what is there are the ones that are dropped.
- **A file cannot refer to an entity it did not give an id.** See above. Entities whose models have no `create_with_id` cannot be referred to by a file.
- **The loader is one process.** Beyond four or so writers it is the limit, not the database.

**A trap, if you do it by hand:** from Memgraph 3, `SHOW STORAGE INFO` shows only the mode the server *started* in, and says `IN_MEMORY_TRANSACTIONAL` after the switch has worked. Ask `SHOW STORAGE INFO ON CURRENT DATABASE` and read `storage_mode`.

**Not done:** loading through the API or the SDK (this works on the database directly, with the models, in the process that runs it), a way to add to a database that has data, and a bulk *migration* in analytical mode (it would give up the transaction that makes a migration safe).
