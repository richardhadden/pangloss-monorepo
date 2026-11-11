# Similar items by graph embeddings: an investigation ⏳

Written 2026-11-11. **Nothing here is built.** This page says how documents and entities could be given vectors from
the shape of the graph around them, kept in a vector index, and searched for "items like this one"; what the two
databases offer; what was tried and measured on throwaway containers; what would have to be built; and what is left
for the user to decide.

## Contents

- In short
- What is to be similar: heads, and the head graph
- What the databases offer
- What was tried and measured
- Which algorithm
- Where the computing is done
- Where the vectors are kept
- The batch: building every vector
- On write: keeping vectors current
- Who may see what
- Declaring it in a project
- API, SDK and interface
- Neo4j
- What would be built
- Decisions for the user
- What is not known yet
- Sources

## In short

- **Embed only head nodes** (top-level documents and entities), over a **head graph**: one node per head, an edge
  wherever something inside a head's tree points at another head. The stored graph, with its reverse edges, inner
  nodes, records and add-on nodes, is the wrong graph to walk (see the next section).
- **Use FastRP, computed by Pangloss in Python, not node2vec in the database.** On a synthetic graph of 520,000 nodes,
  FastRP over the 320,000-head graph took **0.2 s** of computing; Memgraph's `node2vec` took **204 s** and GDS's
  `node2vec` 122 s. FastRP is deterministic when each head's random start vector is seeded by its own id, and a
  head's vector depends only on its neighbourhood a few steps out, so it can be updated locally after a write.
- **The database stores and indexes; it does not have to compute.** Both databases have a vector index in their free
  editions. So the same code runs on Memgraph and Neo4j, and nothing has to be installed into the database. A custom
  Memgraph query module only pays off if reading the head graph out of the database becomes what costs. It does at
  scale (14 s of the 106 s total), but writing the vectors back costs more.
- **Keep vectors on their own nodes**, `(:PGEmbedding {vector})-[:embeds]->(head)`, not on the head. An update
  replaces a head's properties, and every read returns all the properties of every entity it refers to.
- **On write**: the existing `hooks.pending_work` queue plus a background worker, as `pangloss-derived` does it. A
  changed head gets a vector folded in from its neighbours' vectors at once (under 1 ms each, measured), and a full
  rebuild (about 2 minutes at this size, mostly I/O) runs as an admin job or on a schedule to stop drift.
- **`node2vec_online` is not usable.** It is not in the community image: the procedure does not exist without a
  licence. Even with one, it only learns from added edges, and a Pangloss update deletes and re-creates a document's
  whole tree.
- A new package, provisionally **`pangloss-similar`**, with two new `Dialect` methods, a capability, a migration for
  the index, a route, an SDK operation and an interface section. Nothing in the core needs to know of it.

## What is to be similar: heads, and the head graph

The user's requirement is to index only documents and entities. In Pangloss terms that means **head nodes** (`HeadNode`,
with `Document` or `Entity`). The stored graph is wrong to walk as it is:

| In the stored graph | Why it misleads an embedding |
|---|---|
| Every relation is two edges (`field` and its reverse, `reverse: true`) | A walk goes back and forth along the same relation; degrees are doubled |
| A document is a tree of nodes (nested documents, reified relations, embedded objects, semantic spaces, conjunctions) | Two people named in one factoid sit 2-4 steps apart, depending only on how the factoid was modelled. A deeply nested model would make its entities look unrelated |
| `PGCreation`, `PGUpdate`, `PGUser`, `PGUrl`, `PGPending`, `PGUriClaim`, `PGDerived`, calendar days, migrations, locks | Not research data. `PGUser` alone would link everything one person entered |
| Flagged nodes (`deleted`, unpublished) | Must not shape what a reader sees (see "Who may see what") |

**The head graph** contracts each head's tree into the head. There is one node per head, and an undirected edge
`(head A) — (head B)` wherever a node of A's tree (A itself or a node with `head_node_id = A`) has a forward edge to
head B. In practice B is an entity, because documents point at entities and contain documents. One query reads it:

```cypher
MATCH (n:PGIndexableNode)-[e]->(x:HeadNode)
WHERE NOT coalesce(e.reverse, false)
RETURN coalesce(n.head_node_id, n.id) AS a, x.id AS b
```

