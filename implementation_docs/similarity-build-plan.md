# Similarity: the build plan ⏳

Written 2026-11-20. **Nothing here is built.** [graph-embeddings.md](graph-embeddings.md) holds the design, the
measurements and the decisions; [similarity-plan.md](similarity-plan.md) holds the packages, the hooks and the
stages. This page is what is built from them, step by step: what each step changes and where, the tests that say it
is done (by file), what is measured, and who builds it. Phases 1 to 7 are the base (vectors, the graph part, kept
current, shown in the interface) and are planned in full. Phases 8 to 13 (names, time, reconciliation, comparison,
learning) are planned in outline: each gets its steps written when it is reached, because phase 3's measurements
decide their order.

## Contents

- What is taken as settled
- How the work is run
- Phase 0: the ground
- Phase 1: the core hooks
- Phase 2: `pangloss-vectors`
- Phase 3: `pangloss-fastrp`, the Python engine
- Phase 4: the Memgraph engine
- Phase 5: keeping vectors current
- Phase 6: the interface
- Phase 7: the demo and the docs
- Phases 8 to 13, in outline
- Who builds each step
- What can go wrong

## What is taken as settled

Decided by the user (2026-11-11 and 2026-11-20; the investigation's "Decisions for the user"): FastRP; a module in
Memgraph and the same maths in Python; vectors on their own nodes; per-class weights by `type`; the class part with
`SemanticTrait`; wrappers hopped over; shares by `SumsTo`; computed candidates followed at a share; a wrapper's own
relations joined to the document; citations join; derived documents out; no typed joins; `SIMILAR_GRAPH_SEES`.

**Taken here so that building can start** (they were the decisions still open in the two pages). **Confirmed by the
user, 2026-11-20**, all of them; so is the pause after each phase, not each step, and that the phase branches are
taken from `graph-embeddings-update`:

| Open decision | Taken as | Where it bites |
|---|---|---|
| Package names | `pangloss-vectors`, `pangloss-fastrp` (settings `VECTORS_*`, `FASTRP_*`; `SIMILAR_GRAPH_SEES` becomes `VECTORS_GRAPH_SEES`) | 2.1, 3.1 |
| The meta slots | `_vectors_meta = VectorsMeta(searchable=, include=)` in `pangloss-vectors`; `_fastrp_meta = FastRPMeta(weight=, weights=, stop=, own=, through=)` in `pangloss-fastrp`. The investigation's single `SimilarMeta` is split by owner, as the plan's "each package owns its settings" asks | 2.2, 3.1 |
| Containment | A nested document is joined to the one it is in | 3.1 |
| The default walk | Every wrapper kind is hopped over; a project puts `stop` on its `Negative` (the demo does, in phase 7) | 3.1, 7.1 |
| Indexes | One over all vectors of a part, and one for each class with `searchable=True` (the demo: `Person`, `Statement`) | 2.2 |
| Vocabularies and typologies | In, at weight 1; measured in 3.5 before any default changes | 3.5 |
| Past the hub cap | Approximate now, count as stale, rebuild later | 5.3 |
| A model method | The route only; `Model.similar()` and the SDK later | 2.5 |
| The 100,000-record fault | Worked round (a write procedure); a strict `xfail` says when it is fixed. Not reported to Memgraph until the user says | 4.2 |
| Real data for the evaluation | Not waited for. Phase 3 measures on the scratch database of 590,000 nodes of the demo's models (`pangloss-memgraph-identity`, `:7690`) and on planted data. The script takes any database, so a copy of a real project is one command when there is one | 3.5 |

## How the work is run

- **Branches**: one for each phase, from `dev` (`vectors-1-hooks`, `vectors-2-package`, …), merged into `dev` when
  its last step is green.
- **Commits**: one for each step, pushed. **A pause for the user's go-ahead after each phase**, and inside a phase
  wherever a step says "decide". (The relation-steps work paused after every step; with 30 steps here a phase is
  proposed as the unit. Say if it should be the step.)
- **A session can stop at any moment** (the five-hour usage limit ends a turn where it stands, and the session
  cannot see how much is left). So that a stop costs at most the step in hand:
  - a step is committed and pushed as soon as it is green, never held for the next;
  - **the resume line** is brought up to date in the same commit: "Where the work stands" at the foot of this
    page (the step just finished, the next one, anything half done and where it is), and the same in the memory
    note. A new session told "continue the similarity build plan" starts from that line;
  - **a budget the user sets is kept**: "stop after this step", or "at most two steps this session", ends the
    session cleanly at that step's commit, with the resume line written. Nothing is scheduled to resume by itself:
    a cloud agent has neither the local databases nor the checkout;
  - work given to an agent that had not reported when a session stopped is not trusted: the next session reads
    `git status` and the diff, and gives the step out again from its brief if the work is partial.
- **Docs with the code**: each step that changes what a user or a package author types updates its page in the same
  commit, and an "As built" section here says where the code differs from the step.
- **Test runs** (the traps are known): under `caffeinate -is`; never two database runs at once; scratch work on its
  own container and port, never `:7687` (tests) or `:7688` (the demo); a new package's `tests/live` is added to the
  Neo4j list in `run_tests.sh` (lines 104-109 and the header) in the step that creates it.
- **Three kinds of test**, named in every step:
  - *pure*: no database (`tests/unit`), numpy at most; the maths and the maps;
  - *live*: `tests/live`, on Memgraph and on Neo4j, with the fixtures of `pangloss_testing.live`;
  - *conformance*: `pangloss_testing/conformance/`, for what the core gains.
- **The oracle.** Nearly every graph test has the same form: build the vectors two ways and compare. The slow, plain
  way is `rebuild` by the pure Python maths on a graph held in memory. Everything else (the Cypher reader, the
  Memgraph module, `refresh`, `overlay`) must give the same vectors to 10⁻⁵. So one fixture, `oracle(graph)`, is
  written first (3.2) and used by phases 3, 4 and 5.

## Phase 0: the ground

Small, and done by main before any agent is briefed, because the briefs quote its results.

**0.1 What is stored, seen.** The storage table of the investigation was read from the code, not run. A scratch
script (`notes/similarity-evaluation/stored_shapes.py`) writes, on a scratch Memgraph, one document of each shape the
rules name, and prints its nodes and edges: `Agent | Identification[WeightedAlternative[Person]]` inside a
`Negative`; a class below `InRole`; a wrapper with a relation of its own; a field that subclasses a parent's; a
`MatchesCriteria` evaluated by its worker; a `Cites`; a merged entity; a derived shortcut and a derived document.
- **Done when** each row of the table is confirmed or corrected in the investigation, and the models are kept as
  `packages/pangloss-testing/src/pangloss_testing/similar_models.py` (the models every later live test uses).

**0.2 The scratch databases.** Start `pangloss-memgraph-identity` (`:7690`, 590,000 nodes of the demo's models) and
the Neo4j container on `:7698`; migrate both to today's models on a copy if the migrations are behind (the edge-model
types). Note their state in `notes/similarity-evaluation/README.md`. If either is beyond repair, a fresh bulk load
of `populate` data scaled up is 0.2's fallback.

### As built (2026-11-20)

- **0.1** is done. `notes/similarity-evaluation/stored_shapes.py` writes the shapes on a scratch Memgraph
  (`pangloss-memgraph-similar`, `:7702`) and prints them; what it printed is `stored_shapes.txt` beside it. Every
  row of the investigation's table held; what the run added is its paragraph "Seen, 2026-11-20" (a
  `ReifiedRelationDocument` has no `Document` label; `pg_edge_model` only where there is an edge model; a citation
  has `target_head_id` too; the node of a derived edge points at its entities by forward edges; what a merge
  leaves). The models are `pangloss_testing.similar_models.declare()`, which wants the apps `pangloss_derived`,
  `pangloss_library` and `pangloss_criteria` installed.
- **Not in the models**: a computed edge with `seen_by: "logged_in"`, an unpublished document (no review in them),
  and a merge between two alternatives of one `WeightedAlternative` (refused by the merge). 3.3's live tests add
  review to the installed apps for the first two.
- **0.2**: the Memgraph of `:7690` has 1,026,342 nodes and was six migrations behind; migrated in place, with a
  snapshot first. **The Neo4j of `:7698` cannot be used**: 118,173 nodes of the models of 2026-10-30, written by
  `compare_api.py` with no record of migrations. The fallback (a fresh load) is not done here, because the file the
  Memgraph data came from is gone too: **3.5 begins by writing a generator** (`notes/similarity-evaluation/gen.py`)
  and loading its file into a Neo4j with `pangloss neo4j bulk-load`. The state of each container is in
  `notes/similarity-evaluation/README.md`.
- `notes/**` is now among the paths `ty` checks loosely (`pyproject.toml`): `wrapper_walks.py` imports numpy, which
  the workspace has not got, and the type check of `./run_tests.sh` failed on it.
