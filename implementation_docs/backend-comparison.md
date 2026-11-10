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

## Through the API: 75 kinds of request (20,000 entities, 6,000 factoids)

`pangloss-demo/compare_api.py` calls the real application (`create_app()` and its lifespan: middleware, authentication, the history recorder; httpx in the same process) and times each route. The installed apps are the demo's models, users, history and review in one run (`core`), and dates, calendar and typology in another (`extras`: the demo's own `Date` clashes with `pangloss_dates`'). Both containers had 4 CPUs and 6 GB (Neo4j: heap 2 GB, page cache 1 GB). The data are about 26,000 nodes of the demo, 300 reviewed memos, a typology of 600 types with 1,500 posts, 21 feasts and a Julian calendar of 80 years. Each request is run 7 times after a warm-up (3 for the slow ones), one at a time. **Medians in ms; the p95 is in the JSON the script writes.**

```
PYTHONPATH=pangloss-demo uv run python pangloss-demo/compare_api.py memgraph|neo4j core|extras
# (for Neo4j set PANGLOSS_TEST_BACKEND=neo4j as well: the calendar's migration is applied by pangloss-testing)
```

Of the 75 requests, **Memgraph is more than 20% faster in 42, Neo4j in 12, and 21 are within 20%.**

| Request | Memgraph | Neo4j |
|---|---|---|
| **Reading one record** | | |
| GET a Person | **5.5** | 23.5 |
| GET a Person for edit | **4.5** | 12.8 |
| GET a Factoid (whole) | **4.5** | 27.4 |
| GET a Factoid for edit | **6.4** | 28.2 |
| GET an id that is not there (404) | **3.0** | 7.2 |
| **Lists** (50 per page) | | |
| Person page 1 / page 100 | **28 / 30** | 40 / 39 |
| Factoid, Group, Place page 1 | 27 / 28 / 28 | 28 / 28 / 27 |
| Statement (an abstract class, all kinds) | **57** | 85 |
| Person, published only | 41 | 39 |
| **Text search in a list** | | |
| a label (`Person 1234`) | 27 | 24 |
| a prefix (`Perso`) | 50 | 41 |
| nothing found | **5.3** | 8.4 |
| deep search (`Known 99`) | **11** | 19 |
| Factoid label | 32 | 30 |
| **Autocomplete** (Person) | | |
| `Pers` / `Person 12` / Person and Group | **6.3 / 5.8 / 5.9** | 28 / 14 / 12.5 |
| **Structured search** (`POST /api/search`) | | |
| Factoid year = 800, year between | 93 / 96 | **6.6 / 6.9** |
| Factoid label = | **4.8** | 7.2 |
| Factoid not year 800 / year = or year = | **8.6 / 5.9** | 12 / 8 |
| Factoid by its source (is / pattern) | **11 / 14** | 36 / 40 |
| Factoid: an activity by a person | **16** | 35 |
| Factoid: a statement in a Negative | **32** | 41 |
| Factoid mentions a person / a place | **83 / 83** | 245 / 270 |
| Factoid somewhere a transfer of silver | 24 | 26 |
| Person with an incoming activity | **22** | 54 |
| Person with an incoming statement of year 800 | **12** | 41 |
| Person label contains | **5.6** | 11 |
| Person: all | **11** | 29 |
| **Writing** | | |
| POST a Person | 17 | **11** |
| POST a Factoid (3 statements) | 22 | **13** |
| PUT a Person (rename, with `If-Match`) | 26.5 | 27 |
| DELETE a Person | 11.4 | 11.3 |
| **Users** | | |
| GET /me, list users, list tokens | **3.8 / 8.1 / 8.3** | 5.1 / **5.9 / 6.2** |
| POST token (login), POST access token | 25 / 9.4 | 26 / 8.6 |
| **History** (the recorder is SQLite; the reads fetch the node) | | |
| versions / a version / a draft / a diff | 11.6 / 5.4 / 4.5 / 5.3 | 12.0 / 6.5 / 5.6 / 6.4 |
| POST restore | 33.4 | 33.3 |
| **Review** | | |
| queue / queue by status and type / detail | 14.6 / 20.9 / **6.1** | 14.2 / **13.0** / 9.8 |
| POST comment / POST status | 9.4 / 12.1 | 10.9 / 15.3 |
| **Typology** (600 types) | | |
| GET the tree | 61.5 | **30.2** |
| GET a type with its entities | 112 | **55** |
| GET a type's path | 55 | **27** |
| PATCH a type | 124 | **72** |
| **Calendar** (80 years of days) | | |
| day / day in the other calendar / month | 9.4 / 6.4 / 6.3 | 9.4 / 8.5 / 7.5 |
| year / Easter / list characterisations | **3.3 / 3.2 / 3.2** | 5.4 / 5.6 / 5.8 |
| days of a characterisation / POST attach | 6.0 / **6.3** | 6.9 / 9.1 |

**Eight at once** (requests per second; every request answered 2xx):

