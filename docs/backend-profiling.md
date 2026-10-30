# Profiling the backends

✅ Measured and, for Memgraph, fixed 2026-10-30 (see **After the fixes** below), on the data of [backend-comparison.md](backend-comparison.md) (20,000 entities, 6,000 factoids, 300 memos, 600 types, a calendar of 80 years: about 118,000 nodes on Memgraph). **What is in it was measured; what was not is said to be a guess.**

## Method

`pangloss-demo/compare_api.py <backend> core|extras --profile` calls each of the 75 requests of the comparison, and for one of them keeps every statement the transactions are given (`neo4j.AsyncManagedTransaction.run` is wrapped). It then runs each statement as `PROFILE` and, for the reads, times it five times by itself with the driver:

- **`api_ms`** is the request through the application (median of 5); **`db_ms`** is the sum of the reads' own times, fetching all the rows; what is left (a median of **5.4 ms** on Memgraph and 4.9 on Neo4j for a read, 6.5 and 6.1 for the extras) is what Pangloss and httpx cost: it is the same on both and small.
- **Memgraph** gives the rows pulled and the time of each operator, but will not profile inside a transaction, so its reads are profiled as they are and **its writes are timed and not profiled** (the PROFILE would write).
- **Neo4j Community** gives the database hits and rows of each operator (not their time). Its PROFILEs are run in a transaction that is rolled back.

```
PANGLOSS_TEST_BACKEND=neo4j PYTHONPATH=pangloss-demo uv run python pangloss-demo/compare_api.py neo4j core --profile --out FILE
```

## Findings: Memgraph

### 1. Every write scans the whole database for the migration lock

`MATCH (l:PGMigrationLock) RETURN count(l)` is run by each write, and in Memgraph its plan is `ScanAll (l)` and then a filter on the label: **118,059 nodes read for a lock that is not there** (Neo4j answers it from its count store in one hit). The cost grows with the database, measured on its own in a scratch Memgraph:

| nodes | 10,000 | 100,000 | 300,000 | 600,000 | 610,000 with `CREATE INDEX ON :PGMigrationLock` |
|---|---|---|---|---|---|
| ms | 1.7 | 3.2 | 6.6 | **12.0** | **0.3** |