- Phase 0 was committed on `graph-embeddings-update`, which holds these pages and is not in `dev`. The phase
  branches are taken from it (or from `dev` once it is merged there: the user's call).

## Phase 1: the core hooks

Five small things, none knowing of similarity. Branch `vectors-1-hooks`.

**1.1 `SemanticTrait` and `SemanticNonHeritableTrait`.**
- *Where*: `pangloss_models/model_bases/trait.py` (two classes below `Trait` and `NonHeritableTrait`), exported from
  the package root; `utils.py` gains `model_is_semantic_trait`; `export.py` (the per-model `traits` list stays, and
  a `semanticTraits` list is added beside it); the interface's types for the export; `typestubs.py` needs nothing
  (checked by a test). `model_is_trait` already takes them.
- *Pure tests* (`pangloss-models/tests/initialisation/test_semantic_traits.py`): labels are as for any trait; a trait
  below a semantic trait is semantic; `SemanticNonHeritableTrait` labels only the class that names it; the export
  lists them; the stubs compile; a plain `Trait` is in `traits` and not in `semanticTraits`.
- *Docs*: `models.md` (traits), the guide's modelling page, the skill's modelling reference.

**1.2 Capabilities.** `vector_index` (Memgraph, Neo4j: true) and `query_modules` (Memgraph: true) on
`pangloss_core.storage.Capabilities`.
- *Pure test* (`pangloss-core/tests`): an app that `requires` one is refused on a backend without it, by name.
- *Docs*: `backend-neutral-addons.md`.

**1.3 A vector index as a kind of index.** `AddIndex`/`RemoveIndex` with `index = {"kind": "vector", "name",
"label", "property", "dimension", "metric", "capacity"}`.
- *Where*: `migrations/changes.py` (the description, the validation of the keys); `MemgraphMigrations.add_index` /
  `remove_index` and `create_index_statement` (`CREATE VECTOR INDEX … WITH CONFIG`); `Neo4jMigrations` and
  `schema.create_index_statement` (`CREATE VECTOR INDEX … OPTIONS {indexConfig}`, then `await_indexes`); each
  backend's `installed_app_structure()` so that `<app>.structure.INDEXES` may list one and the expected structure
  holds it.
- **Main first**: the two DDL statements, and how each backend lists a vector index (`SHOW INDEX INFO`,
  `SHOW INDEXES`), tried by hand on scratch containers. The capacity on Memgraph is fixed at creation: what happens
  at capacity is found out here and written down.
- *Conformance* (`conformance/test_vector_index_live.py`): a migration makes the index, a second run makes nothing,
  `RemoveIndex` drops it, undoing the migration drops it; the structure check reports a missing one.
- *Docs*: `migrations.md`.

**1.4 `Dialect.vector_search`.** `vector_search(index, k, vector) -> str`, written after `CALL` and before
`YIELD node, score`, as `text_search` is (Memgraph: `vector_search.search`, with `similarity AS score`; Neo4j:
`db.index.vector.queryNodes`, or the `SEARCH` clause through `Dialect.query` if the procedure is refused).
- *Conformance* (same file): ten nodes with known vectors, the nearest three come back in order on both backends; a
  node deleted in the same test may still come back on Memgraph (asserted as "is tolerated by the caller", with the
  reason), and never on Neo4j.
- *Docs*: `database-abstraction.md`.

**1.5 `install_query_module`.** `Backend.install_query_module(name, source) -> bool` on Memgraph
(`mg.get_module_file`, then `create_module_file` or `update_module_file` only if the text differs, then
`mg.load(name)`); absent on Neo4j. The `Backend` protocol gains `dialect` too (add-ons reach it by
`transactions.dialect()` today).
- **Main first**: whether one module file can import another installed beside it (phase 4 wants the maths in a file
  of its own), and what an import error in a module looks like to the caller.
- *Live* (`pangloss-memgraph/tests/live/test_query_modules_live.py`): a module is installed and callable at once;
  the same text again changes nothing (returns false); changed text replaces it; a module that fails to import
  raises with the module's error in the message.
- *Docs*: `backend-neutral-addons.md`, `memgraph.md`.

### As built (2026-11-20)

- **1.1**: as written, and three things more. The two bases are among the top-level classes (`utils.get_top_level_classes`),
  or their own names would have become labels. `semanticTraits` is in the snapshot's `NOT_DATA_KEYS`, beside
  `traits`: without it the replay of every project's migrations stopped equalling its models at the next
  `makemigrations`, whether or not it has a semantic trait (found by the builder's test, which is
  `test_a_trait_that_becomes_a_semantic_trait_is_not_a_change_of_data`). The editor schema that `pangloss check`
  gives the language server names the two bases. Traits have no entries of their own in the export, so only the
  per-model list is new.
- **1.2**: as written.
- **The trials of 1.3 to 1.5** changed three things in the steps below (the table is in
  `notes/similarity-evaluation/README.md`):
  - *Capacity is not a limit on Memgraph 3.14*: the index grows (64, 256, 16,384). `capacity` stays a key of the
    index, as where it starts, and "what happens at capacity" is nothing.
  - *1.4 gives the whole clause, not what goes between `CALL` and `YIELD`.* On Memgraph a node just deleted is still
    given by the search, and reading a property of it fails the whole query; the hit has to be matched again by its
    internal id. And the two scores differ (the cosine; one plus the cosine, halved). So
    `Dialect.vector_search(index, k, vector, carry=())` is the clauses that bind `node` and `score` (the cosine, on
    both), keeping the variables named in `carry`.
  - *1.5 cannot give the module's error*: a module that fails to import fails silently, the reason in the database's
    log alone. `install_query_module` checks that the module has procedures or functions afterwards, and says where
    to look. One module file can import another, so 4.1 needs no inlining.

- **1.3**, as built: an entry is `{"kind": "vector", "name", "label", "properties": [one], "dimension", "metric":
  "cos", "capacity"?}` (`properties`, as every other entry has, not `property`), checked when the change is made
  or read from a file (`changes.check_index_entry`). Three things the step did not foresee:
  - `same_structure` compared only kind, label, properties and name, so another dimension was "the same index". It
    now compares every key but `app`.
  - A remove and an add of the same name were applied add first (and undone add first), and the add was refused.
    `RemoveIndex` of a vector index is in the creating phase, and `diff_structure` lists removes before adds. No
    other kind changes its order. (A text index whose property changes under one name has the same fault on
    Memgraph, from before: not fixed here, in `TODO.md`.)
  - Both databases make nothing, silently, for a second name on a label and property that have a vector index. The
    add reads the list again afterwards and raises if its index is not there.
  `pangloss memgraph info` lists vector indexes. Nothing compares a database with `structure()` at run time: a
  missing index is found as any is, by the snapshot differing from the migrations.
- **1.4**, as built: `Dialect.vector_search(index, k, vector, carry=())`. **Memgraph's `similarity` is the size of
  the cosine, not the cosine** (found by the builder with a vector pointing the opposite way; the trials had only
  positive cosines), so the score is `1 - distance`. The two texts:
  - Memgraph: `CALL vector_search.search('<index>', <k>, <vector>) YIELD node AS pg_hit, distance AS pg_distance
    WITH <carry, >id(pg_hit) AS pg_hit_id, 1 - pg_distance AS score MATCH (node) WHERE id(node) = pg_hit_id` (the
    `MATCH` is a `ScanAllById`);
  - Neo4j: `CALL db.index.vector.queryNodes('<index>', <k>, <vector>) YIELD node, score AS pg_raw_score WITH
    <carry, >node, 2 * pg_raw_score - 1 AS score`.
- **For 2.4**: on Memgraph a deleted node keeps its place among the `k` until the database collects it, and is then
  dropped by the re-match: after many deletes a search gives far fewer than `k`, even none (the conformance
  fixture runs `FREE MEMORY`). `VECTORS_OVERFETCH` alone does not answer that. 2.4 measures how long deleted nodes
  stay on a database in use, and `nearest` asks again for more when it comes back short.
- **1.5**, as built: `install_query_module(name, source, expects=(), library=False) -> bool` on Memgraph's backend;
  `library=True` is a module of helpers with no procedure of its own. `Backend.dialect` on both.
  `pangloss_core.backend.ONLY_WITH_CAPABILITY` says which names of `Backend` go with which capability. The test
  is `packages/pangloss-memgraph/tests/test_query_modules_live.py` (the package has no `tests/live`).
- **Not looked at**: whether a vector index survives `pangloss restore` of a Memgraph snapshot
  (`rebuild_text_indexes` knows only text indexes); what is left of a working module updated with text that does not
  load. Both are in 2.2's and 4.1's way, and are checked there.

**Phase 1 is done when** `./run_tests.sh` is green and nothing but the tests uses the hooks.

## Phase 2: `pangloss-vectors`

The framework and the one part that needs no graph. Branch `vectors-2-package`. `requires = {"cypher",
"vector_index"}`.

**2.1 The package and the Part protocol.**
- *Where*: `packages/pangloss-vectors` (`__init__` with `_install()`, `parts.py`, `settings.py`, `structure.py`,
  `migrations/0001_initial.py`), `run_tests.sh`, `implementation_docs/packages.md`, the skill's package table (the
  skill's check fails without it).
- **Main writes** `parts.py`, since every later package is built against it:

  ```python
  class Part(Protocol):
      name: str                                       # "class", "graph", "name", "time"
      local: bool                                     # can refresh after a save without a rebuild
      requires: frozenset[str]                        # capabilities
      def dimension(self) -> int: ...                 # known after initialise()
      def signature(self) -> str: ...                 # a hash of everything a rebuild depends on
      async def rebuild(self, write: Writer) -> int: ...
      async def refresh(self, changed: Changed, write: Writer) -> Refreshed: ...
      async def overlay(self, plan: WritePlan) -> dict[str, Vector]: ...
  ```

  with `register_part(part)`, and profiles as data (`VECTORS_PROFILES = {"default": {"graph": 1, "class": 0.1}}`).
- *Pure tests* (`tests/unit/test_parts.py`): a part registered twice is refused; a profile naming a part that is not
  installed is refused at `initialise()`, by name; `signature()` changes when a setting it names does.

### As built (2026-11-21)

- **2.1**: as written, with these differences. The pure tests are `tests/test_vectors_parts.py` (the repository
  keeps pure tests in `tests/` and live ones in `tests/live`, and a test file's name must be its own across
  packages). `Part` has one attribute more, `weight`: its weight in the default profile, which, when the settings
  give none, is every registered part at its own weight (a `"default"` naming `graph` would be refused in a project
  without `pangloss-fastrp`). `parts()` is `pangloss_vectors.parts.parts()`, not at the package's root (the module
  of that name would replace it). `settings.py` has `overfetch()` and `graph_sees()`. `structure.py` and `0001`
  hold two plain indexes (`PGVector(of)`, `PGVectorState(part)`); `run_tests.sh` is untouched until 2.2 makes
  `tests/live`.