| | Memgraph | Neo4j |
|---|---|---|
| GET a Person x 600 | **473** | 404 |
| GET a Factoid x 300 | **322** | 280 |
| autocomplete x 300 | **789** | 604 |
| list with a search x 200 | 124 | **184** |
| structured search (year) x 150 | 29 | **360** |
| POST a Person x 300 | 122 | **255** |
| PUT a Person x 150 | 80 | **118** |
| 80% reads, 20% writes x 400 | 288 | **364** |
| calendar day x 200 | **405** | 304 |
| typology type x 200 | 32 | **45** |

Loading these through the models (four at a time, history recording on): entities 200-217 a second on Memgraph, 575-786 on Neo4j; factoids 97 against 80. The whole load took 157 s against 107 s.

### What the API shows

- **Memgraph wins the reads that the interface does most:** a record, a record for edit, autocomplete, a 404, anything that walks edges from a known node (a factoid's source, an activity by a person, what mentions a person). It is 3-5 times faster for a single record through the API (about the same ratio as in-process).
- **Neo4j wins writes, and anything that filters a literal on many nodes with a plan that suits it:** the year searches are 14 times faster (93 against 6.6 ms), and 12 times at eight at once. I did not find out why Memgraph is slow there (6,000 factoids is not many to scan: it is the first thing to look at, with `search_benchmark.py --profile`, and whether the demo's index on `Factoid(year)` was in place: this run did not apply the demo's migrations).
- **Typology is twice as fast on Neo4j** (the tree, a type's path, a patch): these are walks up and down a hierarchy; I did not look at why Memgraph is slower there.
- **Pangloss and not the database costs the same on both:** a login is 25 ms (the password hash), a list of a small class is 27-28 ms for both, a restore is 33 ms for both, and the history reads (SQLite) are within 1 ms.

### After profiling

The figures above are from before the Memgraph fixes of [backend-profiling.md](backend-profiling.md): the year searches (93 ms, 14 times Neo4j's) are now 4-8 ms, the typology reads are 2-3 times faster (the tree 62 to 23 ms), and 150 searches at once go from 29 to 434 a second. The rest is unchanged within the noise.

### Caveats for this run

- The calendar's days have no documents with dates: `Event.Create(when={"type": "JulianExactDate", ...})` is refused outside the live tests' set-up, and I did not find out why. A day report is therefore the characterisations and no hits.
- The indexes were made after the models were initialised (the earlier in-process comparison made them **before**, so it had none of the per-class label indexes: its search figures are lower than they would be on both). The demo's migrations (its `Factoid(year)` index) were not applied: `MIGRATION_CHECK` was off.
- One run each; both have outliers on single reads (the worst p95 is 5.7 times the median for Memgraph, a whole Factoid, and 5.2 times for Neo4j, a Person: 121 ms against 23.5), and the figures under 20% apart are noise.
- `compare_backends.py` (in-process, the models) and `compare_api.py` (HTTP) are two scripts that share no code.

## Caveats (of the in-process comparison above)

- **One run, one machine** (8 cores, 25 GB for Docker). Both databases were started clean, and Neo4j was not tuned further than the memory below. Treat a difference under 20% as noise. Memgraph's timings are steady (p95 at most 2.2 times the median); **Neo4j's have outliers** (p95 up to 12 times the median for a get of a person, a search by label, and a create of a factoid), so its medians are better than its worst case.
- **Neo4j ran out of memory at the large size** with its default heap ("Java heap space", while loading factoids, in a 4 GB container). Setting the heap to 2 GB and the page cache to 1 GB in a 6 GB container ran it to the end with no errors. A production Neo4j needs memory settings (`neo4j-admin server memory-recommendation`); Memgraph did the same in 4 GB without any setting (its memory use was not measured). Neo4j's second run therefore had 2 GB more memory than Memgraph's.
- **Memgraph at the large size** is in its default (transactional) mode. Its analytical bulk mode (`pangloss memgraph bulk-load`, 2.8 times faster) is not in these figures, and Neo4j's bulk load is not either. They time loading through the models only.
- **Four concurrent writers** loaded the data, and eight readers read it: more would change the concurrent figures.
- **Not measured:** structured search (`/api/search`), the history and review queries, migrations, memory use, disk use, the add-on packages (calendar, typology), or anything over 600,000 nodes. The search on `search_benchmark.py` is Memgraph's only.
- Accents: Neo4j finds "Zürich" for `zurich`, Memgraph does not ([TODO.md](../TODO.md)). The figures do not include that.

## Reading it

Neither is the winner at either size, or through the API. Memgraph is the faster for the reads of one record and needs no tuning; Neo4j writes and loads much faster at size, searches faster, and its speed does not fall as the database grows, but it needs memory set. For a database that is loaded once and read (a published edition), Memgraph's lead in reads is the thing; for one that is edited all the time, or loaded in large batches, Neo4j's.

If one is to be chosen on speed, the next measurements to make are the structured search and the `list` of statements at size (the slowest operations on both), and a Neo4j with more of its memory settings tried.
