# Similarity: scratch work

Trial code and measurements for [the similarity build plan](../../implementation_docs/similarity-build-plan.md).
Kept here, never only in `/tmp` (the trial code of 2026-11-11 was lost that way).

| File | What |
|---|---|
| `wrapper_walks.py` | The planted test of 2026-11-20: wrappers walked or hopped over, shares, a wrapper's own relations (numpy only) |
| `stored_shapes.py`, `stored_shapes.txt` | Step 0.1: what each shape the joined graph has a rule for is stored as, and what the script printed on 2026-11-20 (lines cut at 600 characters). The models are `pangloss_testing.similar_models` |
| `profile_recall.py` | Step 2.4's question, measured before 2.2 (2026-11-21): which index layout finds the nearest when a profile weighs the parts. Findings below |
| `hierarchy.py`, `hierarchy.txt` | Step 2.3's planted test of the class part, written again (2026-11-21; it imports `fastrp` of `wrapper_walks.py`). The pattern of the first one holds on new made-up data: a document's nearest of other classes are of a parent, child or sibling class 35% by the graph alone, 48% with the hierarchy at decay 0.5 and weight 0.1, 69% at 0.3. The figures of 2026-11-11 (64% to 76%) were of data that is lost |
| `deleted_in_index.py`, `.txt` | Step 2.4: how long deleted nodes keep their places in a Memgraph vector search with nothing done to hurry it. 150 of 200 deleted, the nearest ones: a search for 10 gave none, and for 40 none, until the database's own collection ran, **21.7 s** later (its cycle is 30 s by default); then all 10. So `nearest` asks again for four times as many while it is short, until it has asked for more than the profile's state says there are |
| `reader_trial.py`, `.txt` | Step 3.3: the five queries of the graph part's reader, tried on `:7702` over the stored shapes, with their plans (2026-11-21). Each starts from an index (`PGIndexableNode(id)`, `HeadNode(id)`, `PGCitation(target_id)`); the page of all nodes is read in the order of the id index with no sort. Seen besides: a head has no `head_node_id`; `published` and `deleted` are absent until set; a forward edge has no `reverse` at all; a citation of a derived document has the label `PGUnprotectedCitation` and **not** `PGCitation`, so the citations of an id are asked of both labels. Not tried on Neo4j (`:7703` is empty): its live tests and 3.5 do |
| `vector_index_trial_3.py`, `.txt` | Step 2.2's trials: a vector index made again with another dimension, and after a recovered snapshot |
| `vector_index_trial.py`, `vector_index_trial_2.py`, `vector_index_trial.txt` | Phase 1's trials by hand (steps 1.3 to 1.5), on `:7702` and `:7703`, and what they printed. Findings below |

## What phase 1's trials found (2026-11-20; Memgraph 3.14.0, Neo4j 2026.10.1 community)

**A vector index**

| | Memgraph | Neo4j |
|---|---|---|
| Create | `CREATE VECTOR INDEX name ON :Label(property) WITH CONFIG {"dimension": 4, "capacity": 16, "metric": "cos"}`, in a transaction of its own (auto-commit) | `CREATE VECTOR INDEX name IF NOT EXISTS FOR (n:Label) ON (n.property) OPTIONS {indexConfig: {`vector.dimensions`: 4, `vector.similarity_function`: 'cosine'}}`, then `CALL db.awaitIndexes(60)` |
| Created again | **No error and nothing made**: the same name again, a second name on the same label and property, the same name on another label, all silent. Whether it is there has to be read from the list | `IF NOT EXISTS` |
| Listed | `SHOW VECTOR INDEX INFO` (`index_name`, `label` with its colon, `property`, `capacity`, `dimension`, `metric`, `size`); **not** in `SHOW INDEX INFO` | `SHOW INDEXES YIELD name, type, labelsOrTypes, properties, options WHERE type = 'VECTOR'` (`options.indexConfig`) |
| Dropped | `DROP VECTOR INDEX name` (no error if it is not there) | `DROP INDEX name IF EXISTS` (an error without `IF EXISTS`) |
| Capacity | **Not a limit.** 16 asked gives 64; 100 nodes made it 256, 5,100 made it 16,384. It is where the index starts | None |
| A vector of the wrong length | The write is refused ("must have the same number of dimensions") | Written, and silently not in the index |
| Search | `CALL vector_search.search('name', k, vector) YIELD node, similarity, distance`: `distance` **is 1 − cosine**; `similarity` is the *size* of the cosine (1.0 for a vector pointing the opposite way: seen 2026-11-20 with `[1, 0]` against `[-1, 0]`, distance 2.0, similarity 1.0), so the cosine is taken as `1 - distance` | `CALL db.index.vector.queryNodes('name', k, vector) YIELD node, score`: `score` **is (1 + cosine) / 2**. The `SEARCH` clause gives the same |
| A node just deleted | **The search still gives it, and reading a property or the labels of it fails the whole query** ("Trying to get a property from a deleted object"), in a later transaction too, until the database collects it (`FREE MEMORY` does). `id(node)` can be read: `WITH id(node) AS i, similarity MATCH (n) WHERE id(n) = i` drops it and is safe. **It still takes one of the `k` places**, so a search can give far fewer than `k`, even none, after many deletes, and an index made after the deletes holds them too | Not given; `k` is counted before, so 3 asked can give 2 |
| A vector set in place, the property or the label removed | Seen by the next search; the index's `size` follows | Seen by the next search |
| The indexed property | Can be read back (`n.vector`, `properties(n)`) | Can be read back |