- **2.4's measurement was done before 2.2**, because it decides what 2.2 stores
  (`notes/similarity-evaluation/README.md`, "Which index a profile searches"). One index of whole vectors fails
  (recall 0.34 at the default profile on Memgraph), and so does the fallback the step named, an index for each part
  merged (0.36 for a balanced profile). **What holds is an index for each profile**: the parts are stored apart and
  unindexed, and for each profile a vector of the parts scaled by its weights is stored and indexed (0.92 and up on
  both; on Neo4j only with quantization off). So 2.2 stores `PGVector` (a part of an item) and a combined vector
  for each profile, the vector indexes are by profile and by profile and group, and a profile's weights are part of
  what a rebuild depends on.

- **A profile's weight is the weight of a part's cosine** (settled with 2.3's planted test, `hierarchy.py`): a part
  goes into a profile's vector at length one times *the square root* of its weight, so that the cosine of two such
  vectors is the weighted mean of the parts' cosines. With the weight itself as the scale, a class part at 0.1
  counted for a hundredth and changed nothing. The planted test, written again on new data, shows what the first
  did: nearest of other classes that are a parent, child or sibling class, 35% by the graph alone, 48% at decay 0.5
  and weight 0.1, 69% at 0.3 (the 64% to 76% of 2026-11-11 were of data that is lost).
- **Two findings of 2.2's trials** (`vector_index_trial_3.py`): Memgraph refuses to make a vector index while any
  node of its label has the property at another length (so the label and name of a profile's index carry the
  dimension); a vector index survives a recovered snapshot, so `pangloss restore` needs nothing for it.

- **2.2**, as built (not as the step says, which the measurement overtook):
  - *Stored*: `PGVector {of, part, type, generation, vector}` (a part of an item, no vector index);
    `PGProfileVector` under the label `PGV_<profile>_<dimension>` and, for each group, `PGV_<profile>_<dimension>_<Class>`
    (the combined vector, indexed by `pgv_<profile>_<dimension>[_<class>]`); `PGVectorState` for a part and
    `PGVectorProfile` for a profile, whose `generation` is the one in use. The plain indexes are in `0001`.
  - *The switch* is one transaction that sets the generation on the state nodes; both generations are in the vector
    index meanwhile, and readers filter by the state's. "Written before it is indexed" is not done. Generation
    numbers are one sequence for all parts and profiles; two rebuilds at once would take the same number, which
    2.5's lock prevents.
  - *A group* is a class that says `VectorsMeta(searchable=True)` itself; its subclasses are in its group and have
    none of their own.
  - *The indexes follow the models* by a general hook: an app's `structure` module may have functions `indexes()`
    and `constraints()`, called after `initialise()`, and an entry's own `app` wins over the stamp
    (`pangloss_models.indexes.installed_app_structure`, now one copy for both backends). The vector indexes go to
    the project's migrations: a group's to the app of its class, a profile's to the installed app with the most
    models of its own, or `VECTORS_MIGRATIONS_APP`. **So a class added to or taken from a project is a migration
    of two indexes or more** once the class part exists (its dimension is in their names).
  - *`quantization`* is a new optional key of a vector index entry; Neo4j's index is made with it off.
  - *Open*: Neo4j does not compare the quantization of an index that is already there; `combine` reads every id of
    a generation into Python before paging, and its queries are not measured at size (2.5 measures a rebuild).
  - *Tests*: 68 in the package on each backend; the conformance file 11 on each.

- **2.3**, as built: `class_part.py`, the part `"class"` at weight 0.1, registered when the package is imported
  (so every project that installs `pangloss_vectors` has it in its default profile). With several ways up to one
  dimension the nearest counts, a fulfilled class included (not a sum). `overlay` knows the fulfilled classes: a
  write plan's head has its labels. The class part does not apply `VECTORS_GRAPH_SEES` (it holds nothing of an
  item's contents). A head is `HeadNode` with the label `Document` or `Entity` (so a `SameEntity`, a
  `ReifiedRelationDocument`, has no vector), not `deleted`, not `merged_into`.