It is one of about 10 statements of a create (8-14 for each write), and about 35% of the 34 ms that a Person took to create at 600,000 nodes ([backend-comparison.md](backend-comparison.md): 7.6 ms at 8,500 nodes). **A label index on `PGMigrationLock` is the cheapest speed-up found.** The other statements of this kind, which are plain `ScanAll` over every node (rows 118,000-118,174 each time): `MATCH (user:PGUser)` (list users), `MATCH (token:PGAccessToken {username})` (a user's tokens), and the review queue `MATCH (head:HeadNode:PGIndexableNode)` (1.3-2.4 ms by itself, with 301 reviewed memos), and the calendar's `MATCH (t:CalendarDay)-[:CHARACTERISED_BY {origin: 'manual'}]` (`ScanAll (t)`, 36,007 rows). Each wants a label index (not tested, except the first).

### 2. The creation of each result is looked up from the wrong end

Every list and search fetches who made each node of the page with `OPTIONAL MATCH (creation:PGCreation)-[:is_creation_of]->(n)`. For `year = 800` Memgraph planned it as `ScanAll (creation)` and then a filter (not even by label), once for each of the 26 results: **2,951,025 rows scanned, 657,525 filtered, 86 ms** for a page of 26. The same shape for `year between` was planned from `n` (`Expand (n)<-[is_creation_of]-(creation)`: 2.2 ms), so which plan is made varies with the query. Written from `n` (`OPTIONAL MATCH (n)<-[:is_creation_of]-(creation:PGCreation)`), a scratch copy of the same shape went from 24.3 ms to **1.4 ms**, and without the label on `creation` to 1.2 ms. The search by year was 14 times slower than on Neo4j for this reason alone ([backend-comparison.md](backend-comparison.md)). The index on `Factoid(year)` **was** used (`ScanAllByLabelProperties`): my earlier guess in that document that it was missing was wrong.

### 3. The typology reads scan every type for every type: a plan kept from when the vocabulary was small

`OPTIONAL MATCH (t)-[:is_subtype_of]->(p:RoleType) WHERE ...` on 600 types read `ScanAllByLabel (p)` for each `t` and then filtered: **360,600 rows, 29 ms of 53** for the tree, the path, a type with its entities, and a patch (all about twice as slow as on Neo4j, which does 7,735 hits). A copy of the same tree, built first and queried after, did not do it, and that was the clue: **Memgraph keeps the plan of a query by its text**, and the plan is made the first time the text is run, with the statistics of that moment. Run with 2 types, then 600 made quickly, the same text kept the bad plan **70 seconds later** (360,600 rows, 48 ms), and a variant that did not depend on the order of the join (`CASE WHEN p:RoleType AND ... THEN p.id END` after an `OPTIONAL MATCH (t)-[:is_subtype_of]->(p)`, or a pattern comprehension) stayed at 1,200 rows and 15 ms (all of it the 600 rows crossing the wire). The vocabulary is read when the first type is made, so the plan is made at that moment.

This is probably not particular to the typology: any query whose plan has a choice of where to start, first run on a small database, can keep a plan that is wrong at size. The creation lookup (2) looks like the same thing (its plan was good in a test on an almost empty database and bad on 6,000 factoids). I did not look for the others, or for the setting of the plan cache (`--query-plan-cache-ttl` in the Memgraph flags?) that might bound it.

### 4. Other

- **A mention** (`$mentions`, the factoids that mention a person or a place) takes 80-90 ms: `Filter (w13 :PGIndexableNode)` over 53,412 rows, 16 ms. Neo4j does the same in 242-268 ms (see below).
- **Prefix search** `Perso` (12,001 hits) is 44 ms, `CallProcedure<text_search.regex_search>`: the text index is asked for 12,000 nodes and they are all matched and sorted.

## Findings: Neo4j

### 1. A write looks up the entity by scanning every entity

`MATCH (entity:Entity {id: $id}) UNWIND $urls AS url MERGE (node:PGUrl ...)` (the URLs of an entity) plans as `NodeByLabelScan entity:Entity` and a filter on `id`: **20,007 db hits for a PUT of a Person and for a restore**, though the entity is one node. There is no index that this match can use (I did not check which indexes exist on `id`). A rename took 27 ms (the same as Memgraph's at this size); this grows with the number of entities. Match it with its own label, or index `Entity(id)`.

### 2. `$mentions` is an `EXISTS` over every edge of every factoid

`Factoid mentions a person/place` is 242-268 ms: 468,500 db hits, `Filter` over 11,450 rows. It is the slowest request of all in this comparison, 3 times Memgraph's.

### 3. Walks from a known node cost more hits

`source is` and `source pattern` (`VarLengthExpand(All)`: 78,000 hits, 27-33 ms), `activity by person` (`Expand(All)`: 108,551 hits, 30 ms), `Person incoming activity` (`VarLengthExpand(Pruning,BFS,All)`: 221,953 hits, 56 ms) and the review queue (`SubtractionNodeByLabelsScan`: 90,528 hits, 6,306 rows) all read many times what Memgraph does, and are 2-4 times slower for it.

### 4. A record is 5 statements

Getting a Person takes 15.9 ms in the database on Neo4j and 5.7 on Memgraph for the **same five statements** (the plan shows 108 db hits for 4 rows in `Projection`; I did not look into why it takes 3 times as long). Autocomplete `Pers` takes 28 ms (`Filter` of 12,000 nodes: 36,000 hits) against Memgraph's 4 ms: Neo4j's full-text index finds the nodes, and every one of them is then filtered.

## Both

- **A list reads the whole class every time.** `MATCH (n:Person) ... WITH collect(n) AS allNodes ... ORDER BY toLower(n.label)` counts and sorts all 12,000 persons to give 50 (Neo4j: `Filter` 36,000 hits, Memgraph: `OrderBy` 12,001 rows), so a list is 20-27 ms inside the database on both, and grows with the class (71 ms at 60,000 people, 272 ms for statements at 600,000 nodes: [backend-comparison.md](backend-comparison.md)). The operators add up to far less on Memgraph (the largest is 2.3 ms against 25 ms for the query), and I did not find where the rest of its time goes.
- **What Pangloss costs is the same on both and small:** 5-6 ms per request outside the database; a login is 25 ms (the password hash) and 0.3-0.7 ms of database.
- **The history reads** (SQLite) are 1-3 ms of database; **the calendar's** are 1-5 ms.

## After the fixes (Memgraph, 2026-10-30, commit `ac3036d`)

Done for Memgraph: (1) label indexes on `PGMigrationLock`, `PGUser`, `PGAccessToken` and `HeadNode` (`LABEL_INDEXES` in `initialise_database.py`; the shipped migration `0005_addindex_addindex_addindex`); (2) the creation lookup of a search from the node (`build_search_query.py`); (3) the typology's parent chosen with a `CASE` after the match (`pangloss_typology/graph.py`, for both backends). The same 75 requests, the same data and containers as in [backend-comparison.md](backend-comparison.md); medians in ms:

| Request | before | after | Neo4j |
|---|---|---|---|
| search: Factoid year = 800 | 92.8 | **8.2** | 6.6 |
| search: Factoid year between | 95.7 | **4.4** | 6.9 |
| typology: GET tree | 61.5 | **22.8** | 30.2 |
| typology: a type with its entities | 111.6 | **41.7** | 55.4 |
| typology: a type's path | 55.4 | **25.2** | 27.4 |
| typology: PATCH a type | 124.3 | **65.0** | 71.9 |
| 150 year searches at once, per second | 29 | **434** | 360 |
| 200 typology reads at once, per second | 32 | **60** | 45 |

What did not change, at this size: the writes (a Person 17.1 to 15.7 ms, a Factoid 21.7 to 23.2). The lock check is 3.6 ms of them at 118,000 nodes, and the index takes it to 0.3, but the other statements of a write are what is left: **the effect of the index on a write is measured only by itself (12 ms to 0.3 ms at 600,000 nodes), not yet through the API at that size.** Everything else is within the run-to-run difference (a request of a few ms varies by 2 times between runs here: `GET a Person` was 5.5, 9.1 and 10.5 ms in three runs).

The tests: 2,439 in the main run, 594 for Neo4j and the add-ons on Neo4j all pass. Two tests of Memgraph's plans were changed for the new indexes (a search of an unindexed class starts at the head nodes' label index; the helper that looks for an index knows label indexes); a test keeps the text of the creation lookup (a plan in a test cannot show the problem, as it depends on the statistics when the query is first planned).

## What is left (ranked)

1. **Look for other plans kept from a small database** (Memgraph): the cache of plans by text is the cause of 3, and probably 2; a setting or a restart of the plan after the loads would be a general remedy. Not done.
2. Neo4j: index `Entity(id)` or match writes by the concrete label; look at the `EXISTS { ... }` of `$mentions` (468,000 hits, the slowest request of all).
3. Memgraph: the calendar's `MATCH (t:CalendarDay)-[:CHARACTERISED_BY {origin: 'manual'}]` scans all `CalendarDay` (36,007 rows; 0.4 ms each here); a label index in the calendar's `structure.py` (a migration of the calendar, and for both backends).
4. Both: page a list without collecting and sorting the whole class (a `SKIP`/`LIMIT` on an indexed order, or a label index on a lower-cased label): the list is the request the interface makes most.

## Not done

- Memgraph's writes were not profiled (the tool will not inside a transaction): the 8-14 statements of a write are known, not their plans, apart from the lock check.
- Neo4j's operator times (not given by Community) and its `EXPLAIN` estimates.
- Whether the Python driver's decoding is the missing part of a list's time on Memgraph.
- One run each, at 118,000 nodes; the lock-check scaling was measured on its own, the others only at this size.