**A query module of Memgraph** (`mg.create_module_file`, `mg.update_module_file`, `mg.get_module_file`): a module
**can import another module file** beside it, is callable as soon as it is created, and a change to the imported file
is seen by the importer at once. The text read back is the text written. numpy 2.2.6 and scipy 1.13.1 import. **A
module that fails to import fails silently**: the file is made, it has no procedures, `mg.load` of it says only
"Unable to unload module", and the reason is in the database's log alone. So an install is checked by asking
`mg.procedures()` for the module's names. These procedures, like the DDL, are refused in a transaction of several
commands.

## Which index a profile searches (2026-11-21; `profile_recall.py`, `:7702` and `:7703`)

100,000 made-up items: a graph part of 128 dimensions in 2,000 clusters, a class part as step 2.3 makes it (63
classes in a tree, a few holding most items). Recall of the 10 nearest by the weighted sum of the parts' cosines,
200 queries, the index asked for 4 times as many (10 times in brackets). Every search took 1 to 7 ms.

| Profile | One index of whole vectors, the query rescaled | An index for each part, merged | An index for each profile, vectors scaled before storing |
|---|---|---|---|
| graph 1, class 0.1 | Memgraph 0.34 (0.39); Neo4j 0.58 (0.71) | 0.95 (1.00) on both | 0.97 (1.00) on both |
| graph 1, class 1 | 0.92; 0.66 (0.77) | 0.36 (0.67); 0.37 (0.61) | 0.92 (0.93); 0.98 (0.99) |
| graph only | 0.18; 0.50 | 1.00 | 1.00 |
| class only | 0.99 | Memgraph 0.73; Neo4j 0.99 | Memgraph 0.73; Neo4j 1.00 |
| graph 0.1, class 1 | 0.96; 0.04 | 0.34; 0.35 | 0.97 (0.98); 0.98 (0.99) |

- **One whole index fails** where the profile is unlike what is stored: the index's own graph is knit by class,
  and a query with little class in it is caught in one class's corner. Asking for more does not help.
- **An index for each part fails for balanced profiles**: the nearest by the sum are near the top of neither part
  alone (the class index gives any of thousands of items of the same class).
- **An index for each profile holds** (0.92 and up), since the query is made as the stored vectors are. So this is
  what 2.2 builds: the parts stored apart, unindexed, and for each profile a vector of the parts scaled by its
  weights, indexed.
- **Neo4j's figures in the last column are with `vector.quantization.enabled: false`.** With the default
  (quantized) they are 0.71 (0.83) for graph 1, class 1 and 0.05 for graph 0.1, class 1. The index is made without
  quantization.
- **Memgraph, class only: 0.73.** Thousands of identical vectors are more than its index finds its way among. A
  profile of the class part alone is weak on Memgraph at this size; any weight of graph beside it mends it (0.97).
- **Memgraph refuses to make a vector index while any node of the label has the property at another length**,
  nodes just deleted included, until the database collects them (`vector_index_trial_3.py`, `.txt`; what looked at
  first like an index keeping its old dimension). With the property removed, or after `FREE MEMORY`, it is made.
  A class added changes the class part's dimension, so **the label and the name of a profile's index carry the
  dimension** (`PGV_default_191`): vectors of another length are never under the label an index is made on.
- **A vector index survives a recovered snapshot** on Memgraph (same trial): listed, searched and written to
  after `RECOVER SNAPSHOT`, with the size of the snapshot. `pangloss restore` needs nothing for it.