- **2.4**, as built: `search.nearest(of= | vector=, profile, group, k, see_unpublished)` gives
  `Nearest(status, hits)`, `status` being `ok`, `pending` (no vector, or the profile not built) or `rebuild_due`
  (the stored dimension is not today's). One query: the profile's state, `Dialect.vector_search`, the hits of the
  state's generation, the item by `HeadNode(id)` with the core's visibility. Its plan uses the indexes on both
  backends (seen on test-sized data only). While short of `k` it asks again for four times as many, up to twice
  the state's count plus one, or 4,096. **Open for 2.5**: `set_vectors` does not keep the state's `count`, so
  after many refreshes the limit is too low. Neo4j warns on every search that `db.index.vector.queryNodes` is
  deprecated for `SEARCH` (the dialect's, from 1.4).
- *Tests after 2.4*: 104 in the package on each backend.

- **2.5**, as built: `rebuild.py` (one at a time by a lease, `PGVectorsRebuild`, taken under the backend's lock
  and renewed; a second is refused with `VectorsRebuildBusy`), `status.py`, `cli.py` (`pangloss vectors rebuild`,
  `status`, `weights`), `admin.py` (the job `vectors_rebuild`), `api.py` (`GET /api/{NAME}/{id}/similar`,
  `GET /api/vectors/status`), `implementation_docs/vectors.md`. Differences:
  - **`pangloss check` does not say a rebuild is due**: it reads no database and has no hook for an app; the
    status command and route say it. In `TODO.md`, for the user.
  - A profile's state keeps its `weights`, and `removed`: the vectors deleted in place since it was built, which
    the search adds to the count it stops asking at (a deleted vector holds a place on Memgraph).
  - The route answers `rebuild_due` *with* results when the vectors are only out of date (a signature, the
    weights); with none when the dimension is not today's.
  - A changed `VECTORS_GRAPH_SEES` makes the class part's rebuild due too, needlessly.
  - **Measured** on `:7702`, 100,000 heads of five classes, the class part alone (`measure_rebuild.py`, `.txt`
    in `notes/similarity-evaluation/`): a rebuild 22 s (the part's vectors 4 s, `combine` 16 s), a second 25 s;
    `nearest` 61 ms at the median, 57 ms in a group. Not on Neo4j. **Without the package's plain indexes (its
    migration not applied) a rebuild is a scan for every row**: about 11 s for each 1,000.
  - *Tests*: 130 in the package on each backend, the "done when" of the phase among them
    (`test_a_project_with_only_pangloss_vectors_answers_documents_of_a_like_class`).

**2.2 Storage, groups and generations.**
- *What*: `(:PGVector {of, part, generation, vector, at})` with the labels of its groups (`PGVPerson`); an index on
  `of`; `(:PGVectorState {part, generation, built_at, count, stale, signature, graph_sees})`; `VectorsMeta`
  (`searchable`, `include`); `store.py` (`write_generation`, `switch`, `drop_generation`, `set_vectors` in place,
  `delete_for`). Vector indexes by migration: one for each part, and one for each part and searchable group, made
  from the models by the package's own `makemigrations` hook.
- **Decide before building**: how the package's indexes follow a project's models (a class becomes `searchable`).
  Proposed: the project's own migration carries them (the planner asks installed apps for extra index entries: a
  small general hook, `hooks.extra_indexes`), not a migration of `pangloss-vectors`, which cannot know the project.
  Main checks the planner and settles this in 2.2's brief.
- *Live* (`tests/live/test_store_live.py`): vectors written and read by `of`; a second generation is invisible until
  the switch and the first is gone after it; `set_vectors` updates in place; the group labels follow the item's
  class and the classes above it; a class made searchable gives a pending migration, and applying it makes the
  index.

**2.3 The class part.**
- *What*: `class_part.py`: at `initialise()`, one dimension for each class of the hierarchy and each semantic trait;
  a map `type → vector` (self 1, parent `decay`, and so on, normalised); a second map for fulfilled classes by
  label; settings `VECTORS_CLASS_DECAY` (0.5). `rebuild` reads `(id, type, labels)` in pages; `refresh` and
  `overlay` are a lookup.
- *Pure tests* (`tests/unit/test_class_part.py`): on the demo's hierarchy written out in the test,
  `CreationOfPainting` is nearer `CreationOfArtwork` than `Birth`; a mixin trait adds nothing and a semantic trait a
  dimension; a fulfilled class counts only for a node with its label; a class added changes `signature()`.
- *Measured*: the planted hierarchy test of the investigation (`hierarchy.py`, lost) rewritten as
  `notes/similarity-evaluation/hierarchy.py`, to reproduce 64% → 76% at decay 0.5, weight 0.1.

**2.4 Search.**
- *What*: `search.py`: `nearest(of | vector, profile, group, k, see_unpublished)`: the query vector's parts scaled
  by the profile, `Dialect.vector_search` with `k × VECTORS_OVERFETCH`, joined on `of` to a node that passes
  `fragments.visible`, cut to `k`; a `merged_into` id answers for the survivor; an item with no vector answers
  `pending`.
- **Decide here** (it was "not measured" on 2026-11-11): recall when a profile zeroes or rescales parts of the query
  against an index built on whole vectors. Main measures it on `:7690` with the class part and a random stand-in for
  the graph part. If recall falls below 0.9 at the profiles wanted, parts get an index each and `nearest` merges
  (the storage of 2.2 already keeps parts apart, so this changes `search.py` only).
- *Live* (`tests/live/test_search_live.py`): the nearest come back in order; a deleted item does not; an unpublished
  one only to a logged-in reader; a group narrows; a just-deleted vector returned by Memgraph's index is dropped;
  the survivor of a merge answers.

**2.5 Rebuild, status, routes.**
- *What*: `admin.py` (`JobKind("vectors_rebuild", …, options=(Choice("part", …),))`); `cli.py` (`pangloss vectors
  rebuild [--part]`, `status`, `weights`); `api.py` (`GET /api/{NAME}/{id}/similar?profile=&type=&limit=`,
  `GET /api/vectors/status`); a rebuild takes the backend's lock so two cannot run; a server started with a
  `signature` or `graph_sees` other than the state's says so in the status and in `pangloss check`.
- *Live* (`tests/live/test_rebuild_live.py`, `test_routes_live.py`): the command builds and switches; a search
  during a rebuild sees the old generation whole; the route gives `ReferenceView`s with similarities, 404 for what
  the reader cannot see, `pending` for what has no vector; a changed setting reports "rebuild due".
- *Docs*: `vectors.md` (new), `api.md`, `guide/cli.md`, `status.md`.

**Phase 2 is done when** a project with only `pangloss-vectors` answers "documents of a like class" over the API on
both backends.

## Phase 3: `pangloss-fastrp`, the Python engine

The graph part, on any Cypher backend. Branch `vectors-3-fastrp`. Depends on numpy and scipy (the first workspace
package to). 3.1 and 3.2 need nothing of phase 2 and are built beside it.

**3.1 The maps: the rules, from the registry.**
- *What*: `FastRPMeta`; `maps.py`: `graph_maps() -> GraphMaps`, made at `initialise()` and passed to an engine as
  plain data (it must survive `json.dumps`: the Memgraph module gets it as a parameter):
  - `kinds`: `type → "stop" | "through" | "end" | "out"` (documents and entities are stops; the five wrapper kinds
    through; a class with `stop=True` ends a chain; `PGCitation` and its variants, derived documents and
    `include=False` are out), each class below a declaring class included;
  - `class_weight`: `type → float`, for documents and for wrapper classes;
  - `held`: wrapper `type → [field]` (`held_field_names`), and `own`: wrapper `type → bool`;
  - `field_weight`: `(type, field) → float`;
  - `shares`: `(type, field) → property` for a field with `SumsTo`;
  - `citations`: `type → True` for the citation classes;
  - `signature()`: a hash of all of it and of `FASTRP_STEPS`, `FASTRP_DIMENSION`, `VECTORS_GRAPH_SEES`.
- *Pure tests* (`tests/unit/test_maps.py`), on `similar_models` and small models written in the test, one test for
  each rule of "The joined graph, as now proposed": a class below `InRole` gets what `InRole` declares; a `stop` on
  `Negative` reaches a class below it; `WeightedAlternative.alternatives` is a share of `percent`; a `MatchesCriteria`
  is through and its `target` is held; `PGCitation` is out and a citation; a derived document is out; a weight on a
  wrapper class and on a field; the maps are JSON; a `FastRPMeta` naming a field the class has not is refused at
  `initialise()` with the field's name.

**3.2 The pure maths, and the oracle.**
- *What*: `maths.py`, with no driver and no `mgp`, over a small interface an engine fills in:

  ```python
  class Reader(Protocol):
      def nodes(self, ids=None) -> Iterable[Node]: ...        # id, type, deleted, merged_into, published
      def out_edges(self, ids) -> Iterable[Edge]: ...         # forward: source, target, field, properties
      def in_edges(self, ids) -> Iterable[Edge]: ...          # the same edges, by their target
      def citations(self, ids) -> Iterable[tuple[str, str]]: ...   # citing head or node, cited id; both ways
  ```

  `joins(reader, maps, starts)`, `seed(id)` (from a hash of the UUID), `rebuild`, `refresh(changed)` (the
  neighbourhood `2k − 1` joins out, vectors within `k − 1` returned, with each one's neighbours), `overlay(plan)`.
  `wrapper_walks.py`'s `join` and `fastrp` are where it starts; `MemoryReader` (a graph in dicts) is in
  `pangloss_fastrp.testing`, with `oracle(graph, maps)`.
- **Main builds this step.** It is the part the 2026-11-11 trial proved and lost, and every later equality test
  rests on it.
- *Pure tests* (`tests/unit/test_maths.py`, `test_exactness.py`):
  - each rule on a hand-made graph of a dozen nodes, the joins listed in the test (depth: the same joins for 0 to 3
    wrappers; shares; a computed field's edges at one over their number; one join for each pair at the largest
    weight; a wrapper's own relation joined to the document, and not with `own=False`; a stop; reverse and `derived`
    edges not followed; a citation both ways; deleted and merged nodes out; `graph_sees` both ways);
  - **exactness, by random edits**: 200 seeded rounds on generated graphs of about 2,000 nodes with wrappers of
    every kind: apply a random edit (a document added, removed or changed; a reference removed; a share changed; a
    candidate added; a merge; a document published), `refresh` what changed, and compare **every** vector with a
    fresh `rebuild`: equal to 10⁻⁵. A failure prints the seed and the edit;
  - `overlay(plan)` equals the vectors after the same plan is applied, for 50 seeded plans, two unknowns included;
  - the vector of a node does not depend on the order nodes are read in;
  - the planted figures of `wrapper_walks.py` as a regression: hopped-over family ≥ 15% at every depth; shares beat
    flat on its world B.

### As built (2026-11-21)

- **3.2 was built before 3.1** (main, while phase 2 was with `builder`), so `maths.py` says what the maps are and
  3.1 fills them from the registry. `packages/pangloss-fastrp`: `maths.py`, `testing.py`
  (`MemoryReader`, `oracle`, `World`: a random graph of every shape, and random edits),
  `tests/test_fastrp_exactness.py` (34 tests; pure tests are in `tests/`, as in the other packages).
  - *The reader* is `nodes(ids | None)`, `out_edges(ids)`, `in_edges(ids)` and `citing(ids)` (the ids of the
    citations that cite these): a citation is a node with `cites`, joined as a chain's end, so there is no
    `citations()` giving pairs. A nested node's `published` and `deleted` are its head's: the reader's to give.
  - *`GraphMaps`* is one frozen dataclass of plain maps (`plain()`, `of()`): `kinds`, `class_weight`, `held`,
    `own`, `field_weight` and `shares` keyed `"Type.field"` (`shares` gives `[property, total]`), `citations`,
    `steps`, `dimension`, `sees`. A type not named is out.
  - *Weights*: a wrapper's own relation is joined at the weight the chain arrived with, times that field's. A
    computed edge counts one over the computed edges of its wrapper's field that the reader may see (whatever
    their ends are). A join is undirected, the largest weight of the ways either way.
  - *`seeds`* are from a hash of the id (blake2b, then splitmix64 for each dimension): the same in any engine.
  - *`refresh(reader, maps, changed, cap)`* wants both ends of every join made, lost or reweighted; it reads
    `2k − 1` rings and returns the vectors within `k − 1`, and `gone` for those that now have none; `TooLarge`
    past the cap. *`overlay(reader, maps, nodes, edges, removed)`* lays nodes and edges over the reader and is a
    refresh of them.
  - **The exactness holds** under the rules of 2026-11-20: 200 seeded rounds of random edits (documents added,
    removed, changed, published; a reference dropped; shares changed; a candidate added; a merge; an entity
    deleted), under both values of `sees`, each compared with a whole rebuild to 10⁻⁵; 51 overlays, two unknown
    people in each. The test fails with the neighbourhood a ring short, and with a ring too many returned.
  - *Not done here*: the hand-made rule tests one by one (one test covers the rules together; 3.1's `builder`
    writes the rest), and `wrapper_walks.py`'s planted figures as a regression.

- **3.1**, as built (after 3.2): `meta.py` (`FastRPMeta(weight, weights, stop, own, include)`; **no `through`**:
  the investigation gives it no meaning the others have not), `settings.py` (`FASTRP_STEPS`, `FASTRP_DIMENSION`),
  `maps.py` (`graph_maps()`, `signature()`). What the registry showed:
  - a use of a generic is a registry entry of its own (`InRole[Agent]`), and a stored node's `type` is the
    generic's name: the maps go by the declared class;
  - the five wrapper kinds are told by `model.__metatype__`; held fields by `search.held_field_names`; a share by
    the `SumsTo` among a relation field's validators; the citation types are
    `pangloss_models.citations.CITATION_TYPES`;
  - **`PGCitedBasis`**, a third citation class, a document that holds citations in `basis`: taken as `through`, so
    a document is joined to what its basis cites.
  - *Tests*: `test_fastrp_maps.py` (43), `test_fastrp_rules.py` (24, each rule its own test, the joins worked out
    by hand), `test_fastrp_planted.py` (5: `wrapper_walks.py`'s figures through `maths`: the same family among a
    person's ten nearest 19% to 20% at every depth; shares 34.0 against flat 27.4 on world B with the bystanders'
    field at 0.2). 106 in the package.
- **A rule the rule tests corrected in `maths.py`**: the join of a nested document to the one it is in takes the
  *nested* document's class weight ("a quieted nested class is quieted all the way up"), not the outer one's.
  `GraphMaps.documents` names the stops that are documents for it.
- **Left as it is**: a computed field's share counts every candidate edge the reader may see, whatever its end
  is (the investigation says "the candidates that are in"; a delete or a merge drops computed edges, so the two
  rarely differ).
- **For 3.3**: the documents nested in a derived document are stops by `type`, and only their head is out. The
  reader gives a nested node whose head is out as out.

- **3.3**, as built: `cypher_reader.py` (`load_all`, which reads everything in pages into a `MemoryReader`, now
  in `memory.py`; `CypherReader`, the sync reader over one read transaction: the maths runs in a thread and each
  call of the reader goes back to the loop), `part.py` (the part `"graph"`, weight 1), the setting
  `FASTRP_REFRESH_CAP` (50,000). The five queries of the trial, and one for what is below a head, are index seeks
  on both backends (seen on test-sized data); no text of Neo4j's own was needed.
  - On Memgraph a refresh reads one snapshot; **on Neo4j each query reads what is committed when it runs**, so a
    write during a refresh may be seen in part.
  - `refresh` takes as changed: the trees of the written and removed heads, every stop they are joined to
    *as if they were in* (so a delete, an unpublish and a merge find their neighbours with nothing kept), and
    `before` if the caller gives it.
  - **What phase 5 must keep**: an update replaces the nested documents of a head by new ones with new ids, and the
    old are gone from the database with their graph vectors still stored. Neither they nor a reference an update
    dropped can be found afterwards: both are caught only when the caller gives them as `before`. A strict `xfail`
    marks the second. So 5.2's worker needs, from before the write, the stops of the old tree and what they named.
  - `pangloss_vectors.store.remove_vectors(part, ids)` is new: the vectors of one part, the profiles recombined
    (`delete_for` takes every part's, which would drop the class vector of an item merely joined to nothing).
  - `similar_models.declare(reviewed=True)` gives `Factoid` a review, for the unpublished cases.
  - *Not tested*: an overlay with an entity written by a payload (`create_inline`) or named by a URL.
- **3.4**, as built: with `pangloss_fastrp` installed the default profile is graph 1 and class 0.1. The planted
  live test (40 people in 4 families through `InRole` and `Identification[WeightedAlternative[Person]]`): a
  person's five nearest people are of the family in 200 places of 200 on both backends; a factoid's nearest
  factoid in 31 or 32 of 32.
- *Tests after 3.4*: 155 in the package (one a strict `xfail`) and 131 in `pangloss-vectors`, on each backend.

- **3.5**, measured on Memgraph only (`notes/similarity-evaluation/README.md`, "Step 3.5", has the figures):
  - The scratch data is nearly all unpublished, so the default `VECTORS_GRAPH_SEES = "everyone"` leaves 3,050 of
    its 260,479 stops joined to anything. Measured with `"logged_in"`.
  - A whole rebuild, written and indexed, 240 s for 257,255 graph vectors and 173,564 class vectors; the read
    alone 37 s, the joins 2 s, FastRP 1 s. The rest is writing and combining.
  - A refresh of one document reads 1,027 stops at the median with three steps, and 12% of documents pass the cap
    of 50,000; with two steps none does, with four 32%. With the most joined 0.1% of stops left out, the most is
    546.
  - On planted data more steps find more: 19% of a person's family at `[0, 1, 1]`, 31% at four steps, 47% at
    eight.
  - **The two decisions are the user's and are not taken**: the default steps stay `[0, 1, 1]`, and vocabularies
    stay in at weight 1. What the figures say: steps buy quality on planted data and cost every update its reach;
    hubs, not steps, are what push updates past the cap here, and `FastRPMeta(include=False)` or a low weight on
    a hub class is the lever.
  - **Not done**: Neo4j at size (there is no large Neo4j database of today's models: the demo's `bulk_load.py`
    through the models is the way); quality with shares, citation joins and vocabularies on and off (the scratch
    data has no truth to rank against); a real project's data.
- **Mended after 3.5** (found by its counts):
  - *Nested documents have vectors in every part and can be found.* The class part covers every node of kind
    `Document` or `Entity`, head or nested (not citations, not `PGCitedBasis`); the search matches a hit as
    `PGIndexableNode` and takes what the reader may see from its head; the route answers for a nested document's
    id and class, and gives a nested result as the core's deep search does (`isHeadNode: false`, `headNodeId`,
    `headNodeType`). A searchable abstract `Statement` finds its nested subclasses.
  - *A rebuild of several parts combines each profile once*, and switches all in one transaction.
  - *`load_all` 37 s → 12 s* on `:7690`: the cost was the driver's work for each record, not `properties(e)`;
    a page now comes back as one row of lists.
  - **The whole rebuild is 263 s, not faster**: the profile is combined once, but over 327,109 items (nested
    documents now have class vectors), 163 s, of which writing the profile's vectors is about 128 s. That is the
    next place to look, with `combine` reading every id into Python first (11 s).
  - `nearest` on `:7690`: 83 ms at the median, 140 ms the slowest. **On data mostly unpublished a search by a
    reader who is not logged in comes back short** (1 to 6 of 10): the limit on how far it asks (4,096, or twice
    the count) is reached before ten that the reader may see. With `"everyone"` as what the graph sees, such
    items would have no graph vector; the index still holds their class vectors.
  - *Left*: the class part's `refresh` only writes: a head deleted or merged, and the nested documents an update
    replaced, keep their class vectors until phase 5's worker removes them (the same gap as the graph part's).
    Derived documents keep class vectors and have no graph vector.
