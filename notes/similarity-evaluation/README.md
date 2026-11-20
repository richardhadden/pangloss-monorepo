# Similarity: scratch work

Trial code and measurements for [the similarity build plan](../../implementation_docs/similarity-build-plan.md).
Kept here, never only in `/tmp` (the trial code of 2026-11-11 was lost that way).

| File | What |
|---|---|
| `wrapper_walks.py` | The planted test of 2026-11-20: wrappers walked or hopped over, shares, a wrapper's own relations (numpy only) |
| `stored_shapes.py`, `stored_shapes.txt` | Step 0.1: what each shape the joined graph has a rule for is stored as, and what the script printed on 2026-11-20 (lines cut at 600 characters). The models are `pangloss_testing.similar_models` |
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