## Step 3.5: the graph part at size (2026-11-21; Memgraph, `:7690`)

`measure.py` (reads only), from the demo copy with the two packages installed; `measure_memgraph_*.txt`,
`measure_rebuild_graph.txt`, `steps_planted.py` and `.txt`.

- **The data is nearly all unpublished** (193,685 documents unpublished, 36,946 deleted, 66,794 in): under
  `VECTORS_GRAPH_SEES = "everyone"` 3,050 stops are joined to anything. Everything below is with `"logged_in"`.
- **The graph**: 655,971 nodes and 1,030,449 forward edges read; 260,479 stops; 408,871 joins among 257,255 of
  them. A stop has 3 joins at the median, 7 at the 99th percentile; one Zotero source has 19,766, and some people
  about 3,000.
- **Without writing**: reading 37.0 s (66 pages of 10,000 nodes with their edges, about 0.55 s each), the joins
  2.0 s, FastRP 1.0 s.
- **A whole rebuild, written and indexed** (`pangloss vectors rebuild`): 240 s. The class part 18 s (173,564
  heads), the graph part 93 s (257,255 vectors), the profile combined twice, 46 s and 83 s.
- **What a refresh of one document reads** (500 documents; the stops within `2k − 1` joins):

  | Steps | Median | 90% | Most | Past the cap of 50,000 |
  |---|---|---|---|---|
  | 2 | 56 | 39,542 | 39,547 | 0% |
  | 3 (the default) | 1,027 | 51,628 | 52,782 | 12% |
  | 4 | 8,014 | 67,125 | 96,025 | 32% |
  | 3, the most joined 0.1% of stops (257) left out | 151 | 341 | 546 | 0% |

  A refresh in memory, capped: 298 ms on average.
- **The planted quality by steps** (`steps_planted.py`: of a person's 10 nearest, the share of their family;
  chance 1%): `[0, 1]` 15.0%, `[0, 1, 1]` 19.2%, four steps 31.0%, six 42.2%, eight 47.4%; `[0, 0, 1]` 24.1%.
- **Found by the count**: the class part gives vectors to heads only (173,564) and the graph part to nested
  documents too (257,255), and the search gives heads only. Mended after 3.5 (the plan's "As built").
- **Not measured**: Neo4j at size (no large Neo4j database of today's models; the demo's `bulk_load.py` through
  the models is the way, not done); shares, citation joins and vocabularies on and off for quality (this data has
  no truth to rank against).

## The scratch databases (step 0.2, 2026-11-20)

None of these is the tests' (`:7687`, `:7693`, `:7711` and up) or the demo's (`:7688`).

| Container | Port | What is in it | State |
|---|---|---|---|
| `pangloss-memgraph-similar` | 7702 (test/test) | What `stored_shapes.py` wrote: it empties the database each run | Running. `docker rm -f` it when the work is done |
| `pangloss-neo4j-similar` | 7703 (neo4j/test-password) | Nothing (phase 1's trials clean up) | Running. `docker rm -f` it when the work is done |
| `pangloss-memgraph-identity` | 7690 (test/test) | 1,026,342 nodes of the demo's models: 60,000 people, 75,556 factoids, 36,285 derived factoids, 5,000 Zotero objects (the bulk load of 2026-11-13 and what later measuring left) | Migrated on 2026-11-20 to today's models (six migrations: the edge-model types, criteria, `0023_describable_person`), with a snapshot first. Stop it when not measuring (`docker stop`); before `docker start`, raise `vm.max_map_count` (implementation_docs/large-data.md) |
| `pangloss-compare-api-neo4j-core` | 7698 (neo4j/test-password) | 118,173 nodes written by `pangloss-demo/compare_api.py` on 2026-10-30: 12,012 people, 6,006 factoids, of the models of that day, **with no record of migrations** | **Not usable as it is**: it cannot be migrated to today's models. Left as found, stopped |

The project the migrations were run from is a copy of the demo with its `DB_URL` changed to `:7690`
(`/tmp/similar-demo`, made by `rsync -a --exclude .venv pangloss-demo/ /tmp/similar-demo/`; it may vanish, and is one
command to make again). Never point it at `:7688`.

**The large Neo4j database is still to be made.** The file the Memgraph one was loaded from is gone
(`/tmp/idmeasure/gen.py`). Step 3.5 needs the same data on both backends, so its first task is a generator kept
here (`gen.py`: entities with ids of their own, then factoids, as JSON Lines), loaded by
`pangloss neo4j bulk-load` and, for a Memgraph of the same data, `pangloss memgraph bulk-load`.