(the visibility rules have to be added: see below). This graph is bipartite in the common case (documents on one side,
entities on the other). Entities become similar by appearing in similar documents, and documents by naming similar
entities. Documents and entities share one space, so "documents like this person" is a valid search too.

Things the head graph could carry later, each a decision rather than a default:

- **The field as a weight or a type.** "Born in" and "mentioned in passing" are not equal. FastRP takes a weight per
  edge; a `Meta` setting per field could give it.
- **Derived facts** (`PGDerived`: `SameGroup` and the like) as extra entity-to-entity edges.
- **Typology types** are entities, so they become hubs: a `gender` or `occupation` vocabulary would pull everyone
  sharing a value together. They probably want a low weight or exclusion, per field.
- **Edges between documents**, where a model has them.

## What the databases offer

Checked against the docs and, where marked ✔, against the images this repository runs (`memgraph/memgraph-mage:3.14.0`,
`neo4j:2026.10.1`).

| | Memgraph 3.14 (community) | Neo4j 2026.10 (Community) |
|---|---|---|
| Vector index | ✔ `CREATE VECTOR INDEX n ON :Label(prop) WITH CONFIG {dimension, capacity, metric}`; `:A\|B(prop)` multi-label ✔ | ✔ `CREATE VECTOR INDEX … FOR (n:L) ON n.p OPTIONS {indexConfig: {…}}`; multi-label and filter properties (`WITH [n.kind]`) since 2026.01 |
| Search | ✔ `CALL vector_search.search(index, k, vector) YIELD node, similarity` | ✔ `SEARCH x IN (VECTOR INDEX i FOR v LIMIT k) SCORE AS s` (the `db.index.vector.queryNodes` procedure still works, deprecated) |
| Filtering in the search | None: only by which index | `SEARCH … WHERE` on the filter properties |
| Metrics | `cos`, `ip`, `l2sq` and others; `scalar_kind` f32/f16/i8/… | cosine, euclidean; quantisation (binary by default since 2026.08) |
| Where the vector lives | In the index only (USearch); the property refers to it. Persisted in snapshots and WAL | A `LIST<FLOAT>` property (native `VECTOR` type is Enterprise only) |
| node2vec | ✔ `node2vec.get_embeddings` / `set_embeddings` (C++), on a `project(path)` subgraph | GDS `gds.node2vec` |
| FastRP | Not in MAGE | GDS `gds.fastRP` ✔ |
| Online / incremental | `node2vec_online`: Enterprise only, ✔ absent without a licence; edge additions only | None |
| GDS | — | ✔ Ships in the image (`NEO4J_PLUGINS='["graph-data-science"]'`, no download). Community: all algorithms, **at most 4 cores**, 3 models in the catalogue, no model persistence |
| Text embeddings | ✔ MAGE `embeddings.node_sentence` / `embeddings.text` (sentence-transformers, torch on CPU, in the image) | GenAI plugin (external providers) |
| Custom code in the database | Query modules in Python (`mgp`), C, C++ or Rust: files in `/usr/lib/memgraph/query_modules`, `CALL mg.load_all()` ✔ | Java plugins |
| Triggers | `BEFORE`/`AFTER COMMIT`, may `CALL` procedures | APOC triggers (not in the image) |

Things found while trying it that the docs do not say:

- **`project()` takes paths**, not nodes and edges: `MATCH path = (a)-[e]->(b) … WITH project(path) AS g`. Nodes with
  no edge in the projection get no vector (113k of 520k in the trial).
- **`knn.get` cannot read a property once a vector index holds it** ("must be a list of doubles"), so MAGE's
  k-nearest-neighbours and the vector index do not combine.
- **A just-deleted `PGEmbedding` can still be returned by `vector_search.search`** until garbage collection runs. A
  following `MATCH (node)-[:embeds]->(item)` then fails with "relationships of a deleted node". The index's `size` is
  not reduced by deletes. So: update vectors in place rather than delete and create, and make the read tolerant.
- **Writing vectors with the index live is slow**: 207k vectors in 88 s, against 14 s to build the index over vectors
  already written. A rebuild should write first and index afterwards, or write to a new generation (below).
