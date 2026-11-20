# Similarity: scratch work

Trial code and measurements for [the similarity build plan](../../implementation_docs/similarity-build-plan.md).
Kept here, never only in `/tmp` (the trial code of 2026-11-11 was lost that way).

| File | What |
|---|---|
| `wrapper_walks.py` | The planted test of 2026-11-20: wrappers walked or hopped over, shares, a wrapper's own relations (numpy only) |
| `stored_shapes.py`, `stored_shapes.txt` | Step 0.1: what each shape the joined graph has a rule for is stored as, and what the script printed on 2026-11-20 (lines cut at 600 characters). The models are `pangloss_testing.similar_models` |

## The scratch databases (step 0.2, 2026-11-20)

None of these is the tests' (`:7687`, `:7693`, `:7711` and up) or the demo's (`:7688`).

| Container | Port | What is in it | State |
|---|---|---|---|
| `pangloss-memgraph-similar` | 7702 (test/test) | What `stored_shapes.py` wrote: it empties the database each run | Running. `docker rm -f` it when the work is done |
| `pangloss-memgraph-identity` | 7690 (test/test) | 1,026,342 nodes of the demo's models: 60,000 people, 75,556 factoids, 36,285 derived factoids, 5,000 Zotero objects (the bulk load of 2026-11-13 and what later measuring left) | Migrated on 2026-11-20 to today's models (six migrations: the edge-model types, criteria, `0023_describable_person`), with a snapshot first. Stop it when not measuring (`docker stop`); before `docker start`, raise `vm.max_map_count` (implementation_docs/large-data.md) |
| `pangloss-compare-api-neo4j-core` | 7698 (neo4j/test-password) | 118,173 nodes written by `pangloss-demo/compare_api.py` on 2026-10-30: 12,012 people, 6,006 factoids, of the models of that day, **with no record of migrations** | **Not usable as it is**: it cannot be migrated to today's models. Left as found, stopped |

The project the migrations were run from is a copy of the demo with its `DB_URL` changed to `:7690`
(`/tmp/similar-demo`, made by `rsync -a --exclude .venv pangloss-demo/ /tmp/similar-demo/`; it may vanish, and is one
command to make again). Never point it at `:7688`.

**The large Neo4j database is still to be made.** The file the Memgraph one was loaded from is gone
(`/tmp/idmeasure/gen.py`). Step 3.5 needs the same data on both backends, so its first task is a generator kept
here (`gen.py`: entities with ids of their own, then factoids, as JSON Lines), loaded by
`pangloss neo4j bulk-load` and, for a Memgraph of the same data, `pangloss memgraph bulk-load`.
