# Memgraph and Neo4j compared

✅ Measured 2026-10-30. One run of each at two sizes, on one laptop: the figures show how the two compare, not what a server will do.

## What was run

`pangloss-demo/compare_backends.py` drives the **demo's models** (`Person`, `Group`, `Place`, `Source`, and `Factoid` with 2-3 nested statements, edges, semantic spaces) through each backend's own exposed functions, so it times Pangloss, not bare Cypher. For each backend it starts a fresh Docker container, loads the data (four writes at a time), times the operations, and removes the container.

```
PYTHONPATH=pangloss-demo uv run python pangloss-demo/compare_backends.py memgraph|neo4j \
    [--entities 6000] [--factoids 2000] [--repeat 5] [--memory 4g] [--out FILE]
```

| | Small | Large (the size of `bulk_load.py`, see [large-data.md](large-data.md)) |
|---|---|---|
| Entities (60% people, 15% groups, 20% places, 5% sources) | 6,000 | 100,000 |
| Factoids | 2,000 | 30,000 (about 600,000 nodes) |

Containers: Memgraph `memgraph-mage:3.14.0`, 4 CPUs, 4 GB (the flags of the test containers). Neo4j `2026.10.1` Community, 4 CPUs; **4 GB at the small size, 6 GB with a 2 GB heap and 1 GB page cache at the large size** (see below). Serial timings are the median of 8-40 runs after a warm-up. The tables give milliseconds (lower is better) and operations per second (higher).

## Small: 6,000 entities, 2,000 factoids

| | Memgraph | Neo4j |
|---|---|---|
| **Load**, per second: people / groups / places / sources | 228 / 234 / 212 / 231 | **416 / 612 / 601 / 588** |
| factoids | **101** | 50 |
| create a person, ms | 7.6 | **5.4** |
| create a factoid, ms | **14.8** | 16.9 |
| get a person, ms | **2.5** | 10.5 |
| get a factoid (whole document), ms | **3.0** | 15.3 |
| get a person for edit, ms | **1.2** | 3.2 |
| list people, page 1 / page 20, ms | 27.3 / 27.4 | 27.1 / 26.8 |
| list statements (all kinds), ms | **32.2** | 37.3 |
| search: a person by label, ms | **6.9** | 11.4 |
| search: a group by name, ms | **4.1** | 7.3 |
| search: prefix with many hits, ms | 28.9 | 28.9 |
| search: factoids by label, ms | 28.8 | **25.4** |
| delete a factoid, ms | **3.3** | 4.8 |
| 400 factoid gets, 8 at once, per second | 427 | 416 |
| 1,000 person gets, 8 at once | **940** | 271 |
| 200 searches, 8 at once | **339** | 268 |
| 400 person creates, 8 at once | 223 | **785** |

## Large: 100,000 entities, 30,000 factoids

| | Memgraph | Neo4j |
|---|---|---|
| **Load**, per second: people / groups / places / sources | 187 / 173 / 167 / 157 | **696 / 824 / 721 / 777** |
| factoids | 70 | **111** |
| whole load | about 17 min | about 7 min |
| create a person, ms | 34.1 | **4.1** |
| create a factoid, ms | 45.4 | **7.8** |
| get a person, ms | **4.8** | 7.5 |
| get a factoid (whole document), ms | 14.9 | 15.2 |
| get a person for edit, ms | **2.1** | 3.4 |
| list people, page 1 / page 20, ms | **71 / 66** | 92 / 80 |
| list statements (all kinds), ms | **272** | 338 |
| search: a person by label, ms | 126 | **65** |
| search: prefix with many hits, ms | 205 | **125** |
| search: factoids by label, ms | 112 | **48** |
| search: a group by name, ms | 67 | **34** |
| delete a factoid, ms | 28.1 | **6.6** |
| 400 factoid gets, 8 at once, per second | 423 | 409 |
| 1,000 person gets, 8 at once | **837** | 309 |
| 200 searches, 8 at once | 17 | 19 |
| 400 person creates, 8 at once | 96 | **759** |

## What it shows

- **Reads of one record:** Memgraph is faster at both sizes (a person in 2-5 ms against 8-10 ms; much better with 8 readers at once). A whole factoid is the same at 600,000 nodes, and Memgraph's lead at the small size was lost.
- **Writes:** Neo4j's stay flat (4-8 ms for a person or a factoid at both sizes, 750+ concurrent creates a second). Memgraph's slow down with the size of the database: a person takes 7.6 ms at 8,500 nodes and 34 ms at 600,000, and 8 concurrent creates fall from 223 to 96 a second. The likely cause is Memgraph's text index on every commit (not isolated in this run) (my measurement of it earlier: about 4.5 ms a commit; see [large-data.md](large-data.md)); loading 130,000 items took 17 minutes against 7. Deleting a factoid is 4 times slower on Memgraph at size.
- **Search:** the small database hides it, but at size Neo4j's full-text index (Lucene) is about twice as fast as Memgraph's text index for a label or a name (126 against 65 ms, 112 against 48 ms). Prefix searches with many hits: 125 against 205 ms. Eight searches at once are slow for both (17-19 a second), and no different between them.
- **Lists:** Memgraph is 15-25% faster at size. Neither is quick at listing statements (270-340 ms): they count every statement in the database.
- **Where a user would see it:** the interface reads one record at a time and searches as the user types. Reads are fast in both, searches are faster on Neo4j, and a load of many records is much faster on Neo4j. The one place Memgraph is clearly ahead is reading single records at once.

## Caveats

- **One run, one machine** (8 cores, 25 GB for Docker). Both databases were started clean, and Neo4j was not tuned further than the memory below. Treat a difference under 20% as noise. Memgraph's timings are steady (p95 at most 2.2 times the median); **Neo4j's have outliers** (p95 up to 12 times the median for a get of a person, a search by label, and a create of a factoid), so its medians are better than its worst case.
- **Neo4j ran out of memory at the large size** with its default heap ("Java heap space", while loading factoids, in a 4 GB container). Setting the heap to 2 GB and the page cache to 1 GB in a 6 GB container ran it to the end with no errors. A production Neo4j needs memory settings (`neo4j-admin server memory-recommendation`); Memgraph did the same in 4 GB without any setting (its memory use was not measured). Neo4j's second run therefore had 2 GB more memory than Memgraph's.
- **Memgraph at the large size** is in its default (transactional) mode. Its analytical bulk mode (`pangloss memgraph bulk-load`, 2.8 times faster) is not in these figures, and Neo4j's bulk load is not either. They time loading through the models only.
- **Four concurrent writers** loaded the data, and eight readers read it: more would change the concurrent figures.
- **Not measured:** structured search (`/api/search`), the history and review queries, migrations, memory use, disk use, the add-on packages (calendar, typology), or anything over 600,000 nodes. The search on `search_benchmark.py` is Memgraph's only.
- Accents: Neo4j finds "Zürich" for `zurich`, Memgraph does not ([TODO.md](../TODO.md)). The figures do not include that.

## Reading it

Neither is the winner. Memgraph is the faster for the reads of one record and needs no tuning; Neo4j writes and loads much faster at size, searches faster, and its speed does not fall as the database grows, but it needs memory set. For a database that is loaded once and read (a published edition), Memgraph's lead in reads is the thing; for one that is edited all the time, or loaded in large batches, Neo4j's.

If one is to be chosen on speed, the next measurements to make are the structured search and the `list` of statements at size (the slowest operations on both), and a Neo4j with more of its memory settings tried.
