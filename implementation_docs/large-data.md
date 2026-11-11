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

Throughput falls slowly as the database grows. A factoid is written, with its statements, in one transaction of a few statements (three, usually: see [Writing a large document](#writing-a-large-document)).

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

**Memgraph 3.14's `--experimental-enabled=commit-lock-narrowing` removes the waiting** (measured 2026-10-28, same raw Cypher: 16 writers, one text-indexed node a commit, 22 a second without and 244 with; 16 writers writing 100 nodes a commit, 936 and 12,074; one to four writers unchanged). The load of this page at **16 writers with it** took 989 s (100,000 entities in 583 s, 150 to 220 a second, and 30,000 factoids in 406 s, 74 a second) against 1,283 s at four writers without it, and the 16-writer load without it, which fell to 30 entities a second. The same data (642,550 nodes, 1,649,526 edges). It is experimental, so it is a choice for the project; `docker run ... memgraph/memgraph-mage:3.14.0 --experimental-enabled=commit-lock-narrowing`. Only the load was tried with it, not the API or the migrations.

Pangloss writes a document, with the documents and embedded objects inside it, as one transaction, and one document per `.save()`. A way to write many documents in one transaction (a batch) would be the way to load faster into a database that already has data, where `bulk-load` cannot be used; there is not one yet. (In Memgraph's analytical mode the text index costs nothing, at 1,588 a second against 1,504 for a plain node, which is part of why `bulk-load` is fast.)

### Writing a large document

A document can be large in itself: a register page with an entry for each line, a charter with a hundred statements. Until
2026-11-06 a write was **one Cypher statement with a clause for every node and edge**, and the database's time for such a
statement grows much faster than its length (about the cube: parsing and planning, not the writing). Found by the smoke test of
2026-11-06 (`pangloss-smoketest/`, 337,000 nodes), where a factoid of 200 statements took 134 seconds to write and an update that
dropped 50 of them 59; on Neo4j 160 statements took 50 seconds, and one try in three ended in an error inside the database.

A write is now **a few statements, each over a list of rows** (`pangloss_cypher.render_write`): the head; one `MERGE` over the nodes
of the document, their labels a list in each row; the new entities and their URLs, if there are any; and one statement over the edges,
with a part for each pair of edge names the write has (the type of an edge cannot come from a row). Three statements for an ordinary
document, and their texts do not depend on its size. Measured on the same database, through the API, one writer:

| One factoid of | Before | Now |
|---|---|---|
| 10 statements (deaths) | 58 ms | 47 ms |
| 40 | 527 ms | 75 ms |
| 80 | 3,681 ms | 152 ms |
| 200 (mixed kinds) | 134,537 ms | 289 ms |
| 200, then an update dropping 50 | 59,000 ms | 276 ms |
| 1,000 | not tried | 1,100 to 1,500 ms |

An ordinary factoid (5 statements or so) is as before: 23 to 24 ms each one at a time, 58 to 62 a second with eight writers (53 a
second before). In the database alone (the write's statements, rolled back): Memgraph 90 ms for 200 statements and 392 ms for 1,000;
Neo4j 51 ms for 160 and 416 ms for 1,000. A statement for each set of labels and each pair of edge names (17 for an ordinary factoid)
was tried first and given up: as fast for the large documents, but a round trip each.

The time left for a very large document is no longer the database's: of the 1.4 seconds for 1,000 statements, about 0.5 is validating
the payload and making the models, and reading it back takes a second (`smoke_scripts/write_phases.py`, `large_update.py`).

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

## Reading an entity that thousands of documents refer to

An entity's `HeadView` has everything that refers to it, in its incoming fields. Measured 2026-11-06 on the smoke
test's database (337,000 nodes), for a person that 3,927 statements refer to, in 83 fields:

| | Before | Now |
|---|---|---|
| `GET /api/Person/{id}` (whole: 1.86 MB) | 0.8 to 1.3 s | 0.6 to 0.8 s |
| `GET /api/Person/{id}?incoming_limit=25` (0.99 MB) | - | 0.32 s |
| `GET /api/Person/{id}?incoming_limit=10` (0.42 MB) | - | 0.19 s |
| `GET /api/Person/{id}/incoming/{field}`, a page of 50 | - | 0.06 s |
| The item's page in the interface (dev build) | 5.2 s, 29,507 elements, 105,716 px tall | 2.4 s, 16,045 elements, 61,050 px (with 25 of each field) |

Where the time went (`pangloss-smoketest/smoke_scripts/read_phases.py`): finding the 6,799 reverse edges and the
documents above them took 14 ms; reading the properties of every node on the way 480 ms; who made and last changed
each 160 ms. And 2,863 of the rows were read only to be dropped in Python (a relation that a subclass narrows is
stored under both names, and shown under one). So `build_fetch_incoming_query` now works out the field of each row
in the query, keeps only what the models show (`read_incoming.shown_relations`, passed as a parameter), sorts by the
label of what refers, counts each field, and cuts each field **before** it reads any properties.

- `Entity.get` still gives everything (now in label order, and faster). An API client that wants it all gets it.
- `storage.operations.get_entity_with_some(cls, id, limit)` and `get_incoming(cls, id, field, skip, limit)` are what
  the two routes use. They are for the API, as `check_deletable` is: not bound to the models, and not in the SDK.
- The interface reads an entity's page with 25 of each field (`INCOMING_SHOWN`); a row that has more ends in
  "and N more", which reads the next hundred. With 10 of each the same page was 1.25 s and 7,339 elements: the
  number is a constant in `interface-core/src/api/fetch.ts`.
- A module's view of what refers to an entity (by date, of `pangloss-dates`) has what the page has read. It says how
  many it is without, and **Read them all** reads them (78 requests and 5.3 s for the person above, and then the
  47,000 elements that view always was for it): on request, no longer on every visit.

**Read apart, and rendered as it comes on show (2026-11-07).** The page of that person was still 4.4 MB of HTML and
took 2 s to hydrate (2,280 chips), and sorting it by date, or reading it all, locked the browser for 2 to 5 s: the sort
itself is milliseconds, the DOM is the cost. Now:

- The item's page reads the item alone (`?incoming_limit=0&extras=false`, 65 kB), and what refers to it is read by
  `IncomingRelations` (`GET /api/Person/{id}/incoming?limit=25`, `get_incoming_fields`), and what is derived about it
  by the Derived section (`GET /api/derived/about/Person/{id}`), each in a boundary of its own, in a `Reveal` that
  shows them in page order (a section never appears first and is then pushed down): the server streams them after the
  item, the browser shows the item at once (the heading at 0.05 s where it was at 2.7 s) with a spinner where the rows
  will be.
- From 200 references on (`INCOMING_VIRTUAL_FROM`), and from 200 lines on sorted by date (`BY_DATE_VIRTUAL_FROM`), only
  the rows on show are rendered (`VirtualRows`, the list page's virtualizer): 238 chips in the page instead of 2,280.
- Measured in a headless Chromium, before and after, on the development server: hydration's blocking task 2.0 s to
  0.65 s; "Sort by date" 2.3 s to 0.5 s; "Read them all" (78 requests, then 3,505 lines) 5.5 s to 1.5 s; back by
  field (83 rows of up to 134 chips, of which some fifteen are rendered) 3.9 s to 1.4 s. On the production build
  after: hydration 0.07 s, "Sort by date" 0.1 s, "Read them all" 1.2 s (the requests), back by field 0.16 s; the
  heading is on show at 0.07 s. The HTML is 1.85 MB still: the answer of `/incoming` is in it as the data the browser
  starts from, so that the rows it renders are hydrated, not made again.
- `incoming_limit=0` is the only way to read an entity without what refers to it (`incomingCounts: null` says so, as
  against read whole, no key, or cut, the counts). `Entity.get` and the SDK are unchanged.

## Searching

Structured searches ([Structured search](structured-search.md#step-5-measured)) on the same data: every search tried takes under 600 ms with the indexes Pangloss makes, `$mentions` (a reference anywhere in a document) the longest. A label index for the class searched makes a search of a class three times faster, and an index on a property 100 times faster for an equality; edge indexes make no difference. `search_benchmark.py` in `pangloss-demo/` repeats the measurements.

## Repeating it

```bash
docker run -d --name pangloss-memgraph-smoke -p 7689:7687 -e MEMGRAPH_USER=test -e MEMGRAPH_PASSWORD=test memgraph/memgraph-mage:3.14.0 --experimental-enabled=commit-lock-narrowing
cp -R pangloss-demo /tmp/smoke && cd /tmp/smoke      # then set DB_URL to bolt://localhost:7689 in its settings
pangloss migrate
pangloss users create --username demo --email demo@example.org --password … --no-admin
PYTHONPATH=. python bulk_load.py 100000 30000 4      # entities, factoids, writers
```

If the container is started again (or Docker Desktop restarted), Memgraph warns `vm.max_map_count 262144 is too low`. Not measured, but with this much data it may matter: raise it in Docker Desktop's VM before starting the container (lost when Docker Desktop restarts):

```bash
docker run --rm --privileged --pid=host alpine nsenter -t 1 -m -u -n -i sysctl -w vm.max_map_count=524288
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

## Review tasks on a large database (2026-11-10)

The [review update](review-update-plan.md) added lists that read parts of documents across the whole database (the
unreconciled mentions, the identifications a toolchain suggested), and changed who made an item from one name to a
list. Measured on the scratch Memgraph above (the demo's data, 642,551 nodes), with 3,000 `Witness` entities and
12,000 reviewed `Hearing` documents added by the models (each a testimony with two `Unreconciled` and one
`IdentificationByToolchain` of two weighted candidates): **732,555 nodes, 145,000 head nodes, 24,000 mentions,
12,000 suggestions**. One process, straight to the service functions (no HTTP); medians of six runs after the first.
The load itself: 12,000 hearings in 158 s with 8 writers (76 a second, 7 nodes each).

| | Median |
|---|---|
| `Hearing.get` (a document of 6 nodes) | 2.2 ms |
| `Hearing.list`, a page of 25 (of 12,000) | 29 ms |
| Who made 50 head nodes: one name by a join, as before | 1.9 ms |
| The same, as the list of makers (a pattern comprehension over the `created_by` edges) | 2.3 ms |
| The queue of documents, `unchecked` (12,000), page 1 | 119 ms |
| The queue, of the documents given to one person (1,200) | 32 ms |
| Unreconciled mentions, a page of 25 (of 24,000, sorted by label) | 51 ms |
| The same, with a word of the label (`q=smith`) | 14 ms |
| The same, of the documents given to one person | 37 ms |
| Mentions like one (`similar`): same label by its index, near ones scored | 100 to 117 ms |
| Suggestions, a page of 25 (of 12,000) | 27 ms |
| Suggestions that say the same as one | 41 ms |
| The counts of the three tabs, everyone's | 76 ms |
| The counts, one person's | 68 ms |
| Reconcile one mention (read the document, write it again, give the URIs) | 22 ms |
| Reconcile one with 90 others: the answer | 88 ms; the others, in the background, 53 ms each (4.8 s) |
| Confirm one suggestion | 18 ms; with 14 alike, all done in 0.3 s |

What the measuring changed:

- **A part's head, found after a `WITH`.** `MATCH (u:Unreconciled) MATCH (head:HeadNode {id: u.head_node_id}) WHERE
  <a condition on head>` was planned as a hash join with a scan of every head node (145,000): 110 ms to count 24,000
  mentions. With `WITH u` between the two matches the head is found by the index of ids: 29 ms. The counts of the
  tabs went from 239 ms to 76 ms. (`pangloss_review/graph.py` says so at its top.)
- **A lookup by id goes through `PGIndexableNode` or `HeadNode`**, which have the index of ids: `MATCH
  (u:Unreconciled {id: $id})` scans the label (24,000 nodes), as does `MATCH (e:Entity {id: $id})`. Reconciling one
  mention went from 131 ms to 22 ms (with the next point), and the suggestions like one from 145 ms to 41 ms.
- **An entity is read without what refers to it** (`get_for_edit`) when a mention is reconciled with it: `get` reads
  every document that refers to it, which grows with each mention reconciled.
- **A limit must not decide what is found.** The first query for similar mentions read every mention sharing a word
  with the label, at most 2,000 of them, in no order: for "John Smith" thousands share a word, and only 2 of the 4
  mentions with the *same* label were among those read. Those are now found by the index of `label_key`, all of
  them, and the near ones are read lightly (id and label), those sharing the most words first.
- The Review page asked for the counts once for each tab (three requests of the same); it asks once.

Not measured: on Neo4j (the tests of all of it pass there; the plans may differ); through the API with many readers;
the queue of documents, which is as it was (it builds a row for every document in the status before it cuts the
page: 119 ms for 12,000).


### Parts found by a URI (2026-11-11)

Two parts that name the same URI are of the same person, so they are found by it (`pangloss_review.uris`,
[review.md](review.md)). Three ways of storing the URIs, on synthetic nodes beside the data above (6 in 10 parts
name a URI, a URI is named by about four parts); the time to find the parts that name one URI:

| Parts | List property on the part (a scan of the label) | One node for each URI, shared | A node for each URI of each part |
|---|---|---|---|
| 12,000 | 1.9 ms | 0.5 ms | 0.4 ms |
| 100,000 | 11.7 ms | 0.4 ms | 0.35 ms |
| 500,000 | 56 ms | 0.4 ms | 0.34 ms |

A URI named by 2,500 parts takes 40 ms either way (the rows). 480 writes at once that name one URI: 325 ms with
the shared node, 137 ms with a node each (as with none); two open transactions that link to one shared node did
not conflict. Built: a node for each URI of each part, with no edge (`PGUriClaim`), since an update rewrites what
is under a document and a shared node would need its orphans cleared and a guard against two writers making it.

As built, on the same database (732,928 nodes; the 24,000 mentions and 12,000 suggestions given URIs, 21,402
claims): making every claim again 0.1 s; the parts that name a URI 1.9 ms (pending marks worked off first);
similar mentions 140 ms (as before: the labels are what takes the time) and similar suggestions 46 ms, the URI's
first in each; a suggestion with who has its URI 3.4 ms; a save of a hearing with a mention and a suggestion
15.9 ms with the index kept, 13.0 ms without. Two index updates at once that claim the same marks conflict, and
the second is run again a second later: so one runs at a time in a process (`uris._one_at_a_time`). Not measured:
Neo4j.