- *Tests after the mendings*: 133 in `pangloss-vectors`, 164 in `pangloss-fastrp` (one a strict `xfail`), on each
  backend.

**3.3 The Cypher reader and the part.**
- *What*: `cypher_reader.py` (`nodes` and edges in pages by Cypher both backends run; the neighbourhood a ring at a
  time, with the aggregation the investigation proposed for Neo4j if 3.5 shows the need; citations by the index on
  `target_id`); `part.py` (`GraphPart`: `rebuild` through the reader and `pangloss-vectors`' writer; `refresh`;
  `overlay` from `plan_create`); registered in `_install()`.
- **Main reads every query** against `fragments` (`model_edge`, `not_deleted`, `published`) and tries it on `:7690`
  for its plan before the brief goes out: query text is chosen per planner and measured.
- *Live* (`tests/live/test_reader_live.py`, `test_graph_part_live.py`, both backends), on `similar_models`: what the
  reader gives for the written documents equals a `MemoryReader` built from the same payloads (so the joins are the
  same, shape by shape); `rebuild` on the database equals the oracle; after each of a save, an update that drops a
  reference, a delete, a merge and its undo, a new citation, a publish, `refresh` equals a rebuild; an overlay
  equals the same payload written.

**3.4 Similar by the graph, end to end.** The default profile becomes graph and class; the route of 2.5 answers by
it. A live test of the planted kind on a database: 40 people in 4 families written as documents through `InRole` and
`Identification`; a person's five nearest people are of their family.

**3.5 Measure, and decide.** Main, on `:7690` (Memgraph) and `:7698` (Neo4j), script
`notes/similarity-evaluation/measure.py`, results into the investigation and `backend-comparison.md`:
- the rebuild, by stage (read nodes, read edges, join, FastRP, write, index), against 2026-11-11's 12.5 s at 330,000
  nodes and 33 s on Neo4j;
- the neighbourhood sizes `refresh` meets for 500 real heads: the distribution, the hubs, and so the cap;
- `[0, 1, 1]` against 4, 6 and 8 steps: the planted quality against those neighbourhood sizes (**decide** the
  default steps);
- shares, citation joins and computed candidates on and off, and vocabularies in and out (**decide** the default
  for vocabularies);
- a copy of a real project's data, if the user gives one: held-out identifications ranked by the vectors.

**Phase 3 is done when** "Similar" works by the graph part on both backends after a manual rebuild, and the
measurements and the two decisions are written down.

## Phase 4: the Memgraph engine

The same maths, read in place. Branch `vectors-4-module`.

**4.1 The module.** `pangloss_fastrp/module/pg_fastrp.py` (an `mgp` reader over `ctx.graph`, keeping ids and never
`Vertex` objects across a scan; `rebuild` as a write procedure that writes `PGVector` nodes itself; `refresh` and
`overlay` as read procedures returning at most thousands of rows), with `maths.py` installed beside it as a module
file (or, if 1.5 found that one module cannot import another, the build step that inlines it, with a test that the
inlined text is current). Installed by `install_query_module` at server start and by `migrate`; refused loudly if
numpy or scipy do not import in the database's Python.