- `node2vec` is deterministic with a seed and `workers = 1` ✔; with 8 workers it was not checked.

## What was tried and measured

All on throwaway containers (`:7702`, `:7703`, removed afterwards). The demo's and the tests' databases were not
touched. Laptop, Docker Desktop, 8 cores given to Memgraph, 4 to GDS (its Community limit).

**The synthetic graph** has 100,000 people, 20,000 places, and 200,000 factoids, each with one inner statement naming
two people and a place. That is 520,000 nodes and 1.6 million edges counting the reverse ones. Its structure is
degenerate (2,000 groups of factoids that all name the same few people), so **it says something about speed and
nothing about the quality of the vectors.**

| What | Memgraph | Neo4j + GDS |
|---|---|---|
| Projection, stored graph, forward edges (407,560 nodes, 800k edges) | 0.5 s | 1.7 s |
| node2vec (10 walks of 20, 64 dims) + writing 207k vectors | **204 s**, +2 GB memory | 122 s (stream only, 4 cores) |
| FastRP (64 dims, 3 iterations) on the same projection | — | **0.26 s** compute + 1.1 s write |
| FastRP in Python (numpy/scipy) over the head graph (320k heads, 600k edges, 128 dims) | read 14.4 s, seeds 3.5 s, **compute 0.21 s**, write 88 s with the index live | (same code would run) |
| Building the vector index over 207k vectors already written | 14 s | 9.5 s until online |
| Search, k = 20 | **0.6 ms** median, 1.0 p95 | < 5 ms (not timed finer) |
| Recall@20 of the index against brute force (10 queries) | 1.0 | — |
| Brute force over all vectors, one query | 662 ms | — |
| Fold-in of one new head from its neighbours (trial query module) | **0.4 ms** median; a hub with 201 neighbours 41 ms; 100 heads in one call 6 ms | — |
| Search near a factoid, fetch 200, keep only people | Found **2** of 20 wanted | (filter properties would do it in the index) |
| FastRP vector of a distant node after adding a node elsewhere | — | Unchanged (difference 0.0) ✔ |

The trial scripts are in `/tmp/embed-trial/` (`trial.py`, `big.py`, `time_n2v.py`, `time_idx.py`, `neo.py`,
`fastrp_out.py`, and the query module `modules/pg_embed.py`), with a scratch venv for numpy in `/tmp/embed-venv`. They
are scratch and will not survive a reboot. Anything kept should be rewritten in a package.

What the numbers mean:

- **Computing is not the cost; moving data is.** FastRP's arithmetic takes a fraction of a second. Reading the head
  graph out takes 14 s and writing vectors back up to 88 s. Batching, writing before indexing, and (on Memgraph) a query
  module that reads the graph in place are the levers.
- **node2vec costs three orders of magnitude more than FastRP** and cannot be updated locally, because it is trained
  on random walks across the whole graph.
- **Filtering after the search does not work**: the 200 nearest items to a factoid are mostly factoids and places. A
  "people like this" search needs an index of people, or Neo4j's filter properties.

## Which algorithm

| | FastRP | node2vec | node2vec_online | Text embeddings |
|---|---|---|---|---|
| What makes two items close | Shared neighbours, a few steps out | Walk co-occurrence (tunable towards communities or roles by `p`, `q`) | Recently added edges | What their labels and text say |
| Cost (520k nodes) | < 1 s | 2-3 min | — | Minutes to hours on CPU (not measured) |
| Deterministic | Yes, seeded by id | With a seed and one worker | No | Yes |
| Local update after a write | Yes: a head's vector depends on its k-step neighbourhood | No: retrain | Edges added only | Yes: embed that one head |
| Available on both backends | Yes, if Pangloss computes it | Memgraph built-in; Neo4j GDS | Memgraph Enterprise | Memgraph MAGE; elsewhere a Python library |

**Recommendation: FastRP**, computed by Pangloss, with its random start vector for each head seeded by a hash of the
head's UUID. That makes a vector depend only on the graph and not on the order of loading or on internal node ids, so a
rebuild gives the same vectors for unchanged neighbourhoods. node2vec can be added later as another `kind`, for anyone
who wants walk-based similarity and will pay for the batch.