**4.2 The engine choice.** `GraphPart` uses the module when the backend has `query_modules` and
`FASTRP_ENGINE` is not `"python"`. A citation join on save: the worker's Cypher finds the pairs and hands them over
as virtual edges.
- *Live* (`tests/live/test_module_live.py`, Memgraph only, skipped by capability):
  - **the module's vectors equal the Python engine's** on `similar_models` data, for rebuild, refresh after each
    kind of edit of 3.3, and overlay: the same tests, run again with the other engine (a fixture parameter, so one
    test body);
  - the module is reinstalled when the package's file differs, and not otherwise;
  - `xfail(strict=True)`: a read procedure returning 131,072 records returns them all (the fault; when Memgraph
    fixes it, this fails and the workaround can go).
- *Measured* on `:7690`: rebuild, refresh and overlay against 3.5's Python figures (2026-11-11: overlay 37 ms
  against 267 ms).

**Phase 4 is done when** a Memgraph project uses the module with no setting, and the two engines are held equal by
tests.

### Not built: a trial first (2026-11-21), and a question for the user

Phase 4 was planned when reading the graph through Cypher was the slow part of a rebuild. It no longer is
(`load_all`, 37 s → 12 s). Tried on `:7690` before building anything (`notes/similarity-evaluation/module_scan_trial.py`):

| | In a query module | Python through Cypher |
|---|---|---|
| Read every node and forward edge (655,971 and about a million) | 14.1 s | 11.6 s |
| A refresh of one document | not built | 272 ms at the median, 7.3 s the slowest of 28 |

- **For a rebuild the module buys nothing**: reading properties and edges through `mgp` costs about as much for
  each item as a page of lists through the driver. What a rebuild spends its time on now is writing and combining
  (phase 3's "As built").
- **For a refresh or an overlay it could still be several times faster** (no round trips: on 2026-11-11 an
  overlay was 37 ms against 267 ms). That matters for reconciliation at the speed of typing (phases 9 and 10)
  and for a worker under heavy writing, not for "Similar".
- **What it would cost**: a module cannot look a node up by a property, so citations (found by `target_id`) and
  the starts have to be handed in by the caller's Cypher; a module updated with text that does not load loses
  its procedures (`install_query_module` must put the old text back); every equality test once more, on
  Memgraph alone.
- **Deferred by the user, 2026-11-21**: phase 4 is not built now. It is come back to if a later phase shows the
  Python engine too slow (reconciliation at the speed of typing is the likely one), and then only `refresh` and
  `overlay` go into the module. The Python engine's refresh has cheaper gains first (it asks five kinds of query
  for each ring). Phase 5 does not need it.

## Phase 5: keeping vectors current

In `pangloss-vectors`, generic over parts. Branch `vectors-5-worker`.

**5.1 The mark.** `hooks.pending_work` gives the kind `vectors` for every class with a vector. **Main checks first**
what marks a kind today: a save, delete, undelete and publish; a merge and its undo (`merge.py`); `set_computed`
with `less=` (the criteria worker: the kind `vectors` must not be among what is left out). What is missing is added
as a general fix with a conformance test, not worked round.
- *Live* (`tests/live/test_marks_live.py`): each of those writes leaves exactly one `PGPending` of the kind for the
  right head; the cost to a save is in `test_query_costs.py`'s budgets.

**5.2 The worker.** `worker.py`, on `pangloss_derived.worker`'s pattern (`claim`, a lease, `complete`, `release`;
woken by `hooks.after_write` and `work_marked`), a `BackgroundTask` from `api.py` unless
`VECTORS_WORKER_IN_SERVER` is false, and `pangloss vectors worker`. For a batch it works out the changed nodes (the
saved tree; what it refers to now; what it referred to before, from the neighbours kept with each vector), asks each
`local` part to `refresh`, writes in place, deletes the vectors of what is gone.
- *Live* (`tests/live/test_worker_live.py`, both backends): after each kind of write and one turn of the worker, the
  vectors equal a rebuild (the oracle again); a removed reference updates the entity left; a failing part releases
  its claims and the next turn succeeds; two workers do not do a batch twice.

**5.3 Hubs, staleness, the scheduled rebuild.** `VECTORS_REFRESH_CAP` (nodes; the default from 3.5): past it the
part updates the saved documents from their neighbours' current vectors and reports how many it left;
`PGVectorState.stale` counts them; `VECTORS_REBUILD_AFTER` and `VECTORS_REBUILD_AT` start the rebuild job.
- *Live*: with a cap of 50 on a planted hub, the saved document has a vector within 0.1 of the exact one, `stale`
  rises, and a rebuild brings equality and zero.
- *Measured* on `:7690`: the worker's lag with four writers; what a vector index costs its small writes (unknown
  since 2026-11-11).

**5.4 A rebuild while writes go on.** Marks made during a rebuild are kept and worked afterwards against the new
generation. *Live*: writes during a slowed rebuild are all reflected after it.

**Phase 5 is done when** vectors follow the data with no manual rebuild on both backends.

### As built (2026-11-21)

Built in one piece by `builder`, which a usage limit stopped at the docs; main finished from the tree (the docs page,
the wider runs). **Its report never came**, so what follows is from the code, its docstrings and the tests, not from
an account of its decisions.

- **5.1**: `pangloss_vectors._install()` gives the kind `vectors` for a class that has vectors, only when
  `pangloss_vectors` is an installed app (so importing the package changes no other test's writes: the conformance
  cost tests pass on both backends), and the kind keeps what an update took away (`pending_keeps_before`). Every
  write the explorer listed marks as it said; no fault of the core was found (`test_vectors_marks_live.py`, 9).
  `parts.Changed` has `before`, and the graph part hands it on, so the strict `xfail` of 3.3 is gone.
- **5.2**: `worker.py` on criteria's pattern (lease `PGVectorsWorker`, `VECTORS_WORKER_IN_SERVER`, `pangloss
  vectors worker`, `run_pending`). After a batch it deletes every vector of what is gone, in every part: the
  removed heads, what was nested in them, and what a mark kept of before that no longer exists.
- **5.3**: past `FASTRP_REFRESH_CAP` the graph part writes approximate vectors for the documents written alone
  (`pangloss_fastrp/approximate.py`: the first step exact, the later ones from the stored vectors of what they
  are joined to; a cosine of 0.89 to 0.93 with the exact vector on simulated hubs at the default steps, poorer with
  four steps) and counts them stale; `VECTORS_REBUILD_AFTER` starts a rebuild (the admin job if `pangloss_admin`
  is installed, else in the worker). **`VECTORS_REBUILD_AT` is not built** (no scheduler to hang it on).
- **5.4**: the worker and a rebuild never overlap: both take the rebuild's lock in the transaction that starts
  them; a batch is claimed only if no rebuild holds its lease, and a rebuild waits for the batch in hand (or takes
  the mark of a worker that stopped). Marks made during a rebuild are worked after its switch.
- *The deciding tests* (`test_fastrp_worker_live.py`, both backends, both parts, on `similar_models`): after each of
  a create, an update that adds, drops or replaces, a delete and undelete, a merge and its undo, a publish and an
  unpublish under both values of `VECTORS_GRAPH_SEES`, a new candidate from the criteria worker, and one turn of
  the worker, the stored graph vectors are those of a rebuild and nothing gone keeps a vector; past a cap of 50
  on a hub the vector is close and stale until a rebuild; writes during a slowed rebuild are all reflected.
- *Runs* (main, 2026-11-21): the two packages 339 passed on each backend; the conformance cost and pending tests
  on both; `pangloss-criteria` 340, `pangloss-derived` 399, the CLI guide test, on Memgraph; ruff, ty, the skill
  check. **Not run: `./run_tests.sh` whole** (the user paused here).
- **`./run_tests.sh` whole on `4cb42500`, 2026-11-21**: Memgraph 1740, without a database 3789, `pangloss-neo4j`
  173, Neo4j 1634, e2e 343 and **one failure**, not of this work: `test_admin.py`'s toolchain test read the API
  before the write the page had already shown was kept (it passed alone). The test now waits for the write's answer.
- **Measured** (main, 2026-11-21, `:7690`, 1.9 million nodes, `notes/similarity-evaluation/measure_worker.py` and
  `.txt`; factoids of one statement naming two people at random):
  - **the mark costs a small write nothing that shows**: 12.6 ms with it, 12.2 ms without, at the median of 200;
  - **one turn of the worker for one factoid: 1.2 s** at the median (1.8 s at 90%, 5.3 s the slowest), exact, 52
    vectors written; writing them in place is 0.22 s of it, **4.4 ms for each vector** (the part's node and the
    profile's, which the vector index holds);
  - **a batch of 200 factoids is past `FASTRP_REFRESH_CAP` together, though each alone is not**: the reader spends
    14 s finding that out, then every vector is made approximately and counted stale (2 for each factoid), 18 s in
    all. So with four writers (41 writes a second) **a write waited 18.5 s at the median for its vectors**, 20.6 s at
    most, and none of them is exact until a rebuild;
  - **a fault found and mended**: `store.read_part` (the stored vectors the approximation reads) was planned by
    Memgraph through the index of `generation`, a whole generation read for each id: 22 s for 400 ids, 32 s of the
    batch's 50 s. With the part and generation asked after a `WITH` it is 0.05 s (the figures above are after).
- **For the user** (not built): a burst of writes, which is what a pipeline makes, leaves every vector it touches
  approximate. The cheap mending is for the graph part to refresh a batch that is past the cap in smaller groups
  (halves, down to one head) before it falls back to approximating; it costs reads that are thrown away.
- **Not done**: a reading of the builder's unreported choices.

## Phase 6: the interface

An interface module in `pangloss-vectors`. Branch `vectors-6-interface`. By the interface rules: Solid 2.0, Tailwind,
`ReferenceChip`s, `MenuSelect`, strings as `t()` slots with translations.

**6.1 The "Similar" section.** An `itemSections` entry for every class with a vector, on a head's page and a nested
document's: fetched on its own (as `IncomingRelations` is), `ReferenceChip`s with a similarity bar, a `MenuSelect`
of profile and of type, "not yet" while `pending`, and it refetches on login and logout (`useSessionKey`).
- *Unit* (vitest in the module): the section's states (loading, pending, empty, a list), the profile and type
  controls change the request.
- *e2e* (`e2e/test_similar.py`, rows in `e2e/COVERAGE.md`): on the e2e project with both packages installed and a
  rebuild run, a person's page lists people of their family first; a nested statement's page has the section; a
  logged-out reader never sees an unpublished item in it; the dev build loads the page without errors
  (`e2e/test_dev_mode.py`).

**6.2 The admin slot.** `slots.admin`: generation, built when, how many vectors, how many stale, "rebuild due" and
why, a Rebuild button that starts the job and follows it (`live()`).
- *e2e*: the button runs a rebuild and the figures change; a non-admin does not see it.

**Phase 6 is done when** a reader sees similar items and an admin can rebuild, with the suite green.

### As built (2026-11-21)

Built by `builder` from one brief for both steps, on `vectors-6-interface`; main read the diff and had the runs made.
The page of the feature is [vectors.md](vectors.md), "The interface".

- **Three things main decided in the brief** (not in the step's text; none confirmed by the user):
  - the answer of `GET /api/NAME/{id}/similar` also gives `profiles` (`default` first) and `groups`, and a fourth
    status, `excluded` (the item's class has `include=False`), so the section needs one request and no route of its
    own to know what to offer, and shows nothing for a class without vectors;
  - `GET /api/vectors/status` (and `pangloss vectors status`) says `rebuilding`: who holds the lease of a rebuild
    running now, and since when, read with the states in one transaction (`rebuild.running`). So the admin part
    follows a rebuild whoever started it;
  - the Rebuild button asks nothing first: a rebuild writes a new generation beside the one in use.
- **6.1**: `itemSections.Similar` (`SimilarSection.tsx`; the logic in `similar.ts`), read directly in a memo under
  the boundary `ItemSections` gives, again on login and logout. Each row a `ReferenceChip`, a slate bar (a
  `role="meter"`) and the figure to two decimals in the page's language, in a grid so that chips and bars line up.
  The menus (profile, only with more than one; type, only with a group; never preselected) are in a row under the
  bar: `SectionBar` is a heading and has no place for controls, and core was not changed. A chip links to the
  item's own page (`/Type/id`), a nested document's too.
- **6.2**: `slots.admin.Vectors` (`VectorsAdminSection.tsx`): a table of the parts and one of the profiles, a badge
  for the state (up to date, rebuild due, unavailable) with the API's reasons, and Rebuild, which posts the admin
  job `vectors_rebuild` and is off while a rebuild runs; a `live()` feed of the status
  (`PANGLOSS_VECTORS_POLL_MS`). Between the job's being accepted and its process taking the lease the button is on
  again; a second click is the admin API's 409, shown as a refusal.
- **The e2e project installs both apps** (`Person` is a group; `pangloss vectors rebuild` in the session's setup;
  the worker in the server after that). **The section is on every item's page**, with up to ten chips and a heading
  more: tests that looked for a link or counted headings over the whole page were mended with
  `helpers.outside_similar`, or by naming the new heading, each with a comment.
- **Found, for the user**:
  - review's unreconciled mentions and the entries of a typology have vectors, and are listed among the similar
    under "All types" (a hearing's similar include other hearings' unreconciled mentions). Whether such classes
    should have vectors is not decided; a project can say `VectorsMeta(include=False)` on its own classes, not on a
    package's;
  - in `pangloss-dates`, the timeline's thumb stays on the year it had when its section is scrolled past in one
    step (seen when the page grew longer; `TODO.md`).
- **A fault of the item's page found by the section, and mended** (`interface-app/src/pages/Item.tsx`,
  `ToSurvivor`): the page of an entity merged into another, opened by its old address, changed its address to the
  survivor's as soon as the item had come, while the later parts of the page were still on their way; the item was
  read again, and about one time in two a module's section was taken over with nothing read, failed and was gone
  ("Hydration completed with 47 unclaimed server-rendered node(s)" on the development server). It was there before
  (derived's `DerivedFromThis` failed the same way, unseen: it had drawn nothing); "Similar" has nodes, so the
  development build said it. The address now changes once the page's stream has ended (`_$HY.done`). The same
  message comes when a test leaves an item's page by a link before its sections have come: a test waits first
  (the interface reference of the skill).
- **The look**, seen by main in screenshots of the e2e project's data (deleted): chips, bars and figures in three
  straight columns, slate only; the tables of `/admin` as its other parts. **Seen there**: items with a similarity of 0 or below were
  listed (an empty bar, "-0.02") when fewer than ten were any nearer. **The user, 2026-11-21: they are not shown.**
  The route leaves out what is below 0.005 (`api.MIN_SIMILARITY`), for every client.
- **Only in unit and API tests, not in a browser** (🚧 in `e2e/COVERAGE.md`): "Rebuilding since …", a refusal on
  `/admin`, the pending, empty and rebuild-due lines, the read again on login.

## Phase 7: the demo and the docs

Branch `vectors-7-demo`.

**7.1 The demo.** `pangloss-demo` installs both packages; `Agent` becomes a `SemanticTrait`; `Person` and
`Statement` are `searchable`; `Negative` has `stop=True`; the demo's migration (the trait's label, the indexes) and
its stubs made again; `populate` data gets a rebuild in the demo's setup script. **The demo's database (`:7688`) is
migrated only on the user's word.**

**7.2 Docs.** `vectors.md` and `fastrp.md` (✅ with "As built"); this page's "As built" sections;
`graph-embeddings.md` and `similarity-plan.md` marked for what is now built; `status.md`; `packages.md`;
`guide/vectors/` (declare, rebuild, the section, profiles); `guide/cli.md`; `TODO.md` (the "did you mean" item now
has its overlay); the skill (two packages, `SemanticTrait`, the module hook, the vector index kind) and its check.

**Phase 7 is done when** `./run_tests.sh` passes whole and the demo shows the section.

## Phases 8 to 13, in outline

Each is a package of [similarity-plan.md](similarity-plan.md) (its stages 7 to 13), and each gets its steps written
on this page's pattern when it is reached. The order below is a proposal that 3.5 may change.

| Phase | What | Tests in a line | Needs |
|---|---|---|---|
| 8. `pangloss-names` | The name part (folded trigrams, hashed, weighted by rarity), tables of name variants from a file or a typology | Pure: variants and namesakes rank; a changed table changes only this part's signature. Live: rebuild and refresh on both | 2 |
| 9. The time part, in `pangloss-dates` | Soft bumps over a date's bounds; an entity's span; registered only if `pangloss_vectors` imports | In `pangloss-dates`' tests, skipped without vectors: overlapping vague dates are near, a recurring event's years apart | 2 |
| 10. `pangloss-reconcile` | `POST /api/reconcile/candidates`: validate, plan, overlay, two stages, reasons, several unknowns jointly, "someone new"; review's `candidate_providers` | Live: a payload in, ranked candidates out, **nothing written** (node counts before and after); two unknowns; with and without review. Measured: the planted prosopography rewritten (2026-11-11: 86% → 94% with names) | 3, 8; 9 helps |
| 11. `pangloss-learn`, and reconciliation learning | `fit`, `Model`, a document of weights; retraining from review's decisions | Pure: planted weights are recovered; retraining is reproducible. Live: no decisions still works | 10 |
| 12. `pangloss-compare` | `CompareMeta`, pairs, verdicts at lookup, `EventJudgement`, the side-by-side page, learning from judgements | Pure: the trial's cases (general and specific class, once per, recurring, negated). Live and e2e: a judgement overrides; nothing is written by a lookup | 11; 2 and 9 optional |
| 13. Neo4j tuning | A cheaper overlay; every phase measured on both backends at 300,000 and 640,000 nodes | The same equality tests; figures in `backend-comparison.md` | 3 |

## Who builds each step

The agents of `.claude/agents/`: **`builder`** (builds decided work from a written brief, with its tests; does not
commit), **`test-runner`** (runs and reports; fixes nothing), and **`Explore`** (where is this read). **Main** is
the session that runs the plan: it settles what a step says to decide, tries Cypher on both backends before a brief
names it, writes the maths, measures, writes each brief, reads each diff against a run, writes "As built", and
commits and pushes. A report from an agent is a claim, checked against the diff and a run.

A brief to `builder` always holds: the step's text from this page; the files to read first; the tests by name with
their cases; what it must not touch; and the facts main found (the DDL that worked, the query that planned well).

| Step | Mostly | Main keeps | To `builder` | Runs (`test-runner`) |
|---|---|---|---|---|
| 0.1 Stored shapes | Main | All of it; corrections to the investigation | — | — |
| 0.2 Scratch databases | Main | All of it | — | — |
| 1.1 Semantic traits | `builder` | The export's new key; reading the stubs | All of it | `packages/pangloss-models`; the interface's unit tests |
| 1.2 Capabilities | `builder` (with 1.1) | — | All of it | `packages/pangloss-core` |
| 1.3 Vector index kind | Main, then `builder` | The DDL and the listing on both backends; what capacity does | The change kind, both dialects, the structure, the conformance test, from the statements found | Conformance on both; `packages/pangloss-models` (migrations) |
| 1.4 `vector_search` | `builder` (with 1.3) | The two calls, tried | All of it | Conformance on both |
| 1.5 Query modules | Main, then `builder` | Whether a module imports its neighbour; the error's shape | The hook, `Backend.dialect`, the live test | `packages/pangloss-memgraph` |
| 2.1 Package, protocol | Main, then `builder` | `parts.py`, the profile's shape | The scaffold (pyproject, `_install`, settings, structure, `run_tests.sh`, `packages.md`, the skill), `test_parts.py` | The package; the skill's check |
| 2.2 Storage | `Explore`, Main, then `builder` | How a project's indexes follow its models (`Explore`: how the planner collects indexes); the Cypher of the switch | `store.py`, `VectorsMeta`, the migration hook as settled, the live test | The package on both; `packages/pangloss-models` if the hook is new |
| 2.3 Class part | `builder` | The planted figure reproduced (`hierarchy.py`) | All of it | The package |
| 2.4 Search | Main, then `builder` | The recall of rescaled queries, and so one index or one for each part; the search query | `search.py` and its live test, once that is known | The package on both |
| 2.5 Rebuild, routes | `builder` | A reading of the lock and the generation switch | All of it; the docs of the phase | The package on both; `./run_tests.sh --no-e2e` |
| 3.1 Maps | `builder` | The rules (they are this page's and the investigation's); reading each test against its rule | All of it | The package |
| 3.2 Maths, oracle | **Main** | All of it | The hand-made rule tests, from the list, after `joins` exists (a second pair of eyes on the rules) | The package; the exactness test three times with other seeds |
| 3.3 Reader, part | Main, then `builder` | Every query, planned on `:7690` and on Neo4j | `cypher_reader.py` around those queries, `part.py`, the live tests | The package on both |
| 3.4 End to end | `builder` | — | The planted live test, the default profile | The package on both |
| 3.5 Measure | Main | All of it; the two decisions go to the user | — | — |
| 4.1 Module | Main | The `mgp` reader and the write procedure (the faults of 2026-11-11 are here) | — | — |
| 4.2 Engine choice | `builder` | The equality tests' fixture parameter | The choice, the install at start and at `migrate`, the strict `xfail`, the live test | The package on Memgraph; then on Neo4j (the module's tests skip) |
| 5.1 The mark | `Explore`, then Main | What marks a kind today (`Explore`); any fix to the core's marking | The live test of the marks | Conformance on both; `test_query_costs.py` |
| 5.2 Worker | `builder` | The changed-nodes rule; reading the claim and lease handling against derived's | All of it, from derived's worker as the model | The package on both |
| 5.3 Hubs, staleness | `builder`, then Main | The cap's default from 3.5; the lag and index-cost measurements | The cap, the stale count, the scheduled rebuild, their tests | The package on both |
| 5.4 Rebuild under writes | Main | All of it (ordering of marks against a generation) | — | The package on both; `./run_tests.sh --no-e2e` |
| 6.1 Similar section | `builder` | The look, checked in a browser on the scratch stack; the styling rules | The module, its unit tests, translations, `e2e/test_similar.py`, `COVERAGE.md` | The interface's unit tests; e2e; the dev-mode test |
| 6.2 Admin slot | `builder` (with 6.1) | — | All of it | e2e |
| 7.1 Demo | `builder` | The migration read before it is applied anywhere; the demo's database untouched | The models, migration, stubs, setup script | The demo's tests; e2e |
| 7.2 Docs | `builder` | A reading of the docs against the code | All of it | `./run_tests.sh`, whole, before the last commit |

**What runs side by side.** 1.1 with 1.2 go to one `builder` while main does 1.3's and 1.5's trials; 1.3 with 1.4
then go to a second. 3.1 (`builder`) and 3.2 (main) need nothing of phase 2, so they run while 2.2 to 2.5 are with
`builder`. 6.1 can start once 2.5 is merged (it needs the route, not the worker). Phase 12's first half
(`CompareMeta`, verdicts by rule) needs no vectors and can run beside phases 3 to 6 if comparison is wanted early.
Never two `builder`s in one package at once, and never two database test runs at once.

## What can go wrong

| Risk | Seen where | What the plan does |
|---|---|---|
| The exactness of `refresh` does not survive the new rules (shares counted over one wrapper, one join for each pair, citation joins) | Reasoned on 2026-11-20, not measured | 3.2's random-edit test is written before any engine; a rule that breaks locality is found there, on a laptop, in seconds |
| A module cannot import a neighbouring module file | Not tried | 1.5 finds out; 4.1 has the inlining fallback |
| Recall falls when a profile rescales parts of the query | Not measured since 2026-11-11 | 2.4 measures before `search.py` is written; storage already keeps parts apart |
| Hubs make most updates hit the cap on real data | The 590,000-node scratch data has real hub shapes only as far as `populate` does | 3.5 measures the neighbourhoods; the steps default is decided there, not before |
| Following computed candidates makes the criteria worker and the vectors worker chase each other | A consequence of the decision of 2026-11-20 | 5.1 checks the marks; 5.2's test includes a criteria re-evaluation; the vectors worker writes nothing that marks criteria |
| Memgraph's vector index at capacity, and a deleted vector returned | The second seen 2026-11-11 | 1.3 finds the first; 2.4's search tolerates the second, with a test |
| A project's models change (a class becomes searchable, a class is added) | The class part's dimensions, the indexes | `signature()` and "rebuild due" (2.5); the index follows a migration (2.2) |
| numpy and scipy in the server's environment | No workspace package has them today | Only `pangloss-fastrp` depends on them; a project that does not install it gets neither |

## Where the work stands

*The resume line: kept current with every step's commit.*

- **Finished**: phases 0 and 1 (`vectors-1-hooks`, pushed, whole suite green 2026-11-20). Phase 2, all five steps,
  on `vectors-2-package` (from `vectors-1-hooks`), 130 tests in the package on each backend (phase 2's "As
  built"). **`./run_tests.sh` whole on `ab970d8e`, 2026-11-21: every test stage
  passed** (Memgraph 1656, without a database 3663, `pangloss-neo4j` 173, Neo4j 1550, e2e 344); `ty` failed on a
  scratch script in `notes/` only, mended in the next commit (`ty check` clean).
- **Phase 3** on `vectors-3-fastrp` (from `vectors-2-package`): 3.1 to 3.5 done (phase 3's "As built").
  **`./run_tests.sh` whole on `ed32524f`, 2026-11-21**: Memgraph 1705 (1 xfailed), without a database 3779
  and **one failure** (`test_fragments`: the reader of `pangloss-fastrp` wrote the rule of what is deleted itself),
  `pangloss-neo4j` 173, Neo4j 1599 (1 xfailed), e2e 344. Mended in the next commit (`fragments.deleted`); that
  test and the package run again, not the whole suite.
- **Phase 4 is deferred** (the user, 2026-11-21; its section, "Not built: a trial first"): come back to it only
  if the Python engine proves too slow.
- **Phase 5 built** on `vectors-5-worker` (from `vectors-3-fastrp`; its "As built"), pushed. `./run_tests.sh`
  whole on `4cb42500` and its two measurements: phase 5's "As built" (one fault mended, `store.read_part`).
- **Phase 6 built** on `vectors-6-interface` (from `vectors-5-worker`; its "As built"): the "Similar" section and
  the part of `/admin`, with the e2e project on both apps. **`./run_tests.sh`
  whole on the tree of this commit, 2026-11-21**: Memgraph 1744, without a database 3788 and one failure,
  `pangloss-neo4j` 173, Neo4j 1638, e2e 351 and one failure; both failures passed alone and are mended in the
  commit, and run again by themselves, not in a whole run (`test_interface_workspace`: an old clash with the tests
  that make directories in the JavaScript source, now on one worker; `test_identity.py`: a text looked for in the
  whole page, which "Similar" sometimes listed). The development-build tests four times with no unclaimed nodes.
- **Next**: phase 7 (the demo and the docs) on `vectors-7-demo`. The demo's database (`:7688`) is migrated only on
  the user's word.
- **Half done**: nothing.
- **For the user, not blocking**: the default steps and whether vocabularies are in (3.5's figures); `pangloss check` saying a rebuild is due needs a hook (`TODO.md`).
  From phases 5 and 6 (`TODO.md`): a burst of writes leaves approximate vectors (refresh a batch past the cap in
  smaller groups?); which classes of packages have vectors (unreconciled mentions, typology entries); the three calls main took in phase 6's brief.
- **The user, 2026-11-21**: go on through the next phases without pausing at each; branches stay stacked
  (`vectors-3-…` from `vectors-2-package`), nothing merged.
- **Left running or stopped**: `pangloss-memgraph-similar` (`:7702`) and `pangloss-neo4j-similar` (`:7703`), small,
  running; `pangloss-memgraph-identity` (`:7690`; since 2026-11-21 with some 900 factoids more, of `measure_worker.py`, and
  about 1,500 stale graph vectors) and `pangloss-compare-api-neo4j-core` (`:7698`) stopped.