**Text embeddings are a different similarity**, of what is said rather than who and what it is connected to. They would
suit documents with long text. The storage below has a `kind` for each, so a second kind (or a mix of the two, rank by
rank) can come later without changing the design. It is out of scope here, but Memgraph's image already carries
`sentence-transformers` and a working `embeddings` module.

**How local an update is, exactly.** With `k` FastRP iterations, a changed edge (u, v) changes the vectors of heads up
to `k - 1` steps from u or v. Recomputing those exactly needs the neighbourhood `2k - 1` steps out, which a hub (a
much-cited place, a typology type) makes large. So the on-write step is an **approximation**: the changed head and its
direct neighbours are recomputed from their neighbours' current vectors. A periodic full rebuild then corrects the
drift. Since the rebuild takes minutes at 500k nodes, that is affordable.

## Where the computing is done

| | A. The database's own algorithms | B. A custom Memgraph query module | C. Pangloss, in Python |
|---|---|---|---|
| Batch | `node2vec.set_embeddings`, `gds.fastRP.write` | A procedure that reads the head graph in place and writes vectors | Read the head graph by one query, compute with numpy/scipy, write in batches |
| On write | Re-run all (node2vec), or GDS on a projection | A `write_proc` (as the trial `pg_embed.fold_in`), from the worker or a trigger | The worker reads the neighbours' vectors by one query, computes, writes |
| Same code on both backends | No (different algorithms, Neo4j needs GDS) | No (Memgraph only; Neo4j would need Java) | **Yes**, through `Dialect` methods for the index DDL and the search |
| Deployment | Nothing extra (Memgraph); GDS plugin (Neo4j) | The `.py` file must be put into every Memgraph a project runs (image layer or mounted volume), and kept in step with the package's version | Nothing in the database |
| Head graph | Must be the stored graph or a materialised one: `project()` takes stored paths | Can be computed inside the procedure | Computed by the read query |
| Fits the principles | Against "add-ons run on any backend" | An exception, to be justified by numbers | Yes |

**Recommendation: C, with B kept as an optimisation for Memgraph.** The user expected a custom query module to be the
way on Memgraph. It works (the trial module loaded and ran), but measuring showed that computing is not where the time
goes. The data that a query module would avoid moving is the 14 s read, and the write costs more in either case. A
module also adds a deployment step to every project (`run_tests.sh`, the demo, the smoke tests, a production
`docker compose`), and Neo4j has no equivalent short of a Java plugin. If a measurement on real data later shows the
read to dominate, a module can do the batch read and the fold-in behind the same Python interface. A `Dialect` method
names it, and a capability says whether it is present. **Not measured:** how fast `mgp`'s Python iteration over 500k
vertices is. That decides whether B helps at all.

The batch is too heavy for the server's event loop, so it is a **`pangloss-admin` job** (a process of its own). The
fold-in is light, so it is a `BackgroundTask` worker.

## Where the vectors are kept

`(:PGEmbedding {kind, head_id, generation, vector, at})-[:embeds]->(head)`, one per head and kind. Not a property of
the head node, for three reasons found in the code:

- **An update replaces the head's properties.** `build_replace_head_query` does `SET head = …` and keeps only
  `KEPT_PROPERTIES` (review's fields). A vector there would be wiped by every save, or would need adding to the core's
  kept list, which is a package's name in the core.
- **Reads return every property of everything they touch.** `read_query.py` returns `properties(root)` and
  `properties(endNode(edge))` for each referenced entity. A factoid naming five people would carry five 128-float lists
  to the API, and the API would have to drop them. (Memgraph's `storage.omit_vector_index_properties_on_return` hides
  them only when whole nodes are returned, not from `properties()`.)
- **A separate node can carry its own labels**, which is how filtered search is done on Memgraph.

**Indexes.** On Memgraph a search cannot be filtered, so the embedding node also carries the head's class labels
(`PGEmbedding:Person`, `PGEmbedding:Factoid`), and there is:

- one index over all embeddings (`:PGEmbedding(vector)`), for "anything like this", and
- an index for each class that a project asks to be searchable on its own, `:PGEmbedding&Person(vector)` (Memgraph
  allows `&` for nodes; not tried). A vector in several indexes is kept in each.

On Neo4j one index with a filter property (`WITH [e.kind, e.head_type]`) does it, and the class can be filtered in
`SEARCH … WHERE`.

**Generations.** A full rebuild writes a new `generation` of vectors, switches a pointer
(`(:PGEmbeddingState {kind, generation})`), and deletes the old generation. Searches read the current generation, so
there is never a half-rebuilt space. Two generations mean twice the memory for the duration (about 1 GB at 320k × 128
× f32, plus the index's graph).

**Dimension and metric.** 128 and cosine to start. `scalar_kind: 'f16'` halves the memory on Memgraph and is worth
measuring for recall. The dimension is fixed in the index, so changing it is a rebuild with a new index, which a
migration does.

## The batch: building every vector

An admin job, `embeddings rebuild [--kind fastrp]`, also a CLI command:

1. Read the head graph (with the visibility rules and the project's exclusions) in pages (`UNWIND`/`SKIP` by id range,
   not one 600k-row result), with field names if weights are used.
2. Build the sparse matrix, seed each head from its UUID, run FastRP (numpy/scipy; vectorise the seeding, which was
   the slowest Python step at 3.5 s).
3. Write the new generation in batches of about 10,000 (`UNWIND $rows … CREATE (:PGEmbedding …)-[:embeds]->(h)`),
   with **no index on the new generation yet** (or an index created after the write, then the switch).
4. Switch, drop the old generation, record when and how many in `PGEmbeddingState`.

Expected time at 520k nodes from the measurements: about 2 minutes, most of it the write. A bulk load into an empty
Memgraph (`pangloss memgraph bulk-load`) could run it at the end.

Where numpy/scipy come from: they are not in the workspace today. `pangloss-similar` would depend on them, which
adds about 60 MB to a server install and nothing to a client of the SDK (the SDK only calls the route).

## On write: keeping vectors current

The requirement is "on write, ideally not recalculating everything". The parts already exist in the core:

1. **`hooks.pending_work`**: a write of a head whose class is embedded leaves a `(:PGPending {kind: "embed",
   head_id})` in the write's own transaction (`pangloss_cypher.pending`). It cost `pangloss-derived` 0.1-0.9 ms a save.
   A delete, an undelete and a publish leave one too.
2. **A worker** (a `BackgroundTask` from `pangloss-similar`'s `configure_app`) claims pending heads in batches, as
   `pangloss_derived.worker` does, and for each:
   - reads its neighbours in the head graph and their current vectors (one query);
   - computes its vector as their normalised mean (mixed with its old vector if it has one, by a setting);
   - recomputes its direct neighbours the same way (one more step), capped for hubs: a neighbour of degree above a
     setting is left to the rebuild;
   - writes the vectors **in place** (`SET e.vector = …`, which avoids the deleted-node gotcha above).
3. **A staleness count** in `PGEmbeddingState` (heads folded in since the last rebuild). The admin page shows it, and a
   setting can start a rebuild past a threshold or at an hour.

**Cold start.** A head whose neighbours have no vectors gets none (seen in the trial: a new factoid naming only people
outside the space). Two fixes, both cheap: give it its seeded FastRP start vector propagated over its own
neighbourhood (an exact FastRP for a tiny subgraph), or leave it out of results until the next rebuild. The first is
better and is FastRP's advantage.

**A Memgraph trigger instead of the queue?** `CREATE TRIGGER … AFTER COMMIT EXECUTE CALL pg_embed.fold_in(…)` would
work on Memgraph only, needs the query module, and sees raw created and deleted nodes, not "this head was saved". An
update deletes and re-creates a tree, which a trigger would see as noise. The queue is backend-neutral and already
built, so use the queue.

## Who may see what

- **Deleted heads** (`deleted: true`) are left out of the head graph and have their vectors removed. Entities
  `marked_for_deletion` stay, since they are still referred to.
- **Search results** go through `fragments.visible(item)` and `not_deleted` after the vector search, so the search
  overfetches (k × 2, say) and cuts. The interface never sees an item it could not read.
- **Unpublished documents** (`pangloss-review`) are hidden from readers who are not logged in. If they are in the head
  graph, they shape published items' vectors: a reader could learn that two published people are close because of an
  unpublished factoid. Not much is revealed that way, but something is. Leaving them out until published is the
  conservative choice, at the cost of reviewers not seeing their effect. **A decision for the user.**
- **History**: vectors are derived and rebuildable, so `pangloss-history` does not record them, and no write event is
  raised for them (they are not model data, like derived facts).

## Declaring it in a project

A meta slot, as other packages do (`register_meta_slot("_similar_meta", SimilarMeta)`):

```python
from pangloss_similar import SimilarMeta, Weight

class Person(Entity):
    _similar_meta = SimilarMeta(searchable=True)          # embedded, and an index of its own

class Factoid(Document):
    _similar_meta = SimilarMeta()                        # embedded, searchable only among everything

class Occupation(Entity):                                # a typology
    _similar_meta = SimilarMeta(include=False)           # no vector, and not an edge in anyone's neighbourhood

class Birth(Document):
    place: Annotated[Place, Weight(2.0)]                 # a field counts more
```

Inherited, as meta slots are; the default (embed every document and entity, weight 1) is a setting. Settings:
`SIMILAR_DIMENSION`, `SIMILAR_ITERATION_WEIGHTS`, `SIMILAR_REBUILD_AFTER` (heads folded in) and `SIMILAR_REBUILD_AT`
(a time). Changing the dimension or the classes indexed is a migration of the package (it makes or drops the
indexes). Changing weights or exclusions means a rebuild, which `pangloss check` could warn of.

## API, SDK and interface

- **`GET /api/{NAME}/{id}/similar?kind=fastrp&type=Person&limit=20`**: a list of `{item: ReferenceView, similarity}`.
  `type` picks the index (any class with `searchable=True`, or all); unknown parameters are refused as elsewhere.
  It answers 404 for an item the reader cannot see, and an empty list with `"pending": true` for an item not yet
  embedded.
- **`GET /api/similar/status`**: generation, when it was built, how many are stale, whether a rebuild is running.
- **The SDK**: an operation `Model.similar(id, …)` with its SDK side and a contract test (an operation on the models
  needs both). Or, simpler, the route only and no model method, as `pangloss-derived`'s reads are.
- **The interface**: an interface module with an `itemSections` entry, "Similar", on the item page. It shows a list of
  **`ReferenceChip`s** with a similarity bar, a type filter (the existing `MenuSelect`), fetched on its own as
  `IncomingRelations` is. Its strings are `t()` slots with translations, and it gets a row in `e2e/COVERAGE.md`. An
  admin `slots` entry shows the status and a Rebuild button (the job). Later: "similar to" as a search filter, and
  two-item "why are these close" (the shared neighbours, which the head graph gives directly).

## Neo4j

With option C nothing beyond the vector index is needed, and Neo4j Community has one. What differs is behind two
`Dialect` methods:

- `vector_index_ddl(name, labels, property, dimension, metric)`: Memgraph's `WITH CONFIG {…}` against Neo4j's
  `OPTIONS {indexConfig: {…}}` (plus `db.awaitIndexes()` on Neo4j, whose indexes populate in the background);
- `vector_search(index, k, vector, filter)`: `CALL vector_search.search(…)` against `SEARCH … IN (VECTOR INDEX …)`. On
  Neo4j the class filter goes into the index; on Memgraph it picks the index.

GDS is optional. A Neo4j project that has it could do the batch with `gds.fastRP.write` (1.4 s in the trial, as against
about 100 s by option C, almost all of it moving data), behind the same job, if the capability says GDS is there. But
GDS seeds FastRP by its internal node ids, so its vectors would differ from Pangloss's own, and the fold-in would have
to match its normalisation. That is worth doing only if Neo4j projects grow large.

## What would be built

| Where | What |
|---|---|
| `packages/pangloss-similar` (new) | `SimilarMeta`, `Weight`; the head-graph read; FastRP; the generation switch; the rebuild job (`admin.py`) and command (`cli.py`); the worker; routes; migrations (index DDL through the dialect); translations; an interface module; `requires = {"cypher"}` (plus the new capability) |
| `pangloss-cypher` `Dialect` | `vector_index_ddl`, `vector_search`, and the Memgraph and Neo4j implementations of each |
| `pangloss-core` `Capabilities` | `vector_index: bool` (both backends true; the SDK false) |
| `pangloss_models.hooks` | Nothing new: `pending_work` and `after_write` are enough. A `Weight` marker in `Annotated` is refused today unless it is pydantic's or Pangloss's: it needs the way packages' markers are let through checked, or the weights put in `SimilarMeta(weights={"place": 2.0})` instead |
| `pangloss-testing` | A conformance-style test of the package on both backends: build, search, fold-in after a save, delete leaves results, unpublished not visible |
| `pangloss-sdk` | The operation's HTTP side, if a model method is chosen |
| Deployment | numpy and scipy in the server's dependencies. No change to the database images for option C |
| Docs | This page as the plan with "As built" sections; `status.md`; a guide page; the skill's package table |

Rough order: (1) the head-graph read and FastRP as a CLI command against a scratch copy of the demo, with an evaluation
(next section) before anything else; (2) storage, indexes, the route; (3) the worker; (4) the interface section; (5)
weights and exclusions; (6) Neo4j and the conformance test.

## Decisions for the user

1. **The head graph**: contract each head's tree (recommended), or embed the stored graph and keep only head vectors.
2. **FastRP by Pangloss** (recommended), or node2vec in the database, or both as two kinds.
3. **A Memgraph query module** now, or only if measurement on real data asks for it (recommended: later).
4. **Unpublished documents** in the graph or not (recommended: not, until published).
5. **Which classes get an index of their own** by default: none, entities only, or every class.
6. **Typology and other vocabulary entities**: in the graph at weight 1, at a lower weight, or out by default.
7. **A model method** (`Person.similar(id)`) with an SDK side, or only the route.
8. **Text embeddings** as a second kind now, later, or not at all.
9. **Neo4j with GDS**: use `gds.fastRP` when present, or always the one implementation.

## What is not known yet

- **Whether the vectors are any good.** The synthetic graph cannot say. A test: hold out known pairs and see whether
  the vectors rank them high. Candidates for the pairs are identifications in `pangloss-review` and
  `pangloss-library`'s `Identification` (two mentions of one person), derived `SameGroup` facts, and people in the same
  family. This is the first thing to do on real data, before building storage or interface.
- The cost on **real data of about 640,000 nodes** with its hubs (places, vocabularies), and the fold-in's cost at a
  hub.
- How fast `mgp`'s Python iteration is over the whole graph (which decides whether option B helps).
- `scalar_kind: f16` or `i8` recall, and the memory of two generations.
- Whether GDS's `node2vec` is deterministic with more than one worker, and whether Memgraph's is.
- What the vector index costs a write under concurrent writers. The text index costs per commit (`memgraph.md`,
  `large-data.md`); the vector index was only measured in batches, and the fold-in worker writes in small ones.

## Sources

- Memgraph: [node2vec](https://memgraph.com/docs/advanced-algorithms/available-algorithms/node2vec),
  [node2vec_online](https://memgraph.com/docs/advanced-algorithms/available-algorithms/node2vec_online),
  [vector search](https://memgraph.com/docs/querying/vector-search),
  [custom query modules](https://memgraph.com/docs/custom-query-modules),
  [Python API](https://memgraph.com/docs/custom-query-modules/python/python-api),
  [triggers](https://memgraph.com/docs/fundamentals/triggers),
  [knn](https://memgraph.com/docs/advanced-algorithms/available-algorithms/knn).
- Neo4j: [vector indexes (Cypher 25)](https://www.neo4j.com/docs/cypher-manual/25/indexes/semantic-indexes/vector-indexes/),
  [GDS FastRP](https://neo4j.com/docs/graph-data-science/current/algorithms/fastrp/),
  [GDS editions](https://neo4j.com/docs/graph-data-science/current/introduction/),
  [GDS installation](https://neo4j.com/docs/graph-data-science/current/installation/),
  [GDS and Neo4j versions](https://neo4j.com/docs/graph-data-science/current/installation/supported-neo4j-versions/).
- In this repository: `pangloss_cypher/build_update_query.py` (`KEPT_PROPERTIES`, the head replace),
  `pangloss_cypher/read_query.py` (what a read returns), `pangloss_cypher/pending.py` and `implementation_docs/derived.md`
  (the queue and the worker), `implementation_docs/admin.md` (jobs).
