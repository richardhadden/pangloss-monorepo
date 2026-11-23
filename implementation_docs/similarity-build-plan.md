# Similarity: the build plan ⏳

Written 2026-11-20. **Nothing here is built.** [graph-embeddings.md](graph-embeddings.md) holds the design, the
measurements and the decisions; [similarity-plan.md](similarity-plan.md) holds the packages, the hooks and the
stages. This page is what is built from them, step by step: what each step changes and where, the tests that say it
is done (by file), what is measured, and who builds it. Phases 1 to 7 are the base (vectors, the graph part, kept
current, shown in the interface) and are planned in full. Phases 8 to 13 (names, time, reconciliation, comparison,
learning) are planned in outline: each gets its steps written when it is reached, because phase 3's measurements
decide their order.

**2026-11-21**: phases 0 to 3 and 5 to 7 are built (each has "As built"; phase 4 is deferred). The next phases are
planned from "The next phases" on: 7a (what the base left), 8 (names) and 9 (time) in steps, 10 (reconciliation)
in provisional steps, 11 to 13 in outline, with who builds each and how they are tested.

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
- The next phases: order, and what is the user's first (planned 2026-11-21)
- Phase 7a: what the base left
- Phase 8: `pangloss-names`
- Phase 9: the time part
- Phase 10: `pangloss-reconcile` (provisional)
- Phases 11 to 13, in outline
- Who builds each step
- Who builds the next phases
- Testing the next phases
- What can go wrong
- Where the work stands

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

### As built (2026-11-21)

Built by `builder` from one brief for both steps, on `vectors-7-demo`; main read the migration and the changes to
the demo, and had the whole suite run.

- **7.1**: the demo installs both apps; `Agent` is a `SemanticTrait`; `Person` and `Statement` are groups;
  `Negative` has `FastRPMeta(stop=True)`. **The migration (`demo_app` 0024) is three vector indexes and nothing
  else**: of the profile `default` at dimension 165 (128 of the graph, 37 of the class part), and of its two
  groups. The step expected a label for the trait: there is none, a semantic trait is stored as any trait is
  (phase 1), so that change is no migration. `demo-setup.md` and `populate.py` say to run `pangloss vectors rebuild`
  after `populate.py`. **The demo's database (`:7688`) was not touched**: it needs `pangloss migrate` and then
  `pangloss vectors rebuild`, on the user's word; until then its server does not start (migrations pending).
- **7.2**: [fastrp.md](fastrp.md) is new (`FastRPMeta` has `include=`, not the `through=` of this page's table of
  defaults); [vectors.md](vectors.md) says what is built of all the phases; `graph-embeddings.md` and
  `similarity-plan.md` are marked where built; `status.md`, `packages.md`, the two packages' READMEs;
  `guide/vectors/`; `guide/cli.md`; `TODO.md`; the skill.
- **Found, for the user** (`TODO.md`):
  - the demo's factoids are reviewed, so what `populate.py` writes is unpublished, and with `VECTORS_GRAPH_SEES` at
    its default the graph part sees none of it: the demo's "Similar" is by class alone unless the demo says
    `logged_in` (the scratch copy of phase 3.5 did) or its factoids are published;
  - the similar route takes a UUID only, not the URL an entity was made with, which `GET /api/NAME/{id}` takes.
- **Not done of "done when"**: the demo showing the section, which waits for its database to be migrated.

## The next phases: order, and what is the user's first

Written 2026-11-21, on `similarity-next-phases`. **Nothing below is built.** The base (phases 0 to 3 and 5 to 7) is
in `dev`. What follows is planned in this order:

| Order | Phase | Planned as | Why here |
|---|---|---|---|
| 1 | **7a. What the base left** | Steps, in full | Four things the user decided on 2026-11-21. Three of them are what phase 10 stands on: exact vectors after a pipeline's burst, a route narrowed to a field's types, placeholders out of the results |
| 2 | **8. `pangloss-names`** | Steps, in full | The largest single gain measured (people 86% → 94% right first). Needs only phase 2. Its first step makes the planted data every later phase is measured on |
| 3 | **9. The time part** | Steps, in full | Small, needs only phase 2, helps both 10 and 12. One decision first (below) |
| 4 | **10. `pangloss-reconcile`** | Steps, provisional | The user's first use case. Its weights and its "someone new" depend on what 8 and 9 measure, so its steps are read again when it is reached |
| 5 | **11 to 13** (learning, comparison, Neo4j at size) | Outline | As before: each gets its steps when it is reached |

**The order is a proposal**: no one was there to ask when this was written. Phase 12's first half (`CompareMeta`,
verdicts by rule) needs no vectors and can come earlier if comparison is wanted before reconciliation.

**Confirmed by the user, 2026-11-21: the order above and every default in this table.** (Written as: for the user, before the step named; each had a default the plan took.)

| # | Decision | Taken as | Before |
|---|---|---|---|
| 1 | The order of the phases | The table above | 7a |
| 2 | The name of the placeholder mark | **No new mark: the core already has one.** `hooks.stand_ins` lists the documents that stand in for an entity (review's `Unreconciled` is the one today), and names no package. `pangloss-vectors` reads a stand-in's document class as no vectors. A project that wants them back says `VECTORS_INCLUDE = ["Unreconciled"]` | 7a.3 |
| 3 | Where the time part lives | **A small package of its own, `pangloss-dates-vectors`**, which depends on both and is installed as an app. The plan of 2026-11-20 had it in `pangloss-dates`, registered "only if `pangloss_vectors` imports". That is the optional import the user refused for the placeholder mark on 2026-11-21 ("which ties each package to it"), so the same answer is taken here | 9.1 |
| 4 | The name part and the default profile | The part's own weight is 0: installing `pangloss-names` changes no existing profile, no index and no result. A project names it in a profile (`{"name": 1}`, `{"name": 1, "graph": 1}`) | 8.3 |
| 5 | `type` at the similar route | It may be given more than once (`?type=Person&type=Group`), and `field=` is a short way to say the types a field holds | 7a.4 |
| 7 | ~~A type of a typology in a search that is not narrowed~~ | **Decided by the user, 2026-11-21**: listed, as a type. As the real class (`type=Role`, a field that holds roles) only if the data uses it as one: something names it where a `Role` goes | 7a.5 |
| 6 | An entity's time vector | Not in the first version: documents with a date have one, entities none. An entity's span needs the documents that name it, through wrappers, which is `pangloss-fastrp`'s joined graph; read it from there or not at all, decided on 9.3's figures | 9.4 |

Still the user's from before, and not blocking: the default FastRP steps and whether vocabularies are in the graph
(3.5's figures); the demo's `VECTORS_GRAPH_SEES`; a hook for `pangloss check`; the three calls of phase 6's brief;
the demo's database (`:7688`), not migrated.

## Phase 7a: what the base left

Branch `vectors-7a-leftovers`, from `dev`. Five steps; 7a.5 comes after 7a.3 and 7a.4 (it changes what both made), the others do not depend on each other; 7a.1 is in
`pangloss-fastrp`, the others in `pangloss-vectors`, so 7a.1 can be built beside any one of them.

**7a.1 A burst refreshed in groups.** Today `part.refresh_ids` gives every head of a batch to one
`maths.refresh`; a batch of 200 factoids is past `FASTRP_REFRESH_CAP` together, and all of it is then made
approximately (phase 5, measured: 18 s, nothing exact until a rebuild). Decided: on `TooLarge` the heads written are
halved, each half refreshed by itself, down to one head; only a head that is past the cap alone is approximated.
- *Why it stays exact*: a refresh computes vectors from the database as it is now, and every write of the batch is
  already committed. So each group's vectors are right whatever the order; the groups together must cover both ends
  of every changed join, which they do if `removed` and `before` are given to one group as they are today.
- **Main first** (a trial in `notes/similarity-evaluation/burst_groups.py`, on `:7690`): whether the halves can
  run inside one `reading(...)`, on one `CypherReader`, so that what the failed attempt read (`reader.seen`) is
  not read again. If they can, the "reads thrown away" are nearly none; if not, whether the worker should remember
  the size of group that last fitted and start there. The brief names the one found.
- *Pure* (`tests/test_fastrp_exactness.py`, new cases): random edits as now, the changed heads split into 2, 3 and
  7 groups in a shuffled order: equal to a rebuild to 10⁻⁵. With `removed` and `before` in the first group, and in
  the last.
- *Pure* (`tests/test_fastrp_part.py`): a fake reader that is `TooLarge` above n heads: the calls made are the
  halves expected; a single head past the cap is the only one approximated; `Refreshed.stale` counts only it.
- *Live* (`tests/live/test_fastrp_worker_live.py`, both backends): a cap of 50, a batch of 12 factoids of which one
  names a planted hub: after one turn the eleven are equal to a rebuild, the one is stale, `PGVectorState.stale`
  is 1 (today: 12 and more).
- *Measured* (main, `measure_worker.py` again, `:7690`): the batch of 200 with four writers: how many vectors are
  stale (aim: those of true hubs only), and how long a write waits (18.5 s today). The figures go into phase 5's
  "As built" and `fastrp.md`.

- **As built (2026-11-21)** (`briefs/7a.1.md`, `7a.1-report.md`; the trial `burst_groups.py`, `.txt`):
  - **The units are more than heads**: each head written, each head removed and each id of `before` is a unit
    (`part.Unit`), and a group's centre is `changed_stops` of its units. A stop's answer does not depend on what
    else is in the centre, so any division is exact; `removed` and `before` need not stay in one group.
  - **One reader that remembers** (`cypher_reader.RememberingReader`, all attempts in one `reading`): the trial's
    200 heads took 249 s halved without it and 53 s with it, the same vectors. It forgets everything past
    `REMEMBERED_CAPS` (10) times the cap. **No remembered size of group**: from 5 to 200 the start made 44 to 53 s.
  - Past the cap alone: a head written is approximated, after the exact rows are written and never in place of one
    (`approximately(exact=…)`); a head removed or a `before` id is left, 1 stale. `Refreshed.written` is now the
    exact rows only.
  - **The second reading found one fault, mended**: a head written, past the cap alone, whose own stops another
    group answered exactly had no approximate row and was counted 0 stale, while what is within reach of what it
    newly names was refreshed by nobody. Every unit past the cap alone now counts at least 1 (`part.stale_of`).
    It also noted, unmended: `stale` can count a hub twice (as a `before` unit and by its head's rows), which only
    brings the scheduled rebuild sooner; the approximation reads in a second transaction.
  - **Measured** (`measure_worker.py` again, `:7690`, `measure_worker_7a1.txt`): the batch of 203 factoids in one
    turn **62.7 s, 11,709 vectors written, all exact, none stale** (before: 18.2 s, 952 approximate vectors, 400
    stale); of it 12 s is writing the vectors in place. Four writers, 200 writes: **a write waited 57 s at the
    median for its vectors** (before 18.5 s), and none is stale. So the user's decision costs what was expected
    and a little more: exact vectors after a burst, about three times later. A head alone is as before (1.3 s a
    turn at the median); a batch is still cheaper for each head (0.3 s) than heads one by one.
  - Run: `pangloss-fastrp` 211 passed on Memgraph and 211 on Neo4j (before the mend, which has a pure test).

**7a.2 A URI at the similar route.** `GET /api/NAME/{id}/similar` takes `id: UUID`. For an entity class it takes
what `GET /api/NAME/{id}` takes: the route becomes `/{model_name}/{ref:path}/similar`, parsed by
`pangloss_api.routes.models.parse_reference` (with the route's own parameters, `profile`, `type`, `field`,
`limit`, left out of the URL's query), and `views.visible_item` resolves it with
`pangloss_cypher.lookup.resolve_id` in the transaction it already has. A document is found by its UUID only, as at
its own route.
- **Main first**: that `/{ref:path}/similar` is matched before the model's `/{ref:path}` (the app's router comes
  first: seen for the UUID form, not for a path), and what a URL that itself ends in `/similar` does.
- *Live* (`tests/live/test_vectors_routes_live.py`, both backends): a person made with a URL is asked by that URL
  and by its UUID: the same answer; a URL with a query string of its own; a URL nobody has: 404; a URL at a
  document class: 422; a merged entity's URL answers for its survivor.
- *Docs*: `vectors.md` ("The API"), `guide/vectors/`, the `TODO.md` item closed.
- **As built (2026-11-21)**, as the step says, with three things it did not:
  - `pangloss_api.routes.models.reference_from(request, ref, own)`: the parsing of a reference with a route's own
    parameters named, which `entity_reference` now calls; the similar route's are `profile`, `type`, `limit`.
  - **The new path also matched other apps' routes ending in `/similar`** (`/api/review/unreconciled/{id}/similar`,
    with `model_name = "review"`) whenever `pangloss_vectors` came before `pangloss_review` in `INSTALLED_APPS`. So
    the route has a route class of its own (`ModelRoute`, in `pangloss_vectors/api.py`) that is no match unless the
    first part is the name of a routable model; the request then goes on to the routes after it. `/api/Nothing/…/similar`
    is now the router's plain 404.
  - **An entity whose own URL ends in `/similar`** is no longer read at `GET /api/NAME/{that URL}`: the similar
    route takes the request (the path is matched to its last `/similar`) and looks for the URL without it. Taken
    by main, not asked of the user: the 404 says so, such an entity is read by its id, and its similar are at
    `…/similar/similar`. A merge gives the survivor the absorbed entity's URLs, so a merged entity's URL resolves
    to the survivor directly.
  - Run: `pangloss-vectors` 166 passed on Memgraph and 166 on Neo4j; `pangloss-api` 197 passed.

**7a.3 "No vectors for this", without the package.** Two ways, both decided:
- `VECTORS_EXCLUDE = ["Note", …]`: classes by name, with their subclasses; a name that is no model's is refused
  at `initialise()` by name (`PanglossInitialisationError`, as `VECTORS_PROFILES` is checked).
- The stand-ins of `hooks.stand_ins` have no vectors (decision 2 above), unless `VECTORS_INCLUDE` names them.
- One function says it: `meta.included(type_name)` becomes the class's `VectorsMeta`, then the settings, then the
  stand-in rule; everything that asks (the store, the class part, `pending_work_of`, the route's `excluded`)
  already asks it. The order when they disagree: a class's own `VectorsMeta(include=…)` declared by the project
  wins over the stand-in rule; `VECTORS_EXCLUDE` wins over everything (it is the project's last word).
- **`Explore` first**: every place that reads `VectorsMeta.include` or `FastRPMeta.include` without going through
  `meta.included`, and whether what is included is in a part's `signature()`. **It must be**: a class newly
  excluded has stored vectors, and only "rebuild due" removes them. Main settles whether the graph part follows
  the same rule (an excluded class is still walked through, or is out of the joins: today's `FastRPMeta.include`
  is the second, and `VECTORS_EXCLUDE` should mean "no vector, still joined").
- *Pure* (`tests/test_vectors_meta.py`): each rule and each order of disagreement; a subclass of an excluded class;
  a wrong name refused; the class part's signature changes when the setting does and not otherwise.
- *Live* (`tests/live/test_vectors_rebuild_live.py`, `test_vectors_marks_live.py`, both backends): with review
  installed, an `Unreconciled` gets no row in any part, leaves no mark of the kind `vectors`, and is in no result;
  with `VECTORS_INCLUDE` it does as before. A class in `VECTORS_EXCLUDE` the same. After the setting
  changes, the status says a rebuild is due, and after it the old vectors are gone.
- *e2e* (`e2e/test_similar.py`): a hearing's "Similar" lists no unreconciled mention (it does today); its row in
  `e2e/COVERAGE.md`. Some of `helpers.outside_similar`'s uses may then be unneeded: left as they are.
- *Docs*: `vectors.md`, `guide/vectors/`, `settings` reference, the skill's line on stand-ins if it has one.

- **As built (2026-11-21)** (`briefs/7a.3.md`, `7a.3-report.md`), with these departures:
  - **A head of a class with no vectors is still marked** (the step said it "leaves no mark"). Excluded means
    "no vector is stored" and nothing else: the class is still in the joined graph, so a write of such a head
    changes the graph vectors of what it names. `pending_work_of` no longer asks `include` at all, which also
    mends the same hole for `VectorsMeta(include=False)` (its neighbours were wrong until a rebuild). Main's call.
  - **The signature is the store's, not each part's**: `store.part_signature(part)` is the part's own when nothing
    is excluded, and otherwise mixed with `meta.excluded()` (every class without vectors, whatever says so). A
    project with nothing excluded keeps its signatures; one with review installed, or with an `include=False`
    class, is told once that a rebuild is due, and that rebuild removes the old vectors.
  - **Until that rebuild a search already leaves the class out** (`search_query(..., excluding=True)`, only when
    something is excluded: the query is otherwise the one it was).
  - `VECTORS_INCLUDE` naming a class that is no stand-in is allowed and does nothing.
  - Not done: the graph part is not in the step's live tests (the e2e test has it); the query with `$excluded`
    was not profiled.
  - **The second reading** found nothing that keeps, writes or shows the vectors of a class newly excluded on the
    straight path (the setting changes, every process starts again, a rebuild). It found three things off it,
    **none mended, all cured by a rebuild, the first for the user**:
    1. *A setting changed and changed back with no rebuild between, or two processes that disagree.* The stored
       signature is written only by a rebuild, and the worker refreshes in place by today's rule whatever the
       vectors in use were built with. So: exclude a class, let the worker drop some of its vectors, include it
       again: the signature matches, nothing is due, and those items have no vectors until next written. The
       mirror leaves vectors stored (hidden by the search's filter). A rebuild run before the server is started
       again does the same. **For the user**: the general cure is that a part whose signature is not the one it
       was built with is not refreshed in place until it is rebuilt; that also stops every refresh after any
       change of the models until someone rebuilds, which is a larger change than this step, so it is not taken.
    2. Until the rebuild, a search can be short: the class's vectors still hold places among the nearest, and the
       search stops asking at 4,096. The status says a rebuild is due.
    3. An item dropped in place keeps its vector of a profile that does not weigh the part that dropped it, until
       the rebuild (hidden by the filter).
  - **Found, not this step's**: `uv run pytest packages/pangloss-testing -k query_costs` fails 1 of 4 on its own
    (review's URI-claims worker runs statements while a read is counted), with and without this change (tried on
    a stash). In `TODO.md`.
  - Run: `pangloss-vectors` 198 passed on Memgraph and on Neo4j; `pangloss-fastrp` 212 and 212; `pangloss-review`
    17; `e2e/test_similar.py` 7.

**7a.4 The similar of a field's types.** `type` may be given several times; `field=Activity.carried_out_by`
means the concrete entity classes that field can hold, wrappers hopped over and stand-ins left out
(`initialise_incoming_relation_definitions.entities_reached` and `utils.get_concrete_types`: nothing new is worked
out). A `type` need no longer be a group.
- *The search*, two ways, chosen for each request: if every type asked for is in a group that holds nothing else
  asked for (persons and groups, both searchable), each group's index is asked and the hits merged by score;
  otherwise the profile's whole index is asked with `item.type IN $types` in `search_query`, and the loop that
  asks again while short does the rest.
- **Main first, a measurement** (`notes/similarity-evaluation/field_types_recall.py`, `:7690`; the truth is the
  exact ten nearest of those types, by brute force over the stored vectors): for types that are 50%, 5% and 0.5%
  of the items, how many of the ten the second way finds before `MOST_FETCHED`, and what it costs; and that the
  merge of two group indexes equals the truth. **Decide there** what a rare type that is no group gets: an exact
  scan of that type's vectors when they are few (a count the state can hold), or an answer that says it is short.
- *Pure* (`tests/test_vectors_fields.py`, new): a field's types for a plain relation, a union, a wrapper
  (`InRole[Agent]`), a wrapper in a wrapper, a field that takes a stand-in; `Model.field` that is no relation: 422
  by name.
- *Live* (`tests/live/test_vectors_search_live.py`, `test_vectors_routes_live.py`, both backends): planted
  persons and groups near one item: `type=Person&type=Group` gives both in the order of their scores, equal to
  the whole search cut by hand; one type that is a group and one that is not; `field=` equal to the same types
  named; a nested document's field.
- *Not here*: anything in the interface. A form's suggestions are phase 10's (10.4).

- **As built (2026-11-21)** (`briefs/7a.4.md`, `7a.4-report.md`; the measurement `field_types_recall.py`, `.txt`),
  **not as the step said**:
  - **The whole index filtered by type is not built.** Measured on `:7690` (329,000 profile vectors): an item's
    nearest in the whole index are items of its own kind, so for a class that is a quarter of the items half of
    the true ten were found and fewer than ten given; asking for 65,536 mended neither and cost 1.3 s.
  - **Instead, an exact scan in the database** for every class asked for that no group covers
    (`search.scan_query`): the profile vectors of those classes, found by a new plain index on
    `:PGProfileVector(type)` (the package's migration `0002_profile_vector_type`, so **`pangloss migrate` is
    needed**), each scored by a new `Dialect.vector_cosine` (Memgraph `vector_search.cosine_similarity`; Neo4j
    `vector.similarity.cosine`, checked there; a conformance test). 1,800 vectors 13 ms, 15,000 95 ms, 82,000
    0.53 s: linear, so a large class searched often should be a group. A group all of whose classes (that have
    vectors) are asked for goes through its index; the two are merged by score.
  - `nearest(types=…)` is new; `group=` means what it did, and one `type` that is a group answers as before.
    `pangloss_vectors/fields.py` works out a field's classes. More refusals than listed: a field that reaches no
    entity class, a `type` with no concrete class. `type` takes a trait too.
  - A scan that comes back short asks once how many vectors its classes have, and stops if it has had them all.
  - One existing test changed (it refused `type=Birth` as "not a group", which is now answered).
  - Not done: Neo4j at size (with few vectors Neo4j scans the type index whole for each class; the plan test
    plants 8,000 to see the seek); the scan was timed by main's trial only.
  - Run (by the builder): `pangloss-vectors` 226 passed on Memgraph, its live tests 113 on Neo4j; the conformance
    file 12 and 12; `pangloss-cypher` 60, `pangloss-memgraph` 81, `pangloss-neo4j` 174, `pangloss-fastrp` 212.

**7a.5 A type of a typology is suggested as the real class only where it is used as one.** The user, 2026-11-21:
the types of a typology **have vectors** (they are not to be put in `VECTORS_EXCLUDE`), but one is **not suggested
as the real class unless the data uses it as one**: "Banker" is a `RoleType`, and is suggested among the roles only
if something names it where a `Role` goes. That it could be (`TypologyMeta(name="RoleType", also=Role)` puts the
class `RoleType` below `Role`, and the switch `is_concrete` gives a type the label `Role`) is not enough. Today the
store works out an item's groups from its class (`meta.groups_of(type_name)`), so every `RoleType` is in the group
`Role` and is listed among the roles like any role.
- *The rule, general, naming no package*: where a class leaves labels to the data (`__labels_unmanaged__`, which
  the typology's generated class sets), an item is in the group of such a class, and is a result for a `type` or a
  `field` of it, only if **a relation that takes that class points at it**: a reference from a document or an
  entity, through wrappers or not. Having the type (`HAS_TYPE`) and the hierarchy (`is_subtype_of`) are relations
  to a `RoleType`, not to a `Role`, and do not count. A search narrowed to `RoleType` gives every type.
- **A search that is not narrowed lists such a type, as a type** (the user, 2026-11-21: confirmed as taken).
- **Its vectors are never taken away** (the user, 2026-11-21): a type has its vectors in every part whether or
  not anything uses it as a role, is found as a `RoleType`, and can be searched from. The rule is only about
  whether it is *given as a result of the other class*.
- **Main decides between two ways, the first preferred**: (a) *when a search is read*: the stored vectors and
  their groups stay as they are, and the search's query leaves out a hit of such a class that nothing names as
  the other class. Nothing stored changes and the worker is not concerned; the cost is that unused types hold
  places among the nearest of the group's index (the search asks again while short, and a typology is small).
  (b) *when vectors are written*: the group is given by use, as described below, and follows other heads'
  writes. To be taken only if (a) measures badly.
- *What changes*: the rows a part gives carry the item's class only (`VectorRow.type`), so the store asks, for
  the items of such classes only, which are referred to as the other class, when it writes their groups; 7a.4's
  filter by `item.type IN $types` goes by the group for them. **The group follows writes of other heads**: the
  first document that names "Banker" as a role puts it in the group, and the last one deleted or changed takes it
  out. The worker already has both: what a written head names now, and what it named before (`Changed.before`).
- **`Explore` first**: how "referred to" is asked today for `Usage(include_only_when_referenced=…)`
  (`pangloss_models/usage.py`; the interface's lists and the RDF dump follow it), and whether that query can tell
  a reference as a `Role` from `HAS_TYPE`; which fields can hold the other class
  (`initialise_incoming_relation_definitions`). **Main**: the query, planned on both backends, and its cost to a
  rebuild at size (one more read for the classes concerned, none for the others).
- *Pure* (`tests/test_vectors_meta.py`): which classes the rule is for, and which relations count for each; a
  class without unmanaged labels is as before.
- *Live* (`tests/live/test_vectors_typology_live.py`, new, both backends; `pangloss-typology` installed in the
  test's models): two types switched on, one named as a role by a document, near a real role: `type=Role` gives
  the role and the one type; `type=RoleType` both; a type that only something *has as its type* is not given as
  a role; a document that names the second is written, one turn of the worker: it is given too; that document
  deleted: gone again; the same through a wrapper (`InRole`); a rebuild gives what the worker left.
- *e2e* (`e2e/test_similar.py`): a role's "Similar" narrowed to roles lists no type that nothing uses as a role.

- **As built (2026-11-21)** (`briefs/7a.5.md`, `7a.5-report.md`; the trial `used_as_trial.py`): **way (a), when
  a search is read**. Nothing stored changes, and neither the worker nor the rebuild is concerned: the first
  document that names "Banker" as a role makes it a result at once, and its deletion takes it out at once.
  - `pangloss_vectors/by_use.py` works out from the models, once, for each class with `__labels_unmanaged__`,
    the classes it is only by use and the pairs (the stored type of the node an edge comes from, the edge's name)
    that count. A wrapper's node is stored under its base class (`InRole`), so its pair is `("InRole", "target")`.
    `pangloss_typology` is not named.
  - `nearest(asked=…)`: the names a search was narrowed by, as given (`types` alone cannot tell `type=Role` from
    `type=Role&type=RoleType`). The clause is in `search._hits`, which the group's index and the exact scan both
    use, and only when the request has a class by use (otherwise the query's text is what it was).
  - The query is a `CALL (item) { … RETURN count(user) AS uses }`, not `EXISTS`: the shape `fragments.uses_of`
    already runs on both backends. It counts every referrer of a type instead of stopping at the first.
  - The referrer must also not be a computed relation's, nor a derived document, nor the item itself.
  - **Main's and the builder's calls, for the user if they matter**: a field declared `Role | RoleType` gives
    types by use (it would take reading the annotation to tell); two uses of one generic wrapper that give the
    same pair, one counting and one not, count, with a warning logged (cannot happen with a typology, only with a
    project's own class that sets `__labels_unmanaged__`).
  - **The second reading found two faults, both mended with a test**: what an entity merged into another names
    through a wrapper still counted (the wrapper has no `merged_into` of its own: the holder's is now asked, as
    `fragments.uses_of` does); and `nearest(types=["Role", "RoleType"])` without `asked` took both as asked for
    and gave every type, silently: it is now refused (`ValueError`: say what was asked). Its doubts, not settled:
    a `has_type` field that subclasses a field of roles writes a second edge under the parent's name, which has no
    pair and does not count (is that "having it as a type" or "named where a Role goes"? the user's); **the
    typology lets a type used as a role only through a wrapper be switched off** (`pangloss_typology.graph.uses`
    counts only referrers that are documents or entities), after which the search still gives it as a role (in
    `TODO.md`; not this step's).
  - **No e2e test**: in the e2e project `RoleType` is `also=Role` but `Role` is not a group, and the interface's
    menu offers groups only; the models were left alone.
  - Found on the Neo4j run: 7a.4's plan test failed once of four (Neo4j planned as on an empty database before
    its index statistics were sampled); it now waits for them (`db.prepareForReplanning`), three runs green.
  - Run: `pangloss-vectors` 254 passed on Memgraph and on Neo4j (after the mends), `pangloss-typology` 62 and
    62, `pangloss-fastrp` 212 and 212.

**Phase 7a is done when** the five steps' `TODO.md` items are closed, the suite is green whole, and 7a.1's and 7a.4's
figures are written down.

**7a.6 A burst: estimates at once, exact after** ⏳ (planned 2026-11-21 after 7a.1's figures; **not built**).
The user, on seeing that an exact burst puts a write's vectors about a minute behind: exact, yes, but not
necessarily straight after a large push; "maybe" estimates first and exact vectors after. Taken as the direction,
to be confirmed when the step is given out.
- *What*: when a batch is past the cap together, the graph part first writes the approximate vectors of the heads
  written (`approximately`: one ring read and the stored vectors of the neighbours; in 7a.1's measurement the
  estimate itself was a few seconds, the other 14 s of the old 18 s were spent finding out the batch was too
  large) and counts them stale; then refreshes in groups as 7a.1 does, each exact vector replacing its estimate
  and the stale count going down by it. What is past the cap alone stays an estimate, as now.
- *Main first*: whether both happen in one turn of the worker (simplest: the marks are completed when the exact
  pass is done, and writes that arrive meanwhile wait behind it as today), or the estimate completes the turn and
  the exact pass is queued behind newer writes (a second kind of mark, or the stale count driving it). Measured on
  `:7690` with `measure_worker.py`: how long until a write has *a* vector, and until it has the exact one.
- *To ask the user*: whether a very large push (thousands of heads) should skip the exact pass and leave it to a
  rebuild ("not necessarily after a large bulk-push").
- *Tests*: pure (`test_fastrp_part.py`): the order of the writes, an estimate never replaces an exact vector of
  the same turn, the stale count after each pass. Live (`test_fastrp_worker_live.py`, both backends): a batch
  past the cap: after the first pass every head has a vector and is counted stale; after the turn they equal a
  rebuild and the count is what is past the cap alone; a turn stopped between the passes leaves estimates
  counted stale, and the next turn or a rebuild puts them right. ★ second reading: can an estimate outlive its
  exact vector, or the stale count stay too low.

### The end of phase 7a (2026-11-21)

**`./run_tests.sh` whole on `9243b7e4`**: ruff, `ty` and the skill's check passed; Memgraph 1791 passed; without a
database 3871 passed and **one failed**; `pangloss-neo4j` 174; Neo4j 1685; e2e 353. The failure
(`pangloss-history`, `test_a_write_makes_a_record_with_its_content`) passed alone: the history listener keeps the
schema position it first read, and a test of another package in the same worker had left one. The test's fixture
now forgets it; not a fault of this phase's code. That file and the three packages mended below were run again,
not the whole suite (`pangloss-fastrp` 212, `pangloss-vectors` 254, `pangloss-history` 114, on Memgraph).

**`/code-review`** (medium) on `similarity-next-phases..HEAD`, ten findings:

| Finding | What was done |
|---|---|
| `given_by_use`: a field declared with a class above the by-use class (its own base) did not ask it "as itself" | Mended (`by_use.py`: any class it is by class). No test of its own |
| `RememberingReader`'s bound counted nodes only, not the edges it holds | Mended: it counts every id and answer of the five reads, and `REMEMBERED_CAPS` is 40 (2 million at the default cap: the measured burst asked for 1.6 million, so it is as measured). `seen` is still never cleared (a node for each id read). **Not measured again** |
| An entity's URL whose own query has `type`, `profile`, `field` or `limit` is misread at the similar route | Not mended: the same is true of `incoming_limit` at the entity's own route. Such an entity is asked by its id. In `TODO.md` |
| The scan finds vectors by `type` alone and filters the profile after: its cost grows with the number of profiles and generations | Not mended; in `TODO.md` (an index on profile and type together, planned on both backends) |
| `meta.excluded()` is worked out again at every call, several times a request | Not mended; in `TODO.md` (a cache forgotten with the models, as `by_use.rules()` has) |
| A group's index with a by-use class stops at 4,096 fetched, where the scan goes on | Not mended: a typology is small. Said in `vectors.md`'s terms in `TODO.md` |
| `by_use._registered_above` and `meta._names_above` are one walk written twice | Not mended; in `TODO.md` |
| Every part is due for a rebuild once after this is installed over review or an `include=False` class | As decided (7a.3 "As built") |
| A class without vectors is still walked by the graph part, and its heads still marked | As decided (7a.3 "As built"); **the cost to a project that excluded a class to keep it out of the pipeline is real, and is the user's to weigh** |

**Decided by the user, 2026-11-21: all four stay as built.** A class without vectors is still walked by the graph
part and its heads still marked (a project that wants it out of the graph too says `FastRPMeta(include=False)`);
a part that is due for a rebuild is still refreshed in place (the gap of a setting changed and changed back is
accepted: a rebuild cures it); an entity whose URL ends in `/similar`, or has `type`, `profile`, `field` or `limit`
in its own query, is asked by its id; a `has_type` field that subclasses a field of roles is not a use of the type
as a role. The burst is step 7a.6 (planned, "maybe"). What follows is the list as it was asked.

**For the user, from phase 7a** (all in `TODO.md`): whether a part due for a rebuild should still be refreshed in
place (7a.3); whether a class without vectors should still be marked and walked (above); a burst is exact but its
vectors come about a minute later, not 18 s (7a.1); an entity whose URL ends in `/similar`, or has `type=` in its
query, is asked by its id (7a.2); `has_type` fields that subclass a field of roles (7a.5).

## Phase 8: `pangloss-names`

Branch `vectors-8-names`, from `vectors-7a-leftovers`. A part named `name`: the folded trigrams of an item's names,
hashed to a fixed dimension and weighted by rarity, with tables of name variants applied first. For finding
candidates; review's `likeness` stays what it is, for exact comparing.

**8.1 The planted world.** Main. The trial code of 2026-11-11 (`proso.py`, `reconcile_exp.py`) is gone, and the
scratch data has no truth to rank against, so the first step makes one, kept in the repository:
`notes/similarity-evaluation/planted.py`, a seeded generator of a prosopography on `pangloss_testing.similar_models`
(people in families, with shared names, spelling variants and given-name variants; factoids that name them through
`InRole` and identifications, with dates; mentions of the same person under other spellings; the truth as a file
beside the data). Two outputs: a small world in memory for pure tests (`pangloss_testing.planted`, a few hundred
people), and JSON Lines for `pangloss memgraph bulk-load` and `pangloss neo4j bulk-load` at 300,000 nodes. The
second is also the large Neo4j database of today's models that 3.5 and phase 13 lacked.
- *Pure* (`packages/pangloss-testing/tests/test_planted.py`): the same seed gives the same world; the truth names
  only what is in it.
- *Measured*: the base on it, before any new part: people right first by graph and class alone (the figure every
  later phase is compared with), on both backends. Into `notes/similarity-evaluation/README.md`.

### 8.1 as built (2026-11-21 and 22)

`pangloss_testing.planted` (the generator, `places`, `within`; 5 pure tests) and
`notes/similarity-evaluation/planted.py` (`write`, `empty`, `load`, `rebuild`, `base`; what it printed is
`planted_base_memgraph.txt` and `planted_base_neo4j.txt`). It works from code as the two `bulk-load` commands do
(`bulk_ingest`, `bulk_upload.upload`), not through a project: `similar_models.declare()` declares its classes in a
function, which no app's `models.py` can import. `Group` and `Place` of `similar_models` take ids of their own.

- **The size.** `people=32_000` is 122,777 records (38,564 `Person`s, of which 6,427 are mentions; 1,280 groups,
  800 places, 82,133 factoids): **302,239 nodes of the models, and 629,927 nodes in all** with the records of who
  made each head and 204,910 marks left for the criteria and derived workers, which the load does not run.
  1,330,652 edges. The file is 47 MB and takes 0.7 s to make.
- **Loaded** (8 writers): Memgraph 206 s, Neo4j 284 s. **Rebuilt** (class and graph parts, the default profile):
  Memgraph 187 s (class 8 s, graph 49 s, the profile combined and indexed 130 s), Neo4j 104 s (8, 34, 62).
  224,247 vectors of each. The suite of 8.4 was running on the same machine for part of both.
- **The base, by graph and class alone**, on both backends (6,427 mentions; the person a mention is, ranked among
  the 32,137 people, the other mentions left out):

  | | Right first | Among the five nearest | Among the ten |
  |---|---|---|---|
  | Memgraph | 0.0% | 33.1% | 47.5% |
  | Neo4j | 0.0% | 33.3% | 47.2% |

  **The graph never puts the right person first**: the people a mention is named beside (the person's family and
  fellows) share a document with it and are nearer it than the person, who shares none. The class part changes
  nothing here (every candidate is a `Person`). So the graph says whose company a mention keeps, and something
  else has to choose within it: the name (8.2 on), and in phase 10 the rule that who is named beside a mention is
  not the mention.
- The two backends' graph vectors are not the same vectors (the factoids get their ids at the load, and a stop's
  random start comes from its id), and give the same quality.
- A search narrowed to `Person` (an exact scan, 7a.4, of 38,564 vectors): 307 ms at the median on Memgraph, 183 ms
  on Neo4j. **A class searched this often wants `VectorsMeta(searchable=True)`**; `similar_models`' `Person` has
  none.
- **Name and graph together, before the part exists** (`names_with_graph.py`, `.txt`: the stored graph vectors of
  the Memgraph and name vectors made by 8.2's maths, by a profile's `Σ w·cos / Σ w`):

  | | Right first | Among the five | Among the ten |
  |---|---|---|---|
  | Name alone | 36.6% | 80.5% | 89.1% |
  | Name 1, graph 0.25 | 45.0% | 89.7% | 95.6% |
  | Name 1, graph 1 | 4.2% | 88.3% | 97.5% |
  | Name alone, with the table of variants | 42.0% | 90.5% | 95.3% |
  | Name 1, graph 0.25, with the table | 63.0% | 97.2% | 98.4% |
  | Name 1, graph 1, with the table | 4.8% | 93.3% | 98.9% |

  A little graph helps much, and much graph puts the family (who share the surname) before the person. So the
  demo's profile `who` (8.7) is name 1, graph 0.25, and 8.6 measures the weights between.
- The scratch databases: `pangloss-memgraph-planted` (`:7706`, test/test) and `pangloss-neo4j-planted` (`:7707`,
  neo4j/test-password), each with this world and its vectors. The data files are in `/tmp/planted/large` and are
  one command to make again (`planted.py write`, the same seed).

**8.2 The maths.** Main, as `maths.py` of `pangloss-fastrp` was: `pangloss_names/maths.py`, no database, numpy at
most. `fold` (the fold review uses for `label_key`: `Explore` finds where it is; if it is review's own it moves to
`pangloss-models` as a general function, with review importing it), `trigrams`, `hashed(trigrams, dimension)`,
`weighted(counts, rarity)`, `canonical(tokens, table)`.
- **Decide here** (main, on 8.1's small world): the dimension (`NAMES_DIMENSION`; the vector index of 128 took
  146 s to build over 520,000 in 2026-11-11); and where rarity comes from. Rarity is a count over every name, so a
  refresh cannot recompute it: it is fixed at a rebuild, stored with the generation, and read by `refresh` and
  `overlay`. So a refresh is exact against the last rebuild's table, and the table going old is one more reason
  for "rebuild due" (a count of names written since).
- *Pure* (`tests/test_names_maths.py`): folding (case, accents, punctuation, word order); a name and its variant
  are nearer than two different names; a rare name outweighs a common one; hashing is the same in any process (no
  `hash()`); the empty name gives no vector.
- *Pure, a regression* (`tests/test_names_planted.py`): on the small world, the right person among the five
  nearest by name alone, with and without the table of variants, each above a floor set a little under what is
  measured. A change that costs quality fails a test.

### 8.2 as built (2026-11-21)

`packages/pangloss-names/src/pangloss_names/maths.py` (the package has a `pyproject.toml`, a README and an empty
root so far; 8.3 makes the rest), `tests/test_names_maths.py` (43 pure tests, written by `builder` from the
docstrings as the second pair of eyes; it found no fault) and `tests/test_names_planted.py` (9, the floors).
Measured by `notes/similarity-evaluation/names_planted.py` (`.txt`), on the planted world at 32,137 people and
6,427 mentions, by name alone; "first" counts every namesake of the right person before them (half the people share
their name with another):

| | Right first | Among the five nearest |
|---|---|---|
| No rarity, 256 | 31.5% | 69.7% |
| Rarity by the trigram, 256 | 31.0% | 69.4% |
| **Rarity by the word, 256** | **36.6%** | **80.5%** |
| The same, with the table of variants | 42.0% | 90.5% |
| No rarity, with the table | 41.8% | 91.4% |
| Rarity by the word at 32, 64, 128, 512, 2,048 (no table) | 28.5, 33.0, 35.5, 37.4, 38.1% | 64.8, 74.2, 78.3, 81.8, 82.6% |

- **Decided: rarity is by the word, not by the trigram.** The step said trigrams "weighted by rarity"; by the
  trigram it costs quality (the trigrams two spellings of a name do not share are the rare ones, so the difference
  is what gets the weight). By the word, every trigram of a word weighs as the word is rare: a surname counts for
  more than a given name. It is worth 11 points among the five nearest without a table of variants, and nothing
  with one (the table already makes the given names agree). The planted surnames are evenly common, so what rarity
  among surnames is worth on real names is not measured.
- **Decided: `NAMES_DIMENSION` is 256.** Half of what there is to gain from 128 to 2,048, for twice the length.
- **Where rarity is kept**: `Rarity` is the count of items with names and, for each word two or more of them have,
  how many (a word one item has weighs as a word never seen, so the table holds only shared words: 4,887 words in
  38,564 names here, of which the kept ones are fewer). It is made at a rebuild and stored with the generation
  (8.3); a refresh weighs by it, so it is exact against the last rebuild's table.
- **`fold` did not move**: `pangloss_models.fold` (lower case, accents) was already general; review's `label_key`
  is its own and stays. The name part's `fold` is that and a cut into words.
- The floors (1,500 people, three seeds): among the five nearest above 80% without the table and 93% with it,
  among the ten above 98% with it, and the table worth 5 points to the mentions under a variant.
- `pangloss_testing.planted` gained `places` and `within` (how well vectors find who a mention is), and its
  entities say `create_new` (an id given to a `Create` is otherwise taken for a reference).

**8.3 The package and the part.** `builder`. The scaffold as `pangloss-fastrp`'s (pyproject, `_install`,
settings, README, `run_tests.sh` line 110's list, `packages.md`, the skill and its check, `guide/packages.md`);
`meta.py` (`_names_meta = NamesMeta(fields=["label"], include=True)`: which fields are names; entities are in and
documents out unless a class says otherwise); `part.py` (`rebuild`: one read of the names in pages, the rarity
table, the vectors; `refresh`: the written heads, by the stored table; `overlay`: the heads of a plan; `local`
true; weight 0, decision 4); `store` of the table.
- **Main keeps**: the query that reads the names (on `:7690` and Neo4j, for its plan), and where the table is
  stored (a node of the part's own beside `PGVectorState`, or a property of it: read `store.py` first).
- *Pure* (`tests/test_names_meta.py`, `test_names_part.py`): the slot inherited, refused on a field that is no
  text; the signature changes with the fields, the dimension and the table's hash, and with nothing else.
- *Live* (`tests/live/test_names_part_live.py`, both backends): the part's suite of 8.4.

**8.4 A suite every part passes.** `builder`, from `test_fastrp_worker_live.py`. The writes that file makes
(create, an update that adds, drops and replaces, delete and undelete, merge and its undo, publish and unpublish
under both values of `VECTORS_GRAPH_SEES`) and the claims it checks become `pangloss_testing/parts/`: given a part
and a function that computes its vectors the slow way, after each write and one turn of the worker the stored
vectors equal the slow way's; nothing gone keeps a vector; an overlay equals the same payload written; a rebuild
under writes loses none. The graph part's tests call it and must pass unchanged; the name part and the time part
call it. Behaviour is said by a suite, once.
- *Runs*: `pangloss-fastrp` and `pangloss-vectors` whole on both backends before and after, the same counts.

### 8.3 as built (2026-11-22, after 8.4)

`pangloss_names` (`meta.py`, `part.py`, `settings.py`; `builder`, from `briefs/8.3.md`, its report beside it), and
in `pangloss-vectors` a general hook that the step did not foresee. `implementation_docs/names.md` (🚧, a stub
until 8.7) and `vectors.md` say it.

- **Where the table is kept: a part may have `kept()`**, text that the rebuild just finished worked out over every
  item and that its refresh needs. A part does not know its generation, and the switch comes after `rebuild`
  returns, so the rebuild asks for it (`getattr`: the class and graph parts have none) and stores it before the
  switch as `(:PGVectorKept {part, generation, text})` (`store.keep`); `store.kept(part)` gives the text of the
  generation in use; `drop_older` and `drop_generation` take it with the vectors. A rebuild that stops before its
  switch leaves the text in use as it was, and `next_generation` counts kept texts, so its number is not given out
  again. An index `PGVectorKept(part)`: **migration `0003_vector_kept` of `pangloss_vectors`, so `pangloss
  migrate` is needed.**
- **`NamesMeta(fields=("label",), include=True)`**: with no slot an entity has names (its label) and a document
  none; inherited, a subclass's own overriding. A field is `str`, `str | None` or `list[str]` (each item a name);
  anything else is refused at `initialise()`, as is the slot on a wrapper, an embedded object or an edge model.
  A class `pangloss-vectors` gives no vectors has no names.
- **The part `"name"`**: local, weight 0 (in no profile until `VECTORS_PROFILES` weighs it). The signature is the
  classes with names and their fields, the dimension and the table of variants. The kept table is parsed once for
  a generation and remembered in the process, by the generation and when it was built (a database emptied and
  built again starts its numbers again).
- **Every vector a refresh writes is counted stale**: it is weighed by a table that does not count it, which is
  what `VECTORS_REBUILD_AFTER` means by "left out of date". So a project that sets it gets a new table after that
  many names written.
- **The second reading** (a fresh agent, given the step and the diff) found two faults, both mended with a test:
  a head whose class was changed in place to one without names kept its name vector (a refresh now looks at every
  head written, and removes the name vector of one whose class has none); and a part built whose kept table is not
  there made a refresh do nothing and say nothing (it now raises `RebuildDue`, which the worker reports as it goes
  on). Three things it found are not mended (`TODO.md`): the worker refreshes by today's settings a part that is
  due for a rebuild (as the user decided for the other parts); the stale count also counts writes made before a
  rebuild and refreshed after it; a lost lease.
- **The suite's claims do test the part**: with its `refresh` made to do nothing, 4 of the 15 failed (the others
  write only documents, which have no names in `similar_models`).
- Runs: `pangloss-names` 112 on Memgraph (22 live on Neo4j before the two mends), `pangloss-vectors` 274 (live 145
  on Neo4j), `pangloss-fastrp` 215. 8.4 on Neo4j: `pangloss-fastrp` live 66, `pangloss-vectors` live 140.

### 8.4 as built (2026-11-22, before 8.3, which calls it)

`pangloss_testing/parts/` (`writes.py`, `suite.py`; `builder`, from `briefs/8.4.md`, its report beside it; stopped
once by the usage limit and went on from a message). `implementation_docs/vectors.md`, "The suite of a part", says
how a part calls it.

- **A base class, `PartSuite`**: a part's test module subclasses it and names its parts with their slow ways
  (`parts = {"graph": slow}`); each claim is a test of its own. The installed apps and the settings come from the
  conftest (`parts.installed_apps("pangloss_fastrp")`, `parts.settings_extras(...)`), since they are made once for
  a session. A hook `also(step, ...)` holds what one part alone asserts.
- **15 claims**: after each of 8 writes and one turn the stored vectors are the slow way's, of exactly the same
  ids, and nothing a write took away keeps a vector of any part or profile; delete and undelete; merge and its
  undo; publish and unpublish under each value of `VECTORS_GRAPH_SEES`; an overlay writes nothing and equals the
  payload written (a factoid, and a person); writes during a slowed rebuild are all there after it and one turn.
- **One write is new**: an entity renamed (the name part's; no graph or class vector moves by it).
- **The graph part's worker test calls it**, with the class part checked beside it as before; it keeps as its own
  the criteria worker's new candidate, the cap and the batch in groups. 16 of its tests became 15 of the suite's
  (the replaced statements are now part of "nothing gone keeps a vector"). `"logged_in"` is now tested for the
  publish and unpublish, which it was not. **The class part is called through the suite too**
  (`packages/pangloss-vectors/tests/live/suite/`), compared at 10⁻⁸.
- **The claims are not empty**: with every part's `refresh` made to do nothing, 14 of the 15 failed (the rename is
  the one that moves no graph or class vector).
- Runs on Memgraph: `pangloss-fastrp` 212 → 215, `pangloss-vectors` 254 → 269.
- **For phase 9**: `similar_models` has no dates, so the time part needs a dated payload and write added to
  `writes.py`.

**8.5 Tables of variants.** `builder`. `NAMES_VARIANTS`: a file in the project (CSV: a canonical form and its
variants), read at `initialise()`, refused by line when wrong. Its hash is in the signature, so a changed table
makes a rebuild due for this part alone.
- *Pure* (`tests/test_names_variants.py`): variants found; a variant of two canonical forms refused; a changed
  file changes this part's signature and no other's.
- **A typology as a table is not in this step.** A typology has labels by language and one parent, and no
  alternative labels: what "a typology as a table" would mean (a type's subtypes as its variants?) is the user's
  to say when it is wanted.

**8.6 By a name, and at size.** `builder`, then main. `pangloss_names.vector_of(text)` and `pangloss names search
"Jon Smyth" --type Person` (through `nearest(vector=…)`; `guide/cli.md`). No route yet: phase 10's is the one a
client asks.
- *Live* (`tests/live/test_names_search_live.py`): a spelling variant and a namesake are found, ranked; an
  unpublished item is not shown to a reader who is not logged in.
- *Measured* (main, 8.1's large world on both backends): rebuild and refresh times; what the extra index costs a
  small write; right first and in the top five by name, by graph, and by both, against 8.1's base (2026-11-11:
  label alone 54% right first, label and context 78%, 99.6% in the top five; with variants 86% → 94%).

### 8.5 and 8.6 as built (2026-11-22; the measurement is below, "8.6 measured")

`builder`, from `briefs/8.5-8.6.md`, its report beside it. `pangloss_names/settings.py` (the table), `by_name.py`
(`vector_of`, `search`), `cli.py` (`pangloss names search`).

- **`NAMES_VARIANTS`** is a path to a CSV file (UTF-8, a byte-order mark allowed): a canonical form, then its
  variants, a line each; blank lines and lines beginning with `#` skipped. A relative path is from the directory
  of the settings module. Read once for the settings and forgotten with the models; **a running server sees a
  changed table only when it starts again**. Refused at `initialise()` by file and line: no variant, an empty
  cell, a cell of two words, a variant of two forms, a variant that is a form, a form on two lines, a file that is
  not there or not UTF-8. The hash in the signature is of the table's content, so a comment or the order of lines
  changes nothing, and no table is the hash the part already had.
- **`vector_of(text)`** weighs by the kept table; `NotBuilt` (a `RebuildDue`) if the part was never built.
  **`search(text, types=, profile=, k=, see_unpublished=)`**: the profile named, or the first by name that weighs
  the name part; none is a `ValueError` that says what to set.
- **What a hit's score is**: the query has only the name part, so the score is `cos(names) × sqrt(w_name / Σ w of
  the parts the hit has)`: with name 1 and graph 0.25, 0.894 of the cosine of the names for a hit with a graph
  vector and the cosine itself for one without. **An item that nothing names is lifted above one that is named.**
  The order among hits with the same parts is the order of the names. Said in the docs; whether a search by a name
  should weigh only the name (a profile of the name alone has no such lift) is for phase 10.
- **The step's own example ranks badly**: "Jon Smyth" is nearer "Joan Smithers" than "John Smith" (0.27 against
  0.50 in a world of five). Short names with two letters changed share few trigrams: what the name part finds is
  one change of spelling, or a variant the table knows.
- `pangloss names search TEXT [--type NAME ...] [--profile NAME] [-k 10]` shows unpublished documents (the command
  line is the project's owner); `guide/cli.md` has it.
- Runs: `pangloss-names` 145 on Memgraph, its live tests 35 on Neo4j.

### 8.6 measured (2026-11-22)

Through the part, on 8.1's large world (32,137 people, 6,427 mentions, 302,239 nodes of the models), on both
backends, 2026-11-22 (`notes/similarity-evaluation/planted.py`; `planted_names_*.txt`). "Right first" counts everyone
as near as the right person before them. Tests of other steps were running on the same machine for part of it.

| Weights | Right first | Among the five nearest | Among the ten |
|---|---|---|---|
| Graph alone (8.1's base) | 0.0% | 33.1% | 47.5% |
| Name alone, no table of variants | 36.6% | 80.5% | 89.1% |
| Name 1, graph 0.25, no table | 45.2% | 89.7% | 95.6% |
| Name alone, with the table | 42.1% | 90.6% | 95.4% |
| Name 1, graph 0.1, with the table | 72.5% | 95.8% | 97.6% |
| **Name 1, graph 0.25, with the table** | **63.6%** | **97.2%** | **98.5%** |
| Name 1, graph 0.5, with the table | 28.2% | 96.9% | 99.1% |

(Memgraph's figures; Neo4j's are within 0.3 of each. The trial of 2026-11-11, on data that is lost: label alone 54%
right first, label and context 78%, 99.6% among the five.) The more the graph weighs, the more often the people named
beside a mention, who share its surname, come before the person: a little graph is worth 20 to 30 points right
first, and much graph costs all of it. Among the five nearest it hardly matters between 0.1 and 0.5.

| | Memgraph | Neo4j |
|---|---|---|
| The name part rebuilt (40,644 vectors: read, the table, the vectors written) | 13.3 s | 10.0 s |
| The profile `who` combined and indexed (224,247 vectors of 384) | 234 s | 98 s |
| A search by a name through the profile's index, 20 asked (300 mentions' labels): the person among them | 96.0% | 96.0% |
| The same narrowed to `Person`, an exact scan of 38,564: the person among them | 97.0% | 96.7% |
| A search through the index, at the median | 150 ms | 12 ms |
| A search by the exact scan, at the median | 756 ms | 572 ms |
| A new person written (with the marks for the workers) | 14 ms | 12 ms |
| The worker's turn after it (every part and both profiles) | 760 ms | 201 ms |

- **The profile is the cost, not the part.** A profile holds a vector for every item that has any of its parts, so
  `who` has one for each of 224,247 documents and entities though only 40,644 have names: combining and indexing
  them is 18 times the name part's own rebuild on Memgraph.
- **The index holds for a query of one part** (96.0% against 97.0% by the exact scan), though the query has zeros
  where the stored vectors have a graph part. That was not known before (2.4 measured queries made as the stored
  vectors are).
- **Not measured apart**: what the name part alone adds to a worker's turn (the turn is all the parts'), and why
  Memgraph's search through the index is 150 ms here.

### 8.7 as built (2026-11-22)

`builder`, from `briefs/8.7.md`, its report beside it.

- **The demo**: `pangloss_names` installed; `VECTORS_PROFILES = {"who": {"name": 1, "graph": 0.25}}` (`"default"`
  is not written there and is as it was: class 0.1, graph 1); `NAMES_VARIANTS = "name_variants.csv"`, 27 lines of
  the given names the demo's people have, beside `settings.py` (a relative path is from the settings module).
  **Migration `demo_app` 0025 is three vector indexes and nothing else** (`pgv_who_384`, and the same for the
  groups `Person` and `Statement`). Tried on a scratch copy and a scratch Memgraph, both removed: migrate, populate,
  rebuild (3.9 s), and `pangloss names search "Guido of Spoleto" --type Person` gives `Wido of Spoleto` at 1.0.
  **`:7688` was not touched: it needs `pangloss migrate` (`pangloss_vectors` 0003, `demo_app` 0025) and `pangloss
  vectors rebuild`, on the user's word.**
- **The docs**: `implementation_docs/names.md` (✅), `vectors.md`, `status.md`, `packages.md`, `demo-setup.md`,
  `guide/vectors/names.md` and the guide's indexes, the skill.
- **For the user** (`TODO.md`): every entity of the demo has names by the default, and some labels are not a
  person's name (sources and books, Zotero's records, an occupation, a feast): an unnarrowed search by a name finds
  them and the table of rarity counts their words; nothing was excluded. And the graph's weight in `who`: 0.1 is
  better right first (72.5% against 63.6%), 0.25 among the five (97.2% against 95.8%).
- **Found, not mended** (`TODO.md`): the demo's `add_people.py` gives fields that migration 0021 removed and
  fails; `demo-setup.md` §6 says the demo installs everything but `pangloss-zotero`, and it installs it.

**8.7 The demo and the docs.** `builder`. `implementation_docs/names.md` (✅ with what is built), `vectors.md`
(the parts), `status.md`, `guide/vectors/` (a page on names), the demo (a profile `who` of name and graph on
`Person`, a small table of variants; a migration that is one more index; **`:7688` untouched**).

**Phase 8 is done when** a search by a name returns variants and namesakes ranked, on both backends, and the
figures of 8.6 are written.

### The end of phase 8 (2026-11-22)

**Done as the phase asks**: a search by a name returns variants and namesakes ranked, on both backends, and 8.6's
figures are written ("8.6 measured").

- **`./run_tests.sh` whole on `a56379e3`** (the script was cut off by a time limit in its Neo4j stage, and that
  stage and e2e were then run by their own commands): ruff, `ty`, the skill's check passed; without a database
  3,983; `pangloss-neo4j` 174; Memgraph 1,847 and **2 failed**; Neo4j 1,741 and **2 failed** (the same two); e2e
  352 and **1 failed**. None failed when run alone.
  - The two: tests of `pangloss-fastrp` that said the registered parts are exactly `class` and `graph`. In the
    whole run another package's tests have imported `pangloss_names` in the same process, and a part is registered
    when its package is imported. They now say "at least". (So a rebuild builds every part that is registered,
    whether or not its app is installed: in a project a part's package is imported only when it is installed.)
  - The e2e one: `test_login.py::test_declining_to_log_in_again_is_when_the_page_shows_no_one_logged_in`, the
    dialog to log in again not shown within 5 s. Nothing of this phase is in the interface; it passed alone.
- **`/code-review`** (medium) on the phase's diff: ten findings. **Mended**, with tests where one was missing:
  the name part counted as stale every vector a refresh wrote, so a project with `VECTORS_REBUILD_AFTER` would
  have rebuilt after that many saves of people whose names had not changed (it now counts only a vector that is
  new or differs from the one stored, which also answers the second reading's point about writes made before a
  rebuild); `NamePart.vector` took a plain string as its letters; the suite's slowed rebuild was left waiting with
  its lease held if a write failed before it was let go; `planted.within` divided by nothing for a world with no
  mentions. **Said, not changed**: a planted mention's kind is against the person's canonical name, not the
  stored label. **Not mended** (`TODO.md`): the overlay of an update; the folded table of variants made again at
  each call; two copies each of "an item a reader could be shown" and of the rules of a table of variants. Two
  were already known and decided (a part due for a rebuild is still refreshed).
- **After the mends**: `pangloss-names`, `pangloss-fastrp`, `pangloss-vectors` and `pangloss-testing`'s own tests
  together on Memgraph, four workers: 644 passed. The same three packages' live tests on Neo4j, two
  workers: 246 passed. `e2e/test_login.py`: 13 passed. The whole suite was not run again after the mends.
- **For the user**, all in `TODO.md`: which of the demo's entities have names; the graph's weight in `who` (0.25
  or 0.1); a search by a name lifts an item nothing names; and the demo's database, which needs `pangloss migrate`
  and `pangloss vectors rebuild`.

## Phase 9: the time part

Branch `vectors-9-time`, from `vectors-8-names`. A part named `time`: for a document with a date, soft bumps over
the date's bounds, so that vague dates that overlap are near and a recurring event's years are apart.

**9.1 The package.** `builder` (with 9.3). `pangloss-dates-vectors` (decision 3): it depends on `pangloss-dates`
and `pangloss-vectors`, and holds nothing but the part. `pangloss-dates` is not changed.

**9.2 The maths.** Main. `maths.py`: a date's `earliest_fuzzy`, `earliest_strict`, `latest_strict` and
`latest_fuzzy` (days) to a vector: centres every `DATES_VECTOR_WIDTH` years (2 in the trial; 1 was too narrow)
over `DATES_VECTOR_RANGE`, a bump of full height between the strict bounds falling to nothing at the fuzzy ones;
a document with several dates is the sum; a `Recurrence` is its pattern, not a year.
- **Decide here**: the dimension. Five centuries at 2 years is 250; whether hashing the centres to fewer costs the
  result is measured on 8.1's world before the number is fixed.
- *Pure* (`tests/test_time_maths.py`): the same year is 1; overlapping vague dates are near; ten years apart is
  near 0 at a width of 2; a date outside the range has no vector and is counted; a recurring event's two years are
  apart. *A regression* (`tests/test_time_planted.py`): an event's other reports among its ten nearest, above a
  floor (the trial: 95% → 99.5% with the part).

**9.3 The part.** `builder`. `rebuild` (one read of every `Date` node with its holder's head, in pages: the
query of `pangloss_calendar.graph._dated` is the model), `refresh` (the dates under the written heads; `local`
true), `overlay` (the dates of a plan); weight 0 in the default profile, as the name part.
- **Main keeps**: the query, planned on both backends at size.
- *Live* (`tests/live/test_time_part_live.py`, both backends): 8.4's suite; a nested statement's date gives the
  statement and its head a vector (the rule is written in the step's brief once main has decided whose it is).

**9.4 Entities, decided.** Main, on 8.1's world: whether an entity's span (the dates of the documents that name
it) is worth its cost. If it is, the part reads the joins through `pangloss-fastrp`'s reader when that package is
installed, and the part stops being `local` for entities. If not, the step is a paragraph in the docs.

**9.5 Docs and the demo.** As 8.7: `implementation_docs/dates.md` or a page of its own, `guide/vectors/`, a demo
profile with time on `Statement`.

**Phase 9 is done when** a profile with time finds an event's other reports on both backends.

### 9.2 as built (2026-11-22)

`packages/pangloss-dates-vectors/src/pangloss_dates_vectors/maths.py` (a bare package beside it, which 9.1 fills),
`tests/test_time_maths.py` (19 pure tests), `tests/test_time_planted.py` (7, the floors) and
`tests/time_planted_support.py`. **Where it differs from the step:**

- **No range, and a fixed dimension: the years go round a ring.** The step had a centre every
  `DATES_VECTOR_WIDTH` years over `DATES_VECTOR_RANGE`, and asked whether hashing the centres to fewer costs the
  result. Measured (below): beside the graph it costs nothing, down to 32 places. So the centres are a fixed
  number of places (`maths.Ring(dimension=128, width=2.0)`) and the years go round them: two dates
  `dimension × width` years apart (256) have the same vector. Within that many years the ring changes nothing at
  all (it is not a hash: neighbouring years are neighbouring places); beyond it time alone cannot tell them apart,
  and the graph does. What this buys: **no setting of the range** (`pangloss-dates`' own defaults, the years 1 to
  1600, would have been 801 places for every dated item), **no date outside it** (the step's "has no vector and is
  counted" is gone), and one dimension whatever a project's years are. The settings are to be
  `DATES_VECTOR_WIDTH` (2) and `DATES_VECTOR_DIMENSION` (128), in 9.3.
- **A date is its four bounds as a line in pieces** (1 between the strict bounds, falling to 0 at the fuzzy ones)
  **blurred by a logistic bump whose spread is the width**, read at each centre. Exactly, with no sum over days:
  a bend blurred by a logistic curve is `softplus` and a step blurred is the logistic function, so a date is four
  of them (and no `scipy`: a Gaussian would have needed `erf`). 300,000 dates in 0.9 s.
- **Several dates of an item**: each at length one, then added (a long period does not drown a day).
- **A `Recurrence` is its lifetime**, as its bounds say it: nothing of its rule is in the vector. (The step's "its
  pattern, not a year" is read as: not one year of it. "A recurring event's years are apart" is of the statements
  of each year, which is what the trial measured and what is planted.)
- **The cosine by the gap** (years, at the width 2): 0 → 1, 1 → 0.92, 2 → 0.73, 3 → 0.51, 5 → 0.18, 10 → 0.005.
  It is the same wherever the dates are to about a hundredth (the centres are a width apart: 0.918 or 0.930 for a
  year apart). A year in its decade 0.85; a decade and the next 0.14.

**The planted world has dates** (`planted.world(dated=True)`, `similar_models.declare(dated=True)`: every
statement may say `when`, a `Date` of `pangloss-dates`). The people, the mentions and every factoid are the same
with or without (the dates have a generator of their own), so 8's figures stand. Everything happened on a day,
and a factoid says it as its source knew it (the day 40%, the month 15%, the year 30%, some years it was within
15%). Added after the rest: **a sixth of the gatherings told once more** (fewer of the people, the date said its
own way), and **dues paid year after year** (one family in ten: six to twelve years, each payment reported twice,
by the same person to the same group, so that nothing but the date tells one year's from the next). The truth is
`world.events` and `world.series`. `packages/pangloss-testing/tests/test_planted.py` has four tests more.

**Measured** on a dated world of 5,986 people (18,301 factoids; 1,200 reports of a gathering told twice, 2,374 of
a payment), in the scratch Memgraph `:7702`: the stored graph and class vectors of the factoids, with the time
vectors made from the truth (`notes/similarity-evaluation/planted.py time`, output in
`planted_time_memgraph_small.txt`). The share of an event's other reports that are first, among the three
nearest, and among the ten nearest factoids of a report (those as near counted before it):

| Weights | Told twice: first / 3 / 10 | Year after year: first / 3 / 10 |
|---|---|---|
| Graph (class 0.1 changes nothing) | 89.0% / 96.7% / 98.8% | 5.6% / 16.0% / 52.4% |
| Time alone, width 2 | 15.2% / 26.3% / 33.1% | 13.1% / 25.6% / 31.2% |
| Graph + time 0.25, width 2 | 97.8% / 99.4% / 99.8% | 40.2% / 78.9% / 99.9% |
| **Graph + time 0.5, width 2** | **98.4% / 99.6% / 99.7%** | **57.4% / 92.8% / 100%** |
| Graph + time 1, width 2 | 98.3% / 99.3% / 99.7% | 80.2% / 98.9% / 100% |
| Graph + time 0.5, width 1 | 98.5% / 99.4% / 99.6% | 91.2% / 99.9% / 100% |
| Graph + time 1, width 1 | 97.3% / 98.9% / 99.3% | 95.5% / 100% / 100% |
| Graph + time 0.5, width 5 | 98.0% / 99.7% / 99.8% | 23.8% / 54.4% / 97.6% |

- **With time, an event's other report is nearly always among the nearest** (the trial on real data: 95% to
  99.5% in ten), and a payment's other report, which the graph cannot find among the other years' (5.6% first),
  is among the three nearest.
- **The ring costs nothing beside the graph**: at the width 2, 512, 128, 64 and 32 places give the same figures
  to 0.3 of a point (time alone falls, from 33% in ten to 26% at 32 places, which no profile is).
- **The width is the project's.** Here a width of 1 tells the years of a payment apart far better (91% first
  against 57%) and costs the gatherings nothing: the planted dates are vague by years only one time in seven. On
  the real data of the trial 1 was too narrow (95.6% in ten against 99.1%). The default stays 2, the trial's; a
  project with events year after year and exact dates sets 1.
- The graph vectors of a payment's reports are not the same for each year (each report's own nodes are in
  them), so time has to outweigh that noise: why "first" rises with the weight of time.

**The floors** (`test_time_planted.py`, 1,500 people, three seeds, time alone, no database): of what happened
year after year, the other report of the year is first among the reports of the same thing (measured 99.7% to
100%; the floor 98%); an event told twice is among the nearest tenth of all the factoids by time alone (100%;
99%) and the nearest hundredth (83% to 90%; 75%).

**For 9.3, decided here**: whose vector a date is. A date held by a date (an end of a range or a period) is part
of that date and counts for nothing itself. Any other date counts for **what holds it, if that is a document or
an entity**, and for **the head it is under** (a factoid has the dates of its statements, and each statement its
own). A date held by anything else (a wrapper, an embedded object) counts for the head only. A date that is only
unknown (`precision` `unknown`) counts for nothing. The queries are tried on the small database
(`notes/similarity-evaluation/dates_query_trial.py`: a page by the index of `PGIndexableNode(id)`, the dates
under some heads by `PGIndexableNode(head_node_id)`); at size when the large dated world is loaded.

### 9.1 and 9.3 as built (2026-11-22)

By `builder` from `notes/similarity-evaluation/briefs/9.1-9.3.md` (its report beside it, 17 choices).
`pangloss_dates_vectors`: `settings.py` (`DATES_VECTOR_DIMENSION`, 8 to 2048, 128; `DATES_VECTOR_WIDTH`, more
than 0 and at most 100 years, 2; both refused at `initialise()` when the app is installed), `part.py` (the part
`"time"`: `local`, weight 0), `__init__._install`. `pangloss-dates` is not changed. **As the step says, and:**

- **Whose vector a date is**: as 9.2 decided, said in `part.counts_for`. "A document or an entity" is said as the
  class part says it (not a citation). A date a head holds itself (a person born) has the head's id as its
  `head_node_id`, so the refresh's one query by `PGIndexableNode(head_node_id)` finds it.
- **`rebuild`** reads every date in pages and keeps them compactly (four integers a date, a pair for each item it
  counts for), then makes the vectors 1,000 items at a time (`maths.of_items`): never a matrix of every date.
- **`refresh`** is exact, and nothing is ever stale: the dates under the written heads, their vectors written,
  and the time vector removed of a written head, or a document under it, that has one stored and no date that
  counts now. Nothing if the part was never built.
- **`overlay`** walks the plan from its head through the planned nodes: a planned node with the label `Date` is a
  date, its bounds the `DBField`s on it, held by the node whose relation it is.
- **The signature**: the dimension, the width, the classes that have vectors.
- **The suite with dates** (`pangloss_testing/parts`): `PartSuite.dated`, and when it is true the payloads of
  every write say dates (a day, a year, a range, a period with an end unknown, a person born, a participant
  `during`: `similar_models.declare(dated=True)` adds `Person.born` and `InRole.during`). Undated, the payloads
  are what they were: the other parts' tests give 1,650 passed before and after.
- **Mended by main after the report: a date longer than the ring.** It went round more than once and its ends
  counted twice (a year in the middle of a 300-year period was less near it than its ends). The maths now takes
  the most of a date at each place, not the sum: a date longer than the ring is at every place alike, a little
  like every date (0.16 with a year) and no more like one than another. A range whose start is unknown runs from
  `DATES_EARLIEST_YEAR` and is such a date. `tests/test_time_maths_more.py`, three tests.
- **Found, not mended, not of this phase** (`TODO.md`): a merge fails when the absorbed entity has an embedded
  object (a date) and the survivor has none. A strict `xfail` in the part's live tests says the behaviour wanted.
- **Left** (`TODO.md`): `_kept` and `BELOW_QUERY` now in three packages; a date on a wrapper counts for the head
  only; an `OngoingDate` alone has a vector; the overlay of an update plan.

Tests: the package 96 passed and 1 xfailed on Memgraph (21 + 7 + 3 pure of the maths, 40 pure of the part and
settings, 26 live: the suite's 15 with dates and 11 of the part's own); the live tests of the four packages of
similarity on Neo4j, 271 passed and 1 xfailed.

### 9.3 measured (2026-11-22): the part at size, on both backends

The dated planted world at size (seed 1: 32,137 people, 96,693 factoids, 137,337 records; 856,790 nodes in all,
147,450 of them dates, 116,030 not held by a date; 6,400 reports of a gathering told twice, 11,360 of a payment),
loaded into the scratch Memgraph (`:7706`) and Neo4j (`:7707`); a profile `when` of graph 1, class 0.1, time 0.5
(273 places: 128 + 17 + 128). `notes/similarity-evaluation/planted.py reports`, output
`planted_reports_memgraph.txt` and `planted_reports_neo4j.txt`; the queries' plans `dates_query_trial_*.txt`.

| | Memgraph | Neo4j |
|---|---|---|
| Every date read with what holds it and its head (15 pages) | 1.8 s | 2.7 s |
| The time part rebuilt (212,723 vectors) | 52.7 s | 25.4 s |
| The profile `when` combined and indexed (253,367 vectors of 273) | 181 s | 107 s |
| Told twice, through the profile's index (k 40): the other report first / in 3 / in 10 | 98.0% / 98.7% / 98.7% | 97.7% / 99.0% / 99.0% |
| Told twice, narrowed to `Factoid` (an exact scan) | 99.3% / 100% / 100% | 98.7% / 100% / 100% |
| Year after year, through the index | 56.3% / 90.0% / 99.3% | 60.7% / 90.7% / 100% |
| Year after year, exact scan | 56.7% / 90.7% / 100% | 60.7% / 90.7% / 100% |
| A search through the index, median | 103 ms | 12 ms |
| A search narrowed to `Factoid` (96,693 of them scanned), median | 1.19 s | 0.77 s |
| The time part's refresh in a worker's turn, one head | 0.2 s | not timed apart |

- **Phase 9 is done as it asks**: a profile with time finds an event's other reports on both backends. By the
  graph and class alone, from the same stored vectors (`planted.py time`, `planted_time_*.txt`): first 88.8%, in
  ten 99.0%; a payment's 5.8%, in ten 56%.
- **The index loses about one report in a hundred** against the exact scan (98.7% against 100% in ten), as phase
  8 found for names (96% against 97%).
- **The rebuild of the time part is the writing, not the reading or the maths** (1.8 s to read, under a second to
  compute; 212,723 vectors written in pages). Half the graph part's time on each backend.
- **A worker's turn after a new dated factoid took 5.2 s on Memgraph and 4.4 s on Neo4j, and that is the graph
  part**: the factoid written was a gathering at a place that many are at, and the graph part rewrote 247 vectors
  in 4.5 s of it; the time part's refresh was 0.2 s (`worker_turn_parts.py`). After a small factoid of two new
  people the whole turn is 1.3 s, each part about 0.2 s. (Phase 7a's burst and hubs; nothing of this phase.)
- The Memgraph bulk load stopped twice at its last step at this size ("Cannot get unique access to the storage"
  when the text indexes are made again, a snapshot being written): `pangloss memgraph bulk-recover` finishes it
  (`planted.py recover`). Not seen at 630,000 nodes in phase 8.

### 9.5 as built (2026-11-22)

By `builder` from `briefs/9.5.md` (its report beside it).

- **The demo**: `pangloss_dates_vectors` installed; a profile **`when`**: `{"graph": 1, "class": 0.1, "time":
  0.5}`, the default's parts at their own weights and time (`default` and `who` as they were, by
  `pangloss vectors weights`). The step's "with time on `Statement`" is not how a profile works: a profile is of
  every item, and `Statement`, a group, has an index of its own in it. Migration
  `demo_app/migrations/0026_addindex_addindex_addindex.py`: three vector indexes of 293 (`pgv_when_293`, and for
  `Person` and `Statement`), nothing else. **`:7688` untouched**: it now needs `pangloss migrate`
  (`pangloss_vectors` 0003, `demo_app` 0025 and 0026) and `pangloss vectors rebuild`, on the user's word.
- **Tried on a scratch copy of the demo** (its own container, removed): migrated, populated, rebuilt. By `when`,
  the nearest statements of "Leo crowns Charlemagne" (25 December 800) are the two other reports of that day
  (1.0000), then "Charlemagne goes to Rome" of 24 November (0.9994), then the activities of July 799 (0.876); by
  `default` all five activities are at 1.0000, which is what the part is for.
- **Which of the demo's classes get a time vector**: every statement (they are `Dateable`), `Factoid` and
  `DerivedFactoid` above them, and `Feast` (its `when`). Not `Person` (no date since migration 0021) nor
  `Source` (`written` is a plain `datetime.date`).
- **Docs**: `implementation_docs/dates-vectors.md` (✅), `dates.md`, `vectors.md` (four parts), `status.md`,
  `packages.md`, `README.md`, `demo-setup.md`; `guide/vectors/time.md` and the indexes; the skill's row.
- **For the user** (`TODO.md`): a `Feast`'s date is the calendar's, not when something happened; a statement
  inside `Negative` or `Hypothetical`, or ordered, has the date of what did not happen or was wished; what an
  `Inference`'s date means. Nothing is excluded.

### 9.4 decided (2026-11-22): an entity has no time vector from the documents that name it

Measured on the dated planted world of 5,986 people (1,197 mentions), who a mention is among the people
(`notes/similarity-evaluation/time_entities.py`, output `time_entities_small.txt`): the name made with the table
of variants, the stored graph vectors of `:7702`, and a time vector of each person and mention made from the
truth, of the dates of the factoids that name them (each date added, or one period from the first to the last:
the two give much the same).

| Weights | Right first | In five | In ten |
|---|---|---|---|
| Name | 50.0% | 97.2% | 99.6% |
| Name + time 0.1 | 73.6% | 99.2% | 99.8% |
| Name + graph 0.25 | 76.4% | 99.7% | 99.9% |
| Name + graph 0.25 + time 0.1 | 71.3% | 99.7% | 99.9% |
| Name + graph 0.25 + time 0.25 | 55.5% | 99.4% | 99.8% |
| Name + graph 0.1 | 80.5% | 99.4% | 99.7% |
| Name + graph 0.1 + time 0.1 | 78.4% | 99.4% | 99.8% |

- **By the name alone, when someone lived tells namesakes apart** (50% → 74% right first).
- **Beside the graph it adds nothing and costs a little**: the graph already says who is named with whom, which
  says when as well, and a person's family lived when they did, so time lifts them too.
- **Not built.** It would also have cost what the part has: a person's span depends on every document that
  names them, through wrappers, so the part would stop being local for entities and a write of a factoid would
  refresh the people it names. An entity's **own** dates (a `Person.born`) do give it a vector (9.3's rule):
  that is local. To come back to if a project has names and dates and no graph part.

### The end of phase 9 (2026-11-22)

**Done as the phase asks**: a profile with time finds an event's other reports on both backends ("9.3
measured").

- **`./run_tests.sh` whole on `c62b361a`**, every stage by the script itself: ruff, `ty`, the skill's check
  passed; Memgraph 1,874 and 1 xfailed; without a database 4,058; `pangloss-neo4j` 174; Neo4j 1,768 and 1
  xfailed; e2e 352 and **1 failed**. (The xfail is the merge fault, "9.1 and 9.3 as built".)
- **The e2e failure is not of this phase, and it is not understood.**
  `e2e/test_similar.py` fails now and then, a different test of it each time, always in the same way: the
  similar of an item just written never lists its family within 60 s. Run by itself eight to ten times: on this
  branch it failed about four times in ten, and **on `vectors-8-names` five times in ten** (nothing the e2e
  server loads differs between the two). At a failure every vector is stored (the graph and class vectors of
  all eight people, the profile's 16), nothing is pending and no lease is held, and the search still leaves the
  family out. Tried and not the cause: Memgraph's deleted entries in the index (`FREE MEMORY` between runs, and in
  the tests' `forget`), an old index (dropped and made again). Phase 8's whole run passed it once, phase 7's and
  7a's too. **For the user, in `TODO.md`**: it may be a fault of the search through Memgraph's vector index and
  not of the tests.
- **`/code-review`** (medium) on the phase's diff: seven findings. **Mended**, with tests: a group of dates
  worked out at once was sized by its narrowest date and made as wide as its widest, so one long date among many
  made them all as wide (908 MB for 20,000 dates and one range from the year 1; now cut by the widest, and a date
  wholly there for longer than the ring is said, not worked out); `DATES_VECTOR_WIDTH` had no lower bound, and
  a tiny one would have run a rebuild out of memory (now 0.01 to 100); the part's signature held every class
  with vectors, so any new class made a rebuild of the time part due (now the dimension and the width only: the
  store's signature already adds the classes left out). **Not mended** (`TODO.md`): a refresh removes vectors
  without the worker's guard against a batch whose lease was lost (the name part's does the same); the numpy
  work runs on the event loop (milliseconds a batch since the first mend); a date of a nested statement is
  blurred once for the statement and once for its head; the third copy of `_kept` and `BELOW_QUERY`.
- **After the mends**: `pangloss-dates-vectors` on Memgraph 98 passed and 1 xfailed; its live tests on Neo4j
  25 passed and 1 xfailed. The whole suite was not run again after the mends.
- **For the user**, all in `TODO.md`: the intermittent e2e fault; the merge that fails for an entity with an
  embedded object; which of the demo's dated classes should have a time vector (`Feast`, statements inside
  `Negative` and `Hypothetical`); the width (2, the trial's, or 1, which the planted world prefers); and the
  demo's database, which needs `pangloss migrate` (`pangloss_vectors` 0003, `demo_app` 0025 and 0026) and
  `pangloss vectors rebuild`.

### The user's answers after phase 9 (2026-11-22)

1. **The intermittent `e2e/test_similar.py` failure is found and fixed first**, before phase 10 (which stands on
   that search). Where to start is in `TODO.md`: ask the search through the index, and the exact scan, directly at
   the moment a test fails.
2. **The merge that fails for an entity with an embedded object is mended**, with its conformance test (the
   strict `xfail` in `packages/pangloss-dates-vectors/tests/live/test_time_part_live.py` then passes and loses
   its mark; the suite's payloads no longer need Dee born for Eve's merge).
3. **Which of the demo's dated classes have a time vector: left to main, who leaves them all in.** `Feast`
   and the statements inside `Negative` and `Hypothetical` keep theirs: the part has no way to leave a class out
   but `VECTORS_EXCLUDE`, which would take its other vectors too, and a feast with no start and end is longer
   than the ring and says nothing of when. To come back to only if such an item is seen crowding a result.
4. **The width stays 2.**
5. **The demo's database (`:7688`) is migrated and rebuilt** (by main, on the user's word, 2026-11-22, with a
   snapshot first): `pangloss_vectors` 0001 to 0003 and `demo_app` 0024 to 0026 applied; `pangloss vectors
   rebuild` in 42 s: class 17,709 vectors, graph 68, name 17,614, time 81; the profiles `default`, `when` and
   `who`. It is no longer waiting.

**So a new session does, in this order, on `vectors-10-reconcile` (from `vectors-9-time`)**: (a) the e2e fault,
(b) the merge fault, each committed and pushed when green, with the whole suite after both; then (c) phase 10,
its steps read again first with a `Plan` agent as challenger.

### The two faults, mended (2026-11-22)

**(a) The e2e fault was three faults, one of the product and two of the tests.** Each was caught by running
`e2e/test_similar.py` by itself until it failed, with a diagnostic that asked the database at that moment.

1. **Memgraph's vector index does not find items whose vectors repeat (the product's).** The failure first
   described ("the similar of an item just written never lists its family within 60 s") was this: Ann, Bea and
   Cyd, of one meeting, have one vector; at a failure all three were stored, in the generation in use, with the
   label of the group's index, the index said it held 16 entries, and a search of it for 40 gave 13, not those
   three, for the whole minute. An exact scan gave them at 1.00. Asked of Memgraph 3.14 alone
   (`notes/similarity-evaluation/lost_in_index.py`, `lost_in_index_sized.py`): of 2,000 nodes in families of three
   with one vector each, the index gives a node among the 21 nearest its own vector 31 times in 300, and 16 in 300
   when half the nodes share one vector (as items joined to nothing do); an exact scan 300. Writing once or in
   place, deleting and making again, and a small difference added to each vector made no difference worth the
   name. **Mended in the search**: a profile with at most `VECTORS_EXACT_UP_TO` vectors in use (a new setting,
   20,000 by default; my call, **confirmed by the user 2026-11-22**) is read whole and scored exactly, with no index asked
   (`search.scan_all_query`; `implementation_docs/vectors.md`, "Exact while it is small"); above that the index is
   asked as before. About 7 µs a vector on Memgraph (190 ms at 20,000 in the trial). **This bears on phase 10**:
   people who share a name and nothing else have one name vector, which is the case reconciliation is for, and
   the planted world's 224,000 vectors are above the default size. Open for the user (`TODO.md`).
2. **Two hearings that shared nothing (the test's).** The second hearing of
   `test_a_hearing_s_similar_lists_no_unreconciled_mention` was at -0.008 by an exact scan and by the index alike,
   and the route gives nothing at 0 or less: two items that share nothing have unrelated graph vectors, whose
   cosine is a little above or below 0 by the chance of their ids. Now one witness speaks at both.
3. **A wait that did not wait (the test's).** The fixture `families` waited until the family was first among the
   people. Before the graph part is worked out every person has the vector of the class alone, all eight are at
   1.00, and the tie is broken by id, which puts the family first: so a page could be loaded then, and
   `test_the_menu_of_types_narrows_the_similar_to_people` found no meeting on it. Rare while the index gave ties
   in any order, 5 runs in 20 once the search was exact. Now the fixture waits for Ann's meeting among her similar
   and for the family above 0.9.

Then the file by itself, run after run: see "Where the work stands" for the count. What it says for phase 10
besides the index: two items that share nothing are not at 0 but near it on either side, so candidates are
ranked, never counted on to be there or not; and `conftest.forget` deletes items behind the worker, so their
vectors stay (the search drops them when it matches each hit to its item).

**(b) The merge.** What the survivor takes of the absorbed entity's own nodes (an embedded object, the wrapper
of a relation, in the default values or in values given) was written under their ids, which belong to the
absorbed entity, and `check_ids_available` refused the write. Now `pangloss_cypher.merge._prepare` reads the ids
of the nodes below the absorbed entity (one statement more in the read of the pair) and gives the survivor's
values without them (`_as_new`), so they are written as new nodes; the absorbed entity keeps its own, and an
undo leaves both as they were. Conformance:
`test_the_survivor_takes_the_absorbed_entity_s_embedded_object_and_wrapped_relation_as_nodes_of_its_own`
(`test_merge.py`); the time part's test lost its `xfail`.

## Phase 10: `pangloss-reconcile` (provisional)

Branch `vectors-10-reconcile`. The steps are read again when the phase is reached: 8.6 and 9 decide its profiles
and its hand-set weights. What is fixed is the shape, and the two tests that define it: **nothing is written**, and
**an overlay equals the same payload written**.

| Step | What | Tests |
|---|---|---|
| 10.1 The hook in review | `pangloss_review.hooks.candidate_providers`: review's reconcile dialog asks for ranked candidates and does not know who gives them. With no provider it is as today. No use of it yet | Pure: providers called in order, one that fails is logged and skipped. Review's own tests unchanged |
| 10.2 The service | `POST /api/reconcile/candidates`: a `Create` payload whose unknowns are stand-ins. Validate, `plan_create`, each registered part's `overlay`, and for each unknown `nearest(vector=…)` narrowed to the types its field holds (7a.4). Candidates as reference views with a score for each part | Live, both backends (`tests/live/test_reconcile_candidates_live.py`): the count of nodes, of edges and of `PGPending` marks is the same before and after; the overlay's vectors equal those stored after the same payload is written; a reader who is not logged in sees no unpublished candidate; a payload that would be refused is refused the same way |
| 10.3 The second stage | A weighted score over name, context, time and class fit (hand-set until phase 11); reasons (shared neighbours by name); how likely "someone new" is; several unknowns ranked jointly; what is already in the mention's cluster of identity claims left out (if `pangloss-library` is installed, through a hook, not an import) | Pure (`tests/test_reconcile_score.py`): planted cases, one for each reason. Live: two unknowns in one payload. Measured on 8.1's world against 2026-11-11 (78% right first, 99.6% in five; two unknowns 79% → 94%; "someone new" AUC 0.83) |
| 10.4 The interface | Review's dialog shows the candidates, as `ReferenceChip`s with the reasons, above the picker it has; and a form's field suggests for a new mention as it is typed ("did you mean", `TODO.md`) | Unit (vitest); e2e (`e2e/test_reconcile_candidates.py`, rows in `COVERAGE.md`); the dev build |
| 10.5 The toolchain mode | Above a threshold it writes an `IdentificationByToolchain` for a person to confirm; never a merge | Live: one written and only one; below the threshold none; it is a suggestion in review's list |
| 10.6 Measured, written | Both backends on 8.1's large world: the time of a request by stage; Neo4j's overlay (267 ms against 37 ms in 2026-11-11) | `implementation_docs/reconcile.md`, the guide, `status.md` |

### Read again (2026-11-22): what in the provisional steps cannot work, and the steps as they are now built

The table above stays as it was written. It was read against the code of phases 2, 7a, 8 and 9 by main and, apart,
by a `Plan` agent asked one question (what in these steps cannot work). Eleven things, each checked in the code:

1. **No part's overlay gives the unknown a name, a class or a time.** The name part's overlay is of the plan's
   head only, and a stand-in's class has no names (it has no vectors: 7a.3); the class part's is of the head; a
   stand-in holds no date. "Each registered part's `overlay`" gives the graph alone, which 8.1 measured as never
   right first.
2. **By the default `VECTORS_GRAPH_SEES = "everyone"` the graph overlay of a reviewed document is empty.** A new
   document of a reviewed class is unpublished, `overlay_plan` takes `published` from the head, and
   `GraphMaps.is_in` leaves an unpublished node out. A factoid with an unknown in it is exactly such a document.
3. **The profile was not said, and the search would lose namesakes.** `default` weighs the name at 0; a narrowed
   class that is a group (the demo's `Person`) is asked through its index above `VECTORS_EXACT_UP_TO`, which does
   not find vectors that repeat; a query with no graph part lifts a hit that has none (8.5).
4. **Review's dialog has the id of a stored mention, not a payload** (and says "save the document first"). A
   stored mention has no vectors, and the stored document posted again as a `Create` is refused (its ids are
   taken).
5. **"The overlay's vectors equal those stored after the same payload is written" is false for the unknown**: the
   store keeps no vector of a stand-in.
6. **"Refused the same way" is more than validate and `plan_create`**: a write also resolves citations, makes the
   database model as its creators, fills templated labels, runs `check_before_create`, `checked_plan` and
   `citations.check_before`. Nothing runs these without writing.
7. **Time and class fit have no source**: an entity has no time vector (9.4), nor has the stand-in; the stand-in's
   class is `Unreconciled`. A search gives one score, not one for each part.
8. **A stand-in is in no cluster of identity claims** (clusters are of entities).
9. **"As it is typed" cannot be the service**: a half-filled form is not a valid `Create`, and an exact scan of
   38,000 people is 0.6 to 0.8 s (8.6).
10. **`IdentificationByToolchain` is a node of a document**: writing one is an update of the document that holds
    the mention (a new version), only where the field takes that wrapper, by a toolchain that must be named; and
    nothing in the step says what sets it off.
11. **The planted world has no stand-ins**: its mentions are `Person`s with stored vectors, so 8.6's figures are
    not figures of the service.

**What is decided from them** (main's calls, taken so that building could start in a session with no one to ask;
**none confirmed by the user**; each is also in `TODO.md`):

| | Taken as | Why |
|---|---|---|
| a | **A part says what an unknown's vector would be**, by a method it may have and need not (asked with `getattr`, as `kept` is): `unknown(plan, unknowns) -> {id: vector}`, "the vector an entity of these classes, with this label, put in the place of this node of the plan, would have". The graph part lays the plan over the database with the node as an entity of the class it stands for; the name part gives the vector of its label; the class part the vector of the class; the time part has none | 1, 5, 7. `pangloss-reconcile` then knows no part by name, and depends on `pangloss-vectors` alone |
| b | **The plan is laid over as if it were published** (in memory; the candidates found are still only those the reader may see) | 2. Otherwise the service is by name alone for every project with review and the default setting |
| c | **Which node is an unknown, and of what class, is said by the general hook**: a node of the plan whose class is a document of `hooks.stand_ins`; its class is the value of the property `StandIn.named_type` names (a new optional attribute: review's is `"unreconciled_type"`), or else the entity classes its field takes | The package imports neither review nor criteria. A `MatchesCriteria` has no `named_type` and no label: it is not an unknown in v1 |
| d | **Candidates are found exactly**: `nearest(exact=True)` (new) scans the classes the unknown stands for, whatever the size of the profile, twice: by the name alone and by the graph alone, 50 of each (the trial's first stage, 2026-11-11), by the profile `RECONCILE_PROFILE` names (by default the first, in the order of their names, that weighs both the name and the graph; refused at `initialise()` if the app is installed and none does) | 3. The user's answer of 2026-11-22: phase 10 plans its candidates with the index's fault in hand |
| e | **The second stage scores each part apart**: the vectors of the candidates are read by part (`store.read_part`) and the cosines made in Python; the score is a weighted sum (`RECONCILE_WEIGHTS`, by part, hand-set from 10.3's measurement), a part a candidate lacks counting 0. **No time, no class fit, no cluster in v1** | 7, 8. The classes are already those the field takes |
| f | **Two routes**: `POST /api/reconcile/candidates` (a `Create` payload) and `GET /api/reconcile/candidates/{id}` (a stored stand-in, by its id: its document is read, made an `Update` as review's `rewrite_part` does, planned with `plan_update`, and the same code runs) | 4 |
| g | **Review gains a place in its dialog, not a Python hook**: the reconcile panel draws what the interface modules give for the slot `reconcileCandidates` (the manifest's `slots`, as `/admin` has), each given the mention and `onPick`. No `pangloss_review.hooks`, and no package importing another if it is there | 4; the user's refusal of optional imports (2026-11-21) |
| h | **A create is checked without writing by one function of the core**: `pangloss_cypher.write_functions.checked_create(instance)` runs what a write runs before it writes, in a read transaction, and gives the database model and the plan | 6 |
| i | **"As it is typed" is not built in this phase**: it is a search by a name (8.6), which has no route yet; in `TODO.md` | 9 |
| j | **The toolchain mode (10.5) is not built until the user says what sets it off** (a command, an admin job, each upload), and whether a new version of each document it touches is wanted | 10 |
| k | **The planted world gains a mode with stand-ins** for 10.3 and 10.6: some hearings held back and posted to the service with an `Unreconciled` | 11 |

**The steps as they are now built**:

| Step | What | Tests |
|---|---|---|
| 10.1 A place in review's dialog | (g) `ReconcilePanel` draws the modules' `reconcileCandidates` above its picker; with none it is as today | Unit (vitest): none, one, `onPick` chooses the entity. Review's own tests unchanged |
| 10.2a The core | (c) `StandIn.named_type`; (h) `checked_create` | Pure: the hook. Conformance (`test_checked_create.py`): nothing is written (nodes, edges, marks counted); each refusal of a write is the same refusal (a reference that is not there, an id taken, a `before_create` that refuses, a citation); a templated label is filled |
| 10.2b The parts | (a) `unknown` on the graph, name and class parts; (b) inside the graph part's; (d) `nearest(exact=True)` | The part suite gains a claim: **the unknown's vector equals the stored vector of an entity made in its place** (a person of that label made, the same payload written naming them, the worker turned), and nothing is written. Live on both: `exact=True` finds repeated vectors in a profile above `VECTORS_EXACT_UP_TO` (set to 1 in the test) |
| 10.2c The package and the service | `pangloss-reconcile` (`requires = {"cypher", "vector_index"}`): (d), (e) with weights of 1, (f); candidates as reference views with a score for each part | Live, both backends (`tests/live/test_reconcile_candidates_live.py`), **written first**: the counts of nodes, edges and `PGPending` marks are the same before and after, on the error paths too; a reader who is not logged in sees no unpublished candidate and no stored stand-in of an unpublished document; a merged entity is not a candidate; a payload that would be refused is refused the same way; the stored route gives what the payload route gives for the same document |
| 10.3 The second stage | (k); the weights; reasons (the neighbours an unknown and a candidate share, by label, cut to what the reader may see); how likely "someone new" is; several unknowns of one payload ranked jointly | Pure (`tests/test_reconcile_score.py`): planted cases, one for each reason, and a seeded floor under the measured figure. Live: two unknowns in one payload. Measured against 2026-11-11 (78% right first, 99.6% in five; two unknowns 79% → 94%; "someone new" AUC 0.83) |
| 10.4 The interface | The module's `reconcileCandidates`: the candidates of the mention as `ReferenceChip`s with their reasons; one picked is the dialog's choice | Unit (vitest); e2e (`e2e/test_reconcile_candidates.py`, rows in `COVERAGE.md`); the dev build |
| 10.5 The toolchain mode | Not built (j) | — |
| 10.6 Measured, written | As it was: both backends at size, the time of a request by stage | `implementation_docs/reconcile.md`, the guide, `status.md` |

Who builds: 10.1, 10.2a, 10.2b (★ second reading: is anything written; is the unknown's vector an entity's),
10.2c (★: is anything written, or shown to a reader who may not see it) and 10.4 go to `builder`, a brief each;
10.3 and 10.6's figures are main's.

### 10.1 as built (2026-11-22)

`ReconcilePanel` draws what the interface modules give for the place `reconcileCandidates`
(`useModules().slot(...)`), under "Reconcile with" and above the picker, while no entity is chosen; each is
given `{ mention, onPick }` (`ReconcileCandidatesProps`, said in the module's `README.md`), and `onPick` is the
picker's. One still loading or one that fails draws nothing (each has its own boundary, as core's
`NewItemActions`), and with none the panel's DOM is as it was. Review's code says nothing of who fills the
place. A module cannot import another's file, so 10.4's module says the props' shape itself. Tests:
`ReconcilePanel.test.tsx` (5; each seen to fail against the fault it is for); the module's 67 pass and its type
check is clean, run by `builder` in a scratch copy of a built workspace. Nothing is seen in a browser until 10.4,
so no row in `e2e/COVERAGE.md` yet.

### 10.2a as built (2026-11-22)

- **`hooks.StandIn.named_type`** (`str | None`, None by default): the name of the property of the stand-in's
  document that says the one entity class a value stands for. Review's is `"unreconciled_type"`. Nothing reads it
  until 10.2b.
- **`pangloss_cypher.write_functions.checked_create(instance, *, created_by, toolchain, published, review_status,
  review_assigned_to)`** (among the backend's operations; no method of a model) gives the database model, its plan
  and the entities written in it that exist, and raises what the create raises, **by the same code**: the create
  and it now share `_prepare_create` (citations resolved, the database model made as the creators, labels filled,
  `@before_create`), `_asking` (what the transaction runs under), `_check_writer` and `_check_new_head` (the plan,
  `checked_plan`, `citations.check_before`), the last two in a read transaction. The create's queries are what
  they were (`test_query_costs.py` passes). Beyond the brief: it takes `review_assigned_to` (review puts it on the
  head and may refuse it), refuses a document that cannot be made on its own (as `Create.save` does before the
  create) and refuses while a migration runs.
- **What it does not refuse that a create would** (checked by a create only after its statements, so not without
  writing): a citation of a part of the document itself, cited bases given in the payload, what the apps run in
  the write's transaction (`hooks.in_write`: derived refuses there a derived document not made by its worker), a
  uniqueness constraint broken by another write at that moment. 10.2c's "refused the same way" is so far and no
  further.
- **Found**: `citations.resolve` changes the caller's `Create` in place (as a create does), only where an app
  resolves citations (`pangloss-derived`); each `to_db_model` gives new ids to nodes the payload gave none, so the
  ids of this plan are not those a later create of the same payload writes; a project's `@before_create` is run,
  and one that wrote would write here.
- Tests: conformance `test_checked_create.py` (4: nothing written, by counts of nodes, edges and `PGPending`
  marks and no write event; the plan is the create's; ten refusals the same by class and message, the counts
  unchanged after each; a templated label and the head's review properties). Memgraph, by `builder`: the
  conformance suite 1,007 passed (serially, 261 s), `pangloss-models` 1,490, `pangloss-cypher` 60,
  `pangloss-review` 18. Neo4j, by `test-runner`: `test_checked_create.py`, `test_create.py`, `test_citations.py`,
  `test_query_costs.py` and `test_label_templates_live.py`, 126 passed. **A first serial run of the conformance directory hung** at about 35% for 50 minutes
  (main stopped it); the tests near that place pass alone and the second run did not hang: cause not known,
  `TODO.md`.

### 10.2b as built (2026-11-22)

- **`pangloss_vectors.parts`**: `Unknown(id, type, label)`; the optional `unknown(plan, unknowns)` of a part, said
  beside `kept`; `unknown_vectors(plan, unknowns)` (by unknown, then by part; a part without the method is passed
  over, what a part raises is raised; an unknown whose class has no vectors is not asked about).
  **`pangloss_vectors.unknowns.unknowns_of(plan)`**: the nodes below the head, at any depth, in the order of the
  plan, whose class is (or is below) the document of a stand-in with a `named_type`, with a label that is not
  blank and the name of a class of entities; not a node inside an entity written in the document.
- **The class part**: the vector of the unknown's class (an abstract class has one too: as near each class below
  it). **The name part**: the vector of the label by the kept table and the variants, where `label` is a name
  field of the class (of any concrete class below an abstract one). **The time part**: no `unknown`.
- **The graph part** (`unknown_plan`; `overlay_plan` and it share `_overlaid`): the unknown's node laid out as a
  published node of its class (`stop_class`: an abstract class as the first concrete class of entities below it
  that is a stop, by name; a class out of the graph, nothing), reached by the plan's edges, with nothing of what
  the stand-in points at or holds; every node of the plan published, an update's head too; the rest of the
  database as `VECTORS_GRAPH_SEES` sees it. The old tree of an update is taken away.
- **`nearest(exact=True)`**: the exact ways whatever the profile's size; the route does not have it.
- **The suite's claim is exact** (`PartSuite`, run by all four parts' suites): `similar_models.declare(
  stand_in=True)` declares a `Mention` document and its `StandIn` (no review in `pangloss-testing`); the plan of a
  `CreateDB` with the mention beside Ada is asked of each part; then a person is made **with the unknown's id**,
  the mention in that same instance replaced by a reference to them, the instance written and the worker turned:
  each part's stored vector of the person is what it said of the unknown, to 10⁻⁵, and a part that said nothing
  stored none. Seen to fail with the graph vectors scaled by 1.001.
- **The second reading** (a fresh agent, the step's text and the diff): nothing written on any path, no other
  unpublished document reaches the vector, `nearest` unchanged without `exact`. Four lesser things:
  1. **mended**: an unknown beside a hub raised `maths.TooLarge` and took the other parts' vectors with it (the
     refresh was centred on every stop of the plan). `maths.overlay(only=...)` now reads the neighbourhood of the
     unknowns alone (as exact, and smaller), and past `FASTRP_REFRESH_CAP` they get no graph vector, logged, with
     nothing raised (a live test);
  2. left: `exact=True` is exact up to 4,096 fetched: more hidden vectors than that (unpublished, merged) scoring
     above the visible ones hide them. It errs towards hiding; `TODO.md`;
  3. left: a stand-in with relations of its own (an entity first written under it and named again elsewhere; a
     stand-in below a stand-in) is not laid out rightly. `Unreconciled` has none; `TODO.md`;
  4. the claim is of one unknown, a published create, a concrete class, in a wrapper. An unpublished head and an
     update are tested for the graph part alone; two unknowns in one plan (each computed with the other as an
     entity too) and abstract classes nowhere: 10.2c's and 10.3's live tests.
- Tests, Memgraph (`builder`): `pangloss-vectors` 297, `pangloss-fastrp` 221 (222 after the mend),
  `pangloss-names` 147, `pangloss-dates-vectors` 100, `pangloss-testing` 1,021. Neo4j (`test-runner`, the four
  packages' `tests/live`): 160, 69, 36, 27, all passed; the graph part's live file again after the mend, 18.

### 10.2c as built (2026-11-22)

`packages/pangloss-reconcile` (`implementation_docs/reconcile.md` 🚧): `settings.py` (`RECONCILE_PROFILE`,
`RECONCILE_FETCH` 50, `RECONCILE_WEIGHTS`), `candidates.py` (`candidates_of(plan, see_unpublished=, limit=,
only=)`: found by each part alone with `nearest(exact=True)`, scored part by part from `store.read_part`),
`score.py` (pure), `stored.py` (the plan of a stored document: read as the reader, made an `Update`, its database
model and `plan_update`, no check of an update run and nothing written; the plan keeps the stored ids), `api.py`
(`POST /api/reconcile/candidates`, validated and refused as the create route of the body's class;
`GET /api/reconcile/candidates/{id}`). It imports no part's package and not review.

- **A profile has to be named where several tie** (main, after the builder's finding): with the graph part
  installed `default` (class and graph) weighs as many parts with `unknown` as `who` (name and graph) and came
  first by its name, which finds nobody by a name. Several that weigh as many are now refused at `initialise()`
  with "set `RECONCILE_PROFILE`".
- **The two routes give the same candidates in the same order but not the same graph scores** (0.875 against
  0.907 in the test): each node of the joined graph starts from a vector made from its id, a payload's nested
  nodes get new ids each time it is planned, and the stored document has its own. The test of "the stored route
  gives what the payload route gives" makes the ids the same. So a score is good to about two places, and the
  docs say it.
- **Found, left (`TODO.md`)**: an `Update` made from a view (`editable(view.model_dump())`) whose nested documents
  are `create_with_id` reads each as a `Create` and is refused; review's `rewrite_part` would be too.
- A budget: one POST with one unknown is 13 read transactions and 57 statements on Memgraph (4 and more are the
  login; 33 the graph part reading the neighbourhood).
- Tests: Memgraph (`builder`) the package 41 (11 live), `pangloss-vectors` 297, `pangloss-api` 197. Neo4j
  (`test-runner`): the package's live 11, `pangloss-vectors` live 160.
- **The second reading** (a fresh agent: is anything written, is anything shown that may not be): **no write on
  any path, no leak**. Left to mend, given to `builder` with 10.3 (`briefs/10.3.md`, part A): no bound on the
  unknowns of a payload nor on `RECONCILE_FETCH`; the GET open to readers not logged in, and not cheap; a pydantic
  `ValidationError` (a stand-in below an entity head) and two refusals escaping the GET as 500, 422 and 400; a
  score of 0 for every candidate when `RECONCILE_WEIGHTS` zeroes every part; a zero vector of the unknown counted
  in the denominator; a stored vector of another dimension raising.

### 10.3 measured (2026-11-22): the service on the planted world

`planted.py reconcile` (`notes/similarity-evaluation/planted_reconcile_memgraph_small.txt`): on the dated world of
5,986 people and 1,197 mentions (`:7702`; 47,777 vectors in the profile `who`, the table of variants), each of
300 mentions' own factoid posed again as a payload with a stand-in in the mention's place, planned and not
written, the candidates asked widely, the other mentions' people left out (8.6's condition).

| Scored by | Right first | Among five | Of the 146 whose name several have: first / five | "Someone new", AUC by the best score |
|---|---|---|---|---|
| name alone | 71.3% | 98.7% | 43.2% / 97.9% | 0.65 |
| graph alone | 0.0% | 30.7% | 0.0% / 30.1% | 0.50 |
| name 1, graph 0.1 | **79.3%** | 99.3% | 58.2% / 98.6% | 0.68 |
| name 1, graph 0.25 (the profile's) | 78.0% | **99.7%** | 58.2% / 99.3% | 0.67 |
| name 1, graph 0.5 | 65.3% | 99.7% | 50.0% / 99.3% | 0.62 |
| name 1, graph 1 | 30.0% | 97.0% | 27.4% / 95.2% | 0.54 |

- **It is the trial's figure** (2026-11-11: 78% right first, 99.6% among five; shared names 70% there, 58% here,
  where a mention is in one activity only). The person is among those found, by one part or the other, every time.
- **The weights stay the profile's**: 0.25 and 0.1 are within a mention or two of each other, and 0.25 is what
  the demo's `who` has. `RECONCILE_WEIGHTS` stays empty by default.
- **"Someone new" is not answered as a number**: the best score tells a mention whose person is there from one
  whose person is not with an AUC of 0.67 (0.83 in the trial), too little to print a likelihood. The answer has
  the scores; "nobody of these" is the reader's to say. `TODO.md`.
- **A request is 1.26 s at the median** (slowest 1.58 s): two exact scans of the people and the overlay. By
  stage, and on Neo4j, in 10.6.
- **Several unknowns ranked jointly: not built.** The planted world has one mention to a factoid, so nothing
  measures it; each unknown is ranked by itself, laid out with the others as entities beside it. `TODO.md`.

### 10.3 as built (2026-11-22): the mends, the reasons, the floor

- **The mends of 10.2c's second reading**: `RECONCILE_MOST_UNKNOWNS` (20; a plan with more is refused before any
  part is asked, a 422 at the POST; a stored document with more answers for the one asked, the parts asked of
  that one alone), `RECONCILE_FETCH` at most 1,000; **both routes need a login** (401, nothing computed; below the
  routes `stored_plan` still gives None for a stand-in of a document the reader may not see); a stored document
  that cannot be planned (a `ValidationError`, a refusal, a reference that is gone) is a 404 with one message and
  a warning logged, and a head that is an entity is read with `get_for_edit`; weights that leave every part at 0
  are refused, a zero vector of the unknown is as no vector, a stored vector of another length counts 0.
- **Reasons** (`reasons.py`, `shared` on each candidate, `RECONCILE_REASONS` 5, 0 turns it off): the entities the
  payload names that some stored document, other than the plan's own, also names together with the candidate, each
  a reference view with `documents` (in how many), those of the most documents first. One query for a request,
  with the reader's cut on the document and on the entity, forward relations that count only. The plan's
  references are resolved by `pangloss_cypher.validate_write.resolved_plan`, moved there from the graph part,
  which now calls it. After a merge the survivor shares for the documents of both. The budget of one POST with
  one unknown is now 14 transactions and 59 statements (13 and 57 with reasons off).
- **The floor** (`test_reconcile_planted.py`, pure, three seeds, 7 s): on a planted world of 1,500 people, name
  and graph vectors made in memory and scored as the service scores: name with graph right first 78.0 / 79.0 /
  81.5%, among five 99.7 / 100 / 100%; name alone 68.3 / 65.6 / 70.2%; on shared names the graph adds 22 to 26
  points. Floors: first above 75%, among five above 98%, the graph more than 15 points on shared names. The
  figures are the service's (78.0%, 99.7%), with nothing tuned.
- **Measured by main on `:7702`** (`planted_reconcile_memgraph_small.txt`): the reasons of ten candidates 4 ms at
  the median (250 ms once in 100); the person, where among the ten, shares 2.9 entities at the mean. **A request
  by stage** (1.3 s): the graph part's `unknown` 466 ms, each of the two exact scans about 250 ms (7,187 people:
  35 µs a vector, five times what 7a.4 measured), `store.read_part` 120 ms twice, the name part's `unknown`
  106 ms (the kept table read and folded at each call, `TODO.md` of phase 8), the class part's 0. What 10.6
  looks at first.
- Tests: Memgraph (`builder`) the package 76, `pangloss-fastrp` 222, `pangloss-cypher` 60. Neo4j (`test-runner`):
  the package's live 23, `pangloss-fastrp` live 70.

### 10.4 as built (2026-11-22)

The interface module `pangloss_reconcile` gives one thing, review's place `reconcileCandidates`
(`ReconcileCandidates.tsx`): under "Reconcile with" and above the picker, "Suggested", at most five rows of
`GET /api/reconcile/candidates/{id}?limit=5`, each the entity's `ReferenceChip`, a slate bar and figure as the
Similar section's (the parts' scores in the bar's name and title), and **Choose**, which makes it the panel's
choice; under a candidate that shares something, "also named with" and those entities as chips, with a count
badge above one document. Nothing at all while the answer comes, at `pending`, or with no candidate to show.
Seen by main in a browser (a screenshot of the e2e test's dialog).

- **A least score, in the module** (`LEAST_SCORE = 0.3`, the builder's, kept by main, **not confirmed**): the route
  always gives the nearest entities, and by the graph alone the other people of the mention's own document are
  "candidates" at 0.08; without a cut nearly every mention would show suggestions. 0.3 is above what the graph
  alone can give at the profile's weights (0.2), so it depends on them: a setting, or a cut at the server, is the
  user's to say (`TODO.md`).
- The e2e project installs `pangloss_names` and `pangloss_reconcile`, with the profile `who` and
  `RECONCILE_PROFILE`; its `default` profile is as it was.
- Tests: the module's Vitest 16 (each seen to fail against its fault), type check clean;
  `e2e/test_reconcile_candidates.py` 2 (the namesake who keeps the third witness's company first, with her as the
  reason; Choose, Reconcile; a mention like nobody shows no "Suggested"), `test_reconcile.py` 12,
  `test_similar.py` 7, `test_module_unit_tests.py` 10, `test_dev_mode.py` 32 (the dialog with a suggestion in the
  development build); the package 76. Rows in `e2e/COVERAGE.md`.

### The end of phase 10's building (2026-11-22): the code review and the whole suite

**`/code-review` (medium) on the phase's diff** (`4e55a6ee..823c82bd`): ten findings, none a write and none a leak.

- **Mended**: (1) on the stored route the reasons ran outside the `try` that answers 404 for a document that
  cannot be planned, so a reference that is gone, met there first, escaped; (2) the name part's `unknown` let
  `store.RebuildDue` through (built, its table not there) and both routes answered 500: it now says nothing of
  the unknowns, logged, and the other parts say theirs; (3) a set built again for each unknown.
- **Left (`TODO.md`)**: the reasons query collects every document of each entity the payload names, without a
  bound (a place named in 100,000 documents; 10.6 measures it at size); the exact scans of a request run one
  after another (20 unknowns by three parts is 60); the plan is resolved two or three times a request; an
  unknown of an abstract class is laid out as the first concrete class below it by name, which is arbitrary where
  the maps weigh by class; a part is searched by if the profile weighs it and scored by `RECONCILE_WEIGHTS`,
  which can disagree; `itemHref` is now written in four modules.

**`./run_tests.sh` whole on `823c82bd`** (`test-runner`, 20.8 min): ruff, `ty`, the skill's check clean;
Memgraph 1,923 passed and 1 failed; without a database 4,126 and 1; `pangloss-neo4j` 174; Neo4j 1,816 and 2;
e2e 356. **The four failures all pass alone**:

- three are this phase's "nothing is written" tests (`test_reconcile_candidates_live.py`, one on Memgraph, two
  on Neo4j): the counts after a request were one node and one `PGPending` mark **fewer** than the baseline. A
  write the test made just before had left a mark, which a worker of the test's server took away after the
  baseline was read. Nothing was written by the routes. The baselines now wait until the counts are the same
  three times running (`settled`). Then the package: Memgraph 76; Neo4j, its live tests with the names', 59,
  twice;
- one is `pangloss-interface`'s `test_nothing_is_rewritten_when_nothing_has_changed`, which found files of
  another test's directory in the JavaScript source (the clash phase 6 met and put on one worker): not this
  phase's, `TODO.md`.

**Not run whole again after these mends** (the two packages touched were run on both backends).

### 10.6 measured (2026-11-22): the service at size, on both backends

`planted.py reconcile` on the dated planted world of 32,000 people asked for (32,137 people and 6,427 mentions;
253,400 vectors in the profile `who`, the table of variants), 200 mentions, each posed again as a payload with a
stand-in and not written (`planted_reconcile_memgraph.txt`, `planted_reconcile_neo4j.txt`):

| | Memgraph (`:7706`) | Neo4j (`:7707`) |
|---|---|---|
| Right first / among five, name alone | 58.0% / 91.5% | 58.0% / 91.5% |
| name 1, graph 0.1 | 69.5% / 94.5% | 70.0% / 94.0% |
| **name 1, graph 0.25** (the profile's) | **65.0% / 96.5%** | **66.5% / 95.0%** |
| name 1, graph 0.5 | 46.5% / 95.5% | 50.0% / 95.5% |
| name 1, graph 1 | 16.0% / 89.0% | 17.0% / 90.5% |
| graph alone | 0.0% / 23.0% | 0.0% / 21.5% |
| Of the 115 whose name several have, at the profile's weights | 52.2% / 95.7% | 53.0% / 93.9% |
| "Someone new", AUC by the best score | 0.62 | 0.62 |
| The person among those found, by either part | 99.5% | 99.5% |
| **A request, at the median (slowest)** | **2.21 s** (3.41 s) | **1.30 s** (2.72 s) |
| the graph part's `unknown` | 505 ms | 528 ms |
| each exact scan (two a request) | 679 ms | 350 to 369 ms |
| `store.read_part` (two a request) | 117 ms | 18 ms |
| the name part's `unknown` | 110 ms | 3 ms |
| The reasons of ten candidates (slowest) | 3 ms (9 ms) | 3 ms (119 ms) |
| The rebuild before it (every part, two profiles) | 565 s | 274 s |

- **The quality is 8.6's at this size** (63.6% right first and 97.2% among five there, by the stored vectors of
  mentions that were people): the service, from a payload with a stand-in and nothing stored, gives 65% and
  96.5%. It falls with size (78% at 7,000 people) because there are more namesakes, not because of the service.
  The two backends differ by a mention or two in 200 (their graph vectors are not the same to the last place).
- **Neo4j is the faster here**, against 2026-11-11 (267 ms against 37 ms for the overlay alone, with Memgraph's
  module): the graph part's `unknown` is the same half second on both (it is the Python reader, 33 statements),
  and Memgraph's exact scan of 38,600 people's vectors costs twice Neo4j's (17 µs a vector against 9), its
  reading of 100 vectors six times, its name part's `unknown` 110 ms against 3 (the kept table, read again).
- **What would make a request quick, in the order of what it costs** (none built, `TODO.md`): one scan for both
  parts (the profile's vector holds both: 0.7 s saved on Memgraph), or the two side by side; the graph part's
  reading of the neighbourhood in fewer statements; the name part's kept table remembered across requests on
  Memgraph as it is on Neo4j (why it is not is not looked into); `read_part` on Memgraph.
- **The reasons cost nothing here** (3 ms): the planted world's places are named by tens of documents, not by
  100,000. The code review's worry about a hub is not measured by this world.
- Written: `implementation_docs/reconcile.md` ("Measured at size"), `guide/vectors/reconcile.md` (new: how to
  install it, the dialog, the two routes, the settings, what it does not do), `status.md`.

### The end of phase 10 (2026-11-22)

**Built**: 10.1, 10.2a, 10.2b, 10.2c, 10.3 (but for the two things below), 10.4, 10.6. **Not built, and the
user's**: 10.5, the toolchain mode (what sets it off; whether a new version of each document it touches is
wanted). **Not built, of 10.3**: a likelihood of "someone new" (AUC 0.62 to 0.67 by the best score: too little),
and several unknowns ranked jointly (nothing measures it). The whole suite was run on `823c82bd` (four failures
that pass alone, three a test's baseline, mended); after the mends and the docs only the packages touched were
run, on both backends. `vectors-10-reconcile` is pushed and not merged. **Paused for the user.**

**For the user** (each in `TODO.md`): the eleven calls of "Read again" (none confirmed); the least score of a
suggestion in the dialog (0.3, in the interface module); what sets the toolchain mode off; "someone new" and
joint ranking left out; a request is 1.3 to 2.2 s; the demo is **not** given `pangloss_reconcile` (its models
have review's `Unreconciled` and the profile `who` already: installing it is one line and `RECONCILE_PROFILE`,
no migration, on the user's word).

## Phase 11: `pangloss-learn`, and reconciliation learning from decisions (provisional)

Written 2026-11-23, on `vectors-11-learn` (from `vectors-10-reconcile`). **Nothing below is built.** The user,
2026-11-23: the eleven calls of phase 10 are confirmed; the exact scan stays (2 s is no problem for now; `TODO.md`);
move on to this phase.

### What was found before the steps (2026-11-23)

**1. What the outline stands on is not there.** The outline and [similarity-plan.md](similarity-plan.md) (stage 10)
say reconciliation's examples "are the reconciliations and the confirmed or rejected toolchain suggestions review
already records". Read in the code (an `Explore` agent, every claim with its file and line), **review records
none of them**:

- A reconciliation is an ordinary update of the document: the tree below the head is deleted and written again
  with a plain reference where the `Unreconciled` was. The stand-in's node is gone (not flagged). What is left is
  the reference, like any reference, and a `PGUpdate` (who, when). Nothing says "this was reconciled", with what
  label, or what else was offered.
- With `pangloss-history` the version before is kept, as JSON in a SQLite file outside the graph, under
  `op="update"`: a reconciliation can be found only by comparing every two versions of every document, and
  history may be left out, may drop records when its queue is full, and has no query across heads.
- A candidate not chosen is recorded nowhere. A toolchain's suggestion has no "reject": it is edited away.
  Confirming one keeps neither the toolchain's name nor the alternatives not taken.
- Only **merges** are kept (`PGMerge`: done, rejected, undone, with both labels). They are pairs of stored
  entities, not of a mention and an entity; not used here (below, "Not in this phase").

**2. And the features of a decision cannot be worked out afterwards.** Once the mention is reconciled the person
chosen is named by that document: their graph vector and "also named with" now hold the answer. So an example is
what was offered **when** it was decided (each candidate's features), and who was taken. It has to be kept then.

**3. What the trial found, read twice** (`notes/similarity-evaluation/learn_trial.py`, with
`learn_trial_PEOPLE_shownN.txt`: the planted world in memory, a logistic regression in numpy fitted on the
decisions of half the mentions, the others of the N offered counted as "no", measured on the other half; three
seeds). The first reading was wrong in two ways the challenger found (below, faults 5 and 6): the count of shared
entities counted a candidate the document itself names as sharing itself, and ten were taken as offered where the
dialog shows five. Corrected:

| Right first | 3,000 people | 12,000 | 24,000 |
|---|---|---|---|
| Hand-set, name 1 and graph 0.25 (what phase 10 built) | 75 to 78% | 70 to 72% | 66% |
| **Hand-set, with 0.3 × log(1 + the shared entities) added** | 83 to 85% | 80 to 83% | 79 to 81% |
| Fitted (name, graph, shared, two products), ten kept for each decision | 87 to 89% | 83 to 85% | 78 to 81% |
| The same fitted on the five the dialog shows | 83 to 86% | 73 to 75% | — |
| Fitted on name and graph alone, on five | 77 to 80% | 52 to 53% | — |

| "Someone new" (the person taken out of half the lists), AUC | 3,000 | 12,000 | 24,000 |
|---|---|---|---|
| The best hand-set score | 0.66 to 0.70 | 0.58 to 0.63 | 0.59 to 0.62 |
| The best hand-set score with shared; its gap to the next; its name's cosine (each alone) | 0.68 to 0.81 | 0.65 to 0.72 | 0.65 to 0.71 |
| A fitted model over the head of the hand-set list (best, gap, the best one's features) | 0.84 to 0.86 | 0.78 to 0.82 | 0.79 to 0.82 |
| The same over the head of a fitted ranking | 0.89 to 0.91 | 0.85 to 0.88 | 0.85 to 0.88 |

- **The gain in ranking needs no learning.** The shared entities, which phase 10 shows as reasons and does not
  score, are worth 10 to 15 points at a weight set by hand (0.3 to 0.4 at every size tried), for every project,
  with no decision made. A fitted ranking adds 2 to 4 points at the smaller sizes and nothing at 24,000.
- **A fitted ranking can be much worse** than the hand-set one: fitted on what the dialog shows (five, chosen by
  the score being replaced), or on few decisions (25: 53 to 66% right first in some runs).
- **"Someone new" is what learning buys**: no single figure tells it (AUC under 0.72 at size); a small fitted model
  does (0.80 over the hand-set list, about 73% of lists called rightly where half are new; 0.86 and about 81% with a
  fitted ranking under it).
- A caution, as in the investigation: these "decisions" are the truth, drawn at random. Real ones are fewer,
  chosen by whoever reviews, and sometimes wrong.

### Read by a challenger (2026-11-23): eighteen faults in the first steps

A `Plan` agent was given the first steps (not kept; in short: 11.2 "a decision is
kept", 11.3 "the features and the score", 11.4 "`LearnedModel`, a document") and the code. What it found, each
checked against the code or the trial, and what is taken from it:

| # | Fault | Taken as |
|---|---|---|
| 1 | With `in_form` review writes nothing to the document: an event there is a decision that may never reach the database, and may come twice | No example from `in_form`; the event only after the write (11.3) |
| 2 | "One record of what was shown for each mention" is not what the decider saw: two people; the `also` mentions reconciled in the background; a known URI (no list drawn); rows under 0.3 never displayed; a pick before the list has come | Kept by stand-in **and user**; only a resolution made directly by that user, soon after, makes an example; any other removes it (11.4) |
| 3 | The order was circular: rows kept before the features were defined; ranking by a model before a model is stored | The order below |
| 4 | `shared` is worked out after the cut to `limit`, for ten at most; as a feature it is needed for every candidate found (about 100), whatever `RECONCILE_REASONS` | 11.2, measured first |
| 5 | The trial's `shared` counted a candidate the document names as sharing itself; the service does not | The trial corrected and run again (above): it changed the conclusion |
| 6 | The trial's "no" were ten by the hand-set score; the dialog shows five, and once a model ranks it chooses its own next examples | Measured (above): five is not enough. The ten best by the **hand-set** score are kept, whoever ranked the list (11.4) |
| 7 | A listener of a write event is synchronous and may not write | The new event is awaited after the write, a failure logged, never failing the reconciliation (11.3) |
| 8 | A model as a document can be edited, deleted or restored by anyone logged in, past the check that it is no worse; it costs every project a migration, a class in its lists, search and RDF, and a rebuild of the vectors | **Call d reversed**: plain nodes of `pangloss-reconcile`, one for each fit, none deleted (11.5) |
| 9 | Two models that are a pair were two documents | One record (11.5) |
| 10 | A model for another list of features, or for vectors of another signature, was used unchecked | An example and a model record the signatures; the fit leaves out what it cannot use and says how many; the service falls back to hand-set and says so (11.4 to 11.6) |
| 11 | A part missing for an unknown: the hand-set mean leaves it out, a fitted model cannot | Such an unknown is ranked by hand-set, with no likelihood; such examples are left out, counted |
| 12 | "Someone new" with a list of one or none; and its meaning: "made after the list was shown" (the steps) is not "not among those offered" (the trial) | It means **none of those offered**; no figure for an empty list |
| 13 | The plain nodes had no index or uniqueness | `structure.py` and a migration (11.4) |
| 14 | 11.2 was too large for one brief | Split: the hook (11.3), the keeping (11.4) |
| 15 | Criteria's `resolve` is the same event only loosely (several places at once, no label) | One event for each place, the label optional; the hook's text says it tells of resolutions made through a package's own route, not of every edit |
| 16 | Nothing to hang the clean-up on | Reconcile's own sweep, in its command |
| 17 | A likelihood on the payload route mixes features that differ a little from the stored route's | On the stored route only, at first |
| 18 | Who decided was kept with no use | Not kept in an example |

### The steps, as they are now

| Step | What | Tests | Who | State |
|---|---|---|---|---|
| **11.1 `pangloss-learn`** | A package with no database and nothing of Pangloss in it (numpy): `fit(examples, features, ridge=1.0) -> Model` (a logistic regression by Newton's steps with a ridge; the same examples in any order give the same model); `Model.score(features)`, a likelihood; a `Model` is plain data, to and from JSON; `compare(examples, features, baseline)`: by the decision, in folds chosen by a seed, how often the one taken is first by a model fitted on the other folds, and by a baseline. `Unfittable` with why | Pure: planted weights found again; any order, the same model; examples a feature divides cleanly; the ridge does not pull the constant; each refusal by its message; `compare` where a model must win, where it must not, ties, decisions with nothing taken | **Main** | **Built** (below) |
| **11.2 The shared entities in the score** | No learning in it. The count of the document's entities a candidate is named with elsewhere, for **every candidate found** before the cut to `limit` (the reasons query for the whole union, counting only; `RECONCILE_REASONS` caps what is shown and no longer turns the count off); `features.py`: a candidate's features in one place (each part's cosine, `shared`); the score gains `RECONCILE_SHARED` × log(1 + shared) (default 0.3; 0 is phase 10's score). Main first: the query's cost for 100 candidates at size on both backends, and for an entity named in very many documents; then the service measured as 10.6 was. The least score of a suggestion becomes a setting, cut at the server (asked of the user in phase 10; the score's scale changes here) | Pure: the features and the score of a hand-made case; the seeded floor of 10.3 moves up. Live: the order changes where it should; the reader's cut on the count; the budget of queries | **Main** (measure), then `builder` | Next |
| **11.3 An event: a stand-in was resolved** | The core, `hooks.resolved`: awaited after the write, each listener's failure logged. Review's `reconcile` emits it for each mention written (not `in_form`), saying whether it was the one the person had open (`direct`) or one of the `also`; criteria's `resolve`, one for each place | Conformance, both backends: once for each resolution; none for `in_form`; a listener that fails does not fail the reconciliation | `builder` | **Waits for the user** |
| **11.4 A decision is kept** | `pangloss-reconcile`: the stored route keeps, by stand-in and user, the ten best by the hand-set score with their features, which were displayed, the signatures of the profile and its parts (`PGReconcileShown`; only for an answer that is `ok`); on `resolved`, direct, by that user, within a set age: one `PGReconcileExample` for the stand-in (replacing an earlier one), with which row was taken or that none was; otherwise the shown record is removed. `structure.py`, a migration, a sweep of what is left over | Live: each path of fault 2 by name; twice gives one; ids only, no label | `builder`; ★ second reading | **Waits for the user** |
| **11.5 Retraining** | `pangloss reconcile learn` (`--dry-run`) and an admin job: the examples of the signatures in use; fit; `compare` with the hand-set score; write a `PGReconcileModel` (both models in one record, none deleted, one in use) only past `RECONCILE_LEARN_FROM` decisions and when no worse; `--use` to go back to an earlier fit, through the same check | Live: none, too few, a fit, a second run with nothing new, a worse one refused | `builder`; ★ second reading | **Waits for the user** |
| **11.6 "None of these"** | With a model in use, on the stored route: `new` on each unknown, the likelihood that the one meant is none of those offered; whether the ranking itself is by the model decided by what 11.5 measures (the trial says: not at size) | Live: with and without a model; a model of other signatures is not used and the answer says so | Main, then `builder` | **Waits for the user** |
| **11.7 Measured, written** | Through the service on the planted world, both backends; `implementation_docs/learn.md`, `reconcile.md`, the guide, the skill, `packages.md`, `status.md`; `/code-review`; `./run_tests.sh` whole | The floors | Main, then `builder` | After each half |

**Why 11.3 to 11.6 wait.** They are a new record of what people decide, a route that reads becoming one that
writes, and a new event in the core, and what the trial says they buy is one figure: "none of these", right for
about three lists in four. The ranking, which was the reason for the phase, is had in 11.2 without them. Whether
that is worth building is the user's.

**Calls taken (none confirmed by the user):**

| | Call | Instead of |
|---|---|---|
| a | The shared entities are scored at a weight set by hand, 0.3, for every project | Learnt, or shown only |
| b | A decision, if kept at all, is kept by `pangloss-reconcile` as plain nodes, from what it offered, when a new event of the core says a stand-in was resolved | Reading history (not always there, no query across documents, and the features cannot be made again) |
| c | A decision with no list offered to that person just before is no example | — |
| d | A fitted model is a plain node of `pangloss-reconcile`, one for each fit | A document with history (the outline; fault 8) |
| e | A model is used only past 100 decisions and when no worse than hand-set on decisions held out | Always, once fitted |
| f | Merges are not examples | — |

**Not in this phase**: learning from merges (pairs of stored entities: "are these two people one", which nothing
asks yet); from toolchain suggestions (10.5 is not built, and they have no "reject"); comparison (phase 12 uses
`fit` and `compare` as they are).

### 11.1 as built (2026-11-23)

`packages/pangloss-learn` (not an app: nothing to install, no settings, no models): `pangloss_learn.maths`, and
from the package's root `fit`, `Model`, `Example`, `compare`, `Compared`, `Unfittable`. 25 pure tests
(`tests/test_learn_maths.py`), `ruff` and `ty` clean.

- An `Example` is `features` (numbers by name), `yes`, and `group` (the decision it was offered in).
- `fit` puts the rows in one order before fitting, so the model is the same to the last bit whatever order they
  came in. The ridge pulls every weight but the constant. Features are not rescaled (they are cosines and the
  logarithm of a small count).
- `Model.score` refuses (a `KeyError` saying which) features that lack one the model weighs: a missing part is
  the caller's to handle (fault 11).
- `compare` counts only decisions in which something offered was taken; of several scored alike the first given
  is the first, for the model and the baseline alike. `Compared.no_worse`.
- The maths knows no clock: `fitted_at` is what the caller says.

### 11.2 measured (2026-11-23): the shared entities through the service, at size, on both backends

`planted.py reconcile` (the dated planted world, 32,137 people, 200 mentions; `:7706` and `:7707`, stopped
again; `planted_reconcile_shared_{memgraph,neo4j}.txt`). `shared` is n / (n + 2), n being how many of the
document's entities the candidate is named with in other documents: bounded, so the score stays a weighted mean
from 0 to 1 (in the trial n / (n + 2) at weight 1 did as well as 0.3 × log(1 + n)).

| Weight of `shared` beside name 1, graph 0.25 | Right first (Memgraph / Neo4j) | Among five | Of the names several people have, first |
|---|---|---|---|
| 0 (phase 10) | 65.5% / 67.5% | 95.5% / 96.0% | 50.4% / 54.8% |
| 0.25 | 75.0% / 73.5% | 99.5% | 62.6% / 61.7% |
| 0.5 | 79.5% / 79.5% | 99.5% | 71.3% / 68.7% |
| **0.75** | **80.5% / 80.5%** | 99.5% / 99.0% | 73.9% / 73.0% |
| 1 | 78.5% / 79.0% | 99.5% / 99.0% | 72.2% / 71.3% |
| 2 | 72.0% / 73.5% | 99.5% / 99.0% | 70.4% |

- **The trial's finding holds through the service**: 15 points right first, and the right person nearly always
  among five, with no decision learnt from. The default is 0.75.
- **The count costs nothing that shows**: the reasons query asked for every candidate found (95 at the median)
  takes 10 ms at the median on Memgraph (slowest 20 ms), 8 ms on Neo4j (slowest 166 ms), in a request of 2.2 s
  and 1.1 s. Not measured: a document that names an entity named in very many documents (the planted world has
  none; the code review of phase 10 said the same of the reasons).
- **A fault of the measure, found on the way**: the first run gave 66.5% → 69.5% only. In this measure the
  mention's factoid is stored *and* posed again as a payload, so the people it names shared one another through
  the stored copy. The stored route leaves its own document out; the measure now does too (it looks the stored
  factoid up and gives the plan its id).
- "Someone new" by the best score is no better for it (AUC 0.62 → 0.66).

### 11.2 as built (2026-11-23), and the form that was measured second

Built by `builder` from `briefs/11.2.md`, then changed from `briefs/11.2b.md` (its choices:
`briefs/11.2-report.md`). `pangloss-reconcile`: 110 tests on Memgraph (pure and live); its live tests and
`pangloss-vectors`' on Neo4j, 190; the module's vitest and type check and `e2e/test_reconcile_candidates.py`, 3.
Not run: the whole suite, the development-build test.

**The first form was changed.** As briefed, `shared` was n / (n + 2) at 0.75, one more term of the mean. The
builder saw what that does: people the document itself names (found by the graph, sharing the document's other
entities) came into the answer at about 0.26 with a name's cosine of 0. What is shared counted the same whoever
the candidate was. Measured again (in memory, then through the service on `:7706`,
`planted_reconcile_byname_memgraph.txt`; Neo4j not run again), the term **multiplied by the cosine of the part
the weights weigh most** (the name, in `who`):

| At size, Memgraph, 200 mentions | Right first | Among five | Of the names several people have, first |
|---|---|---|---|
| name 1, graph 0.25 (phase 10) | 66.5% | 95.5% | 53.9% |
| + n / (n + 2) at 0.75 (the first form) | 82.0% | 99.5% | 76.5% |
| + lead × n / (n + 2) at 1 | 85.5% | 99.5% | 79.1% |
| **the same at 1.5 (the default)** | **86.5%** | 99.5% | 82.6% |
| at 2 / 3 / 4 | 86.5% / 86.0% / 85.0% | 99.5% | 82.6% / 81.7% / 80.9% |

In memory at 24,000 people: 85.5 to 86.8% at weights 1.5 to 3 (three seeds). A third form, the score raised
towards 1 by what is shared so that a candidate sharing nothing keeps phase 10's score, gave 79 to 81%: not taken.

- **The count**: `candidates_of` asks `reasons.shared` once a request, for every item found of every unknown,
  uncut, before the cut to `limit`; a `Candidate` carries what it shares, and `api.answer` shows the first
  `RECONCILE_REASONS` without asking again. The budget of queries did not rise (14 transactions, 59 statements).
  Not asked only when the weight of `shared` is 0 and `RECONCILE_REASONS` is 0.
- **The score** (`score.py`, still no database in it): `scores["shared"]` is `lead × n / (n + 2)`, `lead` the
  candidate's cosine of the scored part with the highest weight (of several alike the first by name; never under
  0; no part scored, 0). It is in every candidate's scores while its weight is above 0. `reconcile` still names no
  part's package: the rule is about weights.
- **Settings**: `RECONCILE_WEIGHTS` may name `shared` (1.5 unless given; 0 is phase 10's score exactly);
  `RECONCILE_LEAST_SCORE` (0.15: with the defaults, a candidate that shares nothing and whose name's cosine is
  0.41), cut in `candidates_of` after ranking, on both routes. The interface module's own cut is gone.
- **The scale of the score moved**: a namesake who shares nothing scored up to 1 and now up to 0.41 (the mean is
  over name 1, graph 0.25 and shared 1.5); the bar in the dialog is shorter for the same candidate than it was.
- **The seeded floor** (1,500 people, three seeds): right first 89.2 / 90.7 / 90.1% (by name and graph 78.0 /
  79.0 / 81.5%), among five 100%; floors 0.88 and 0.99.
- **Left**: in the live tests' small world a person of another name has a name's cosine of 0.24 with the mention
  (few names, so the rarity table is coarse) and still comes in at 0.2: a matter of that world, not seen at size.
  A document that names an entity named in very many documents is still unmeasured.

## Phases 11 to 13, in outline

Each is a package of [similarity-plan.md](similarity-plan.md) (its stages 10 to 13), and each gets its steps
written on this page's pattern when it is reached.

| Phase | What | Tests in a line | Needs |
|---|---|---|---|
| 11. `pangloss-learn`, and reconciliation learning (**steps above**) | `fit`, `Model`, a document of weights; retraining from review's decisions | Pure: planted weights are recovered; retraining is reproducible. Live: no decisions still works | 10 |
| 12. `pangloss-compare` | `CompareMeta`, pairs, verdicts at lookup, `EventJudgement`, the side-by-side page, learning from judgements | Pure: the trial's cases (general and specific class, once per, recurring, negated). Live and e2e: a judgement overrides; nothing is written by a lookup | 11; 2 and 9 optional |
| 13. Neo4j tuning | A cheaper overlay; every phase measured on both backends at 300,000 and 640,000 nodes (8.1's generator gives both the same data) | The same equality tests; figures in `backend-comparison.md` | 3 |

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

## Who builds the next phases

The same agents, used a little differently. What phases 1 to 7 showed:

- **A brief is one step, not a phase.** Phases 5, 6 and 7 each went to `builder` as one brief. Phase 5's was
  stopped by a usage limit, its report never came, and its choices were read out of the code afterwards. A step is
  small enough to give out again.
- **A brief and a report are files.** Main writes each brief to `notes/similarity-evaluation/briefs/STEP.md` before
  it is given out, and the brief asks `builder` to write its choices to `briefs/STEP-report.md` as it makes them,
  not only at the end. A stopped agent then leaves both, and the next session gives the step out again from the
  file.
- **The maths and the measurements stay with main.** Every fault that mattered was found by measuring
  (`store.read_part`'s plan, the burst, the short search), and a measurement needs the scratch databases and a
  judgement of what the figure means. `builder` is given what main found, never asked to find it.
- **A second reading that is not main's.** Main wrote the brief, so main reads the diff expecting what it asked
  for. For the steps where a wrong result looks right (marked ★ below), a fresh `general-purpose` agent is given
  the step's text and the diff, **not** the brief's reasoning nor the builder's report, and asked one question:
  where does this give a wrong vector, write something, or show a reader what they may not see. For interface
  diffs main runs the `solidjs-v2-reviewer` skill. Before each phase's whole run, `/code-review` on the phase's
  diff.
- **`Plan` once, as a challenger.** When phase 10's steps are read again, a `Plan` agent is given them and the
  code of phases 2, 7a and 8 and asked what in them cannot work. Not before: it would plan without 8's figures.
- **`test-runner` beside `builder`, on the other database.** Two runs on `:7687` empty each other; the Neo4j run
  (`:7693`) is safe beside a Memgraph one. So while `builder` works on a step (its own tests on Memgraph),
  `test-runner` runs the step before on Neo4j. The whole suite runs at a phase's end, in the background, with no
  `builder` at work.

| Step | Mostly | Main keeps | To `builder` | Second reading | Runs (`test-runner`) |
|---|---|---|---|---|---|
| 7a.1 Burst in groups | Main, then `builder` | The trial: one reader for all the halves, or a remembered size; the reasoning of exactness; the measurement | The split in `refresh_ids`, the pure and live tests, from what the trial found | ★ `general-purpose`: can a changed join fall between two groups | `pangloss-fastrp` on both; the exactness test three times with other seeds |
| 7a.2 URI | `builder` | The route's matching, tried by hand | All of it | — | `pangloss-vectors` on both; `packages/pangloss-api` |
| 7a.3 Exclusion | `Explore`, main, then `builder` | Who reads `include` today (`Explore`); the order of the rules; "no vector, still joined" | `meta.included`, the settings and their checks, the signature, the tests, the docs | ★ `general-purpose`: a class newly excluded, does anything keep or show its vectors | `pangloss-vectors`, `pangloss-fastrp`, `pangloss-review` on both; `e2e/test_similar.py` |
| 7a.4 A field's types | Main, then `builder` | The recall measurement and what a rare type gets; `search_query` with the filter, planned on both | The parameters, the field's types, the two searches, the tests | — | `pangloss-vectors` on both |
| 7a.5 Types used as the real class | `Explore`, main, then `builder` | How "referred to" is asked today (`Explore`, `Usage`); the query on both and its cost at size; which relations count | The groups by use, the filter, the worker's part, the tests | ★ `general-purpose`: after any write, delete or merge, can a type be in the group with nothing naming it, or out with something | `pangloss-vectors`, `pangloss-typology` on both; `e2e/test_similar.py` |
| 8.1 Planted world | Main | All of it | The pure test of the generator | — | `packages/pangloss-testing` |
| 8.2 Names maths | **Main** | All of it; the dimension; where rarity is kept | The pure tests from the list, after `maths.py` exists (a second pair of eyes on the rules, as 3.2) | — | The package; the planted regression with three seeds |
| 8.3 Package, part | `Explore`, main, then `builder` | Where `fold` is (`Explore`); the query of the names; where the table is stored | The scaffold, `NamesMeta`, `part.py`, its tests | ★ `general-purpose`: a refresh against an old table, is it what a rebuild with that table gives | The package on both; the skill's check |
| 8.4 The part's suite | `builder` | Reading that the graph part's tests assert what they did before | All of it | — | `pangloss-fastrp`, `pangloss-vectors` on both, counts compared with before |
| 8.5 Variants | `builder` | — | All of it | — | The package |
| 8.6 By a name, at size | `builder`, then main | The measurement on both backends | The function, the command, the live test | — | The package on both; the CLI guide test |
| 8.7 Demo, docs | `builder` | The migration read; `:7688` untouched; the docs read against the code | All of it | — | `./run_tests.sh`, whole |
| 9.1, 9.3 Package, part | Main, then `builder` | The query of the dates, planned; whose vector a nested date is | The scaffold, `part.py`, 8.4's suite called | — | The package on both |
| 9.2 Time maths | **Main** | All of it; the dimension | The pure tests from the list | — | The package |
| 9.4 Entities | Main | All of it; the decision goes to the user if it costs locality | — | — | — |
| 9.5 Docs, demo | `builder` | As 8.7 | All of it | — | `./run_tests.sh`, whole |
| 10.1 Review's hook | `builder` | That review gains a hook and no knowledge of who fills it | All of it | — | `pangloss-review` on both |
| 10.2 The service | Main, then `builder` | The order of validate, plan, overlay; the two defining tests written first, failing | The route and the rest of its tests | ★ `general-purpose`: is anything written, on any path, error paths too | The package on both; conformance cost tests |
| 10.3 Second stage | **Main** | The score, the weights, "someone new", the measurement | The reasons, the joint ranking's plumbing, the pure tests | — | The package |
| 10.4 Interface | `builder` | The look, in a browser on the scratch stack; the styling rules | The dialog's part, the field's suggestions, unit tests, e2e, translations, `COVERAGE.md` | `solidjs-v2-reviewer` (main) | The modules' unit tests; e2e; the dev-mode test |
| 10.5 Toolchain mode | `builder` | — | All of it | ★ `general-purpose`: can it ever merge or write twice | The package and `pangloss-review` on both |
| 10.6 Measured, written | Main, then `builder` | The figures | The docs | — | `./run_tests.sh`, whole |

**What runs side by side.** 7a.1 (`pangloss-fastrp`) beside 7a.2, then beside 7a.3; main's trials for 7a.4
meanwhile. 8.1 and 8.2 are main's and need nothing of 7a, so they can be written while 7a's steps are with
`builder`. 9.2 (main) beside 8.5 to 8.7 (`builder`). 10.1 beside anything, it is review's. As before: never two
`builder`s in one package, never two runs on one database.

## Testing the next phases

The three kinds of test and the oracle are as they were ("How the work is run"). What is added:

1. **A step is done on four things**, in this order: its pure tests; its live tests on Memgraph (by `builder`);
   the same on Neo4j (by `test-runner`); main's reading of the diff against those runs. Then the commit.
2. **A phase is done on four more**: `/code-review` on its diff; `./run_tests.sh` whole (`test-runner`, in the
   background, under `caffeinate -is`, nothing else on `:7687`); a failure run again alone before it is called a
   fault of the work; the counts written into "Where the work stands" with the commit they were run on.
3. **Every part passes one suite** (8.4, `pangloss_testing/parts/`): stored vectors equal the slow way's after
   every kind of write; nothing gone keeps a vector; an overlay equals the payload written; a rebuild under writes
   loses none. A new part that has not called it is not finished.
4. **Quality has floors.** Each figure measured on the planted world (8.1) becomes a seeded pure test with a floor
   a little under it (`test_names_planted.py`, `test_time_planted.py`, phase 10's score). They run without a
   database, in seconds, in every run. Until now a change could halve the quality and fail nothing.
5. **"Nothing is written" is counted, not read.** Phase 10's service, and phase 12's lookups, are tested by the
   count of nodes, edges and `PGPending` marks before and after, on both backends, on the error paths too.
6. **What a reader may see is tested where a result is made.** Each new way to get results (several types, a
   field, a name, candidates) has one live test with an unpublished item and a reader who is not logged in, and
   one with a merged entity.
7. **A cost is budgeted where the core is touched.** A new hook or mark (7a.3's rule in `pending_work_of`, 10.1)
   keeps `test_query_costs.py`'s budgets on both backends; if a budget has to move, the step says why.
8. **Measured at size, on both backends, on the same data.** 8.1's generator loads the same world into Memgraph
   and Neo4j. Scripts and their output are kept in `notes/similarity-evaluation/`, never only in `/tmp`; scratch
   containers on their own ports (`:7690`, `:7702`, `:7703` are in use), stopped when not measuring, and listed
   in "Where the work stands".
9. **The interface** (10.4 only): unit tests in the module; e2e with rows in `e2e/COVERAGE.md`; the dev build
   (`e2e/test_dev_mode.py`) loaded on the changed pages, which stops on what the production build lets through.
10. **A new package** is added in the step that makes it to: the Neo4j list of `run_tests.sh` (line 110 and the
    header), `packages.md`, the skill and its check, and, if it has an interface module,
    `e2e/test_module_unit_tests.py`.
11. **Mutation testing, if it is in by then.** `mutmut` is decided as a development dependency and not yet added
    (`TODO.md`). When it is, the two new `maths.py` files are run under it once, after their pure tests are
    written: they are small, pure and exactly what it is good at.

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

- **RESUME HERE (2026-11-23)**: phase 11 on `vectors-11-learn` (from `vectors-10-reconcile`), pushed, not merged.
  The user confirmed phase 10's eleven calls and left the exact scan as it is. Phase 11's steps were written, read
  by a challenger and written again ("Phase 11"). **Built: 11.1** (`pangloss-learn`, 25 pure tests) and **11.2**
  (the shared entities in the hand-set score: right first 66.5% → 86.5% at size; `pangloss-reconcile` 110 on
  Memgraph, 190 live on Neo4j with `pangloss-vectors`). **11.3 to 11.6 WAIT FOR THE USER** (an event when a
  stand-in is resolved, decisions kept, retraining, "none of these"): the trial says a fitted ranking buys
  nothing at size, and "none of these" (right about three lists in four) is what is left to buy. **Not done for
  this half**: `/code-review`, `./run_tests.sh` whole. The large scratch containers (`:7706`, `:7707`) are stopped.
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
- **Phase 7 built** on `vectors-7-demo` (from `vectors-6-interface`; its "As built"). **`./run_tests.sh`
  whole on the tree of its commit, 2026-11-21: every stage passed** (Memgraph 1744, without a database 3789,
  `pangloss-neo4j` 173, Neo4j 1638, e2e 352), with none of phase 6's intermittent faults.
- **The base is built: phases 0 to 3 and 5 to 7** (4 deferred). **Paused here for the user**: the demo's database
  (`:7688`) is to be migrated and rebuilt on their word (`pangloss migrate`, `pangloss vectors rebuild`, from
  `pangloss-demo/`); the stacked branches (`graph-embeddings-update` → `vectors-1-hooks` → … → `vectors-7-demo`) are
  merged into `dev` (below); phases 8 to 13 are in outline only, and each gets its steps written when it is reached
  (the order is the user's: names, the time part, reconciliation, learning, comparison, Neo4j at size).
- **Half done**: nothing.
- **For the user, not blocking**: the default steps and whether vocabularies are in (3.5's figures); `pangloss check` saying a rebuild is due needs a hook (`TODO.md`).
  From phases 5 and 6 (`TODO.md`): a burst of writes leaves approximate vectors (refresh a batch past the cap in
  smaller groups?); which classes of packages have vectors (unreconciled mentions, typology entries); the three calls main took in phase 6's brief.
- **The user's answers of 2026-11-21, after phase 7** (each in `TODO.md`, none built):
  - a burst of writes: **build it as proposed** (the graph part refreshes a batch that is past the cap in smaller
    groups before it approximates);
  - the similar route **takes a URI as well as a UUID**;
  - a way to say "no vectors for this" **without `pangloss-vectors` installed: both ways proposed are accepted**:
    a project's setting `VECTORS_EXCLUDE` (classes by name, with their subclasses), and a general mark in the
    models that names no package, for a package's placeholders (review's `Unreconciled`), which `pangloss-vectors`
    reads as no vectors unless the project says otherwise. Not a package importing `pangloss_vectors` if it is
    there. The name of the mark is to be chosen when it is built;
  - a new idea: **the similar of several types at once, by a field of a model** (a field that takes persons or
    groups suggests both); to be designed when built, and of use to phase 10;
  - **merged into `dev`** (a fast-forward from `a36df591`) and pushed.
- **Where a new session starts** (2026-11-21): on the branch `similarity-next-phases` (from `dev`, which has all
  of phases 0 to 7), made for **planning the next phases, not building**. To plan there:
  1. the four things the user decided above, as steps with their tests (a burst refreshed in groups; a URI at the
     similar route; `VECTORS_EXCLUDE` and the placeholder mark; the similar of a field's types, which needs its
     search designed and its recall measured);
  2. phases 8 to 13, which are in outline only: their order with the user, then the steps of the first on this
     page's pattern (what changes and where, tests by file, what is measured, who builds it);
  3. what is still the user's to decide: the default FastRP steps and whether vocabularies are in the graph
     (3.5's figures), the demo's `VECTORS_GRAPH_SEES`, a hook for `pangloss check`, and the three calls main took
     in phase 6's brief, which nobody has confirmed.
  The demo's database (`:7688`) is still to be migrated and rebuilt, on the user's word.
- **The user, 2026-11-21**: go on through the next phases without pausing at each; branches stay stacked
  (`vectors-3-…` from `vectors-2-package`), nothing merged.
- **The next phases are planned (2026-11-21, on `similarity-next-phases`; nothing of them built)**: "The next
  phases" (the order, and six decisions each with a default taken), phases 7a, 8, 9 in steps, 10 in provisional
  steps, 11 to 13 in outline, "Who builds the next phases" and "Testing the next phases". **A session told to
  continue starts at 7a**, on a branch `vectors-7a-leftovers` from `dev`: 7a.1's trial (main) first, with 7a.2 given
  to `builder` beside it. **The user confirmed the order and every default of the table (2026-11-21)**; the two that change most are said again here: **the placeholder mark is `hooks.stand_ins`, no
  new name** (7a.3), and **the time part is a package of its own, `pangloss-dates-vectors`** (9.1).
- **The user, 2026-11-21, after the plan**: the types of a typology have vectors, and are suggested as the real
  class (`also=Role`) only when the data uses them as it ("Banker", a `RoleType`, named where a `Role` goes; not
  the label, not `HAS_TYPE`); not narrowed, a search lists them as types. Step 7a.5; typology types are no longer
  an example for `VECTORS_EXCLUDE`.
- **Phase 7a in hand (2026-11-21)** on `vectors-7a-leftovers` (from `similarity-next-phases`, as the user said;
  briefs and builders' reports in `notes/similarity-evaluation/briefs/`):
  - **7a.2 done** (its "As built"), committed.
  - **7a.1 done** (its "As built": second reading, one fault mended, measured; `TODO.md` item closed).
  - **7a.3 done** (its "As built", with the second reading: one question for the user, in `TODO.md` once 7a.4's
    builder has given the file back).
  - **7a.4 done** (its "As built": an exact scan, not the filtered index).
  - **7a.5 done** (its "As built", with the second reading's two mends).
  - **Phase 7a is finished** ("The end of phase 7a": the whole suite, the code review, what is the user's).
    `vectors-7a-leftovers` is pushed and not merged.
  - **7a.6 planned, not built** (the user, 2026-11-21, on 7a.1's figures: estimates at once, exact after; "maybe").
    To be confirmed and built, on a branch of its own from `vectors-8-names` or before 8.3, whichever the user says.
  - **Phase 8 begun** on `vectors-8-names` (from `vectors-7a-leftovers`): 8.1's generator
    `pangloss_testing/planted.py` and `tests/test_planted.py` (5 pure tests) are written and committed there. Not done of 8.1: the
    command that writes the JSON Lines and the truth (`notes/similarity-evaluation/planted.py`), loading at size
    on both backends (`Group` and `Place` of `similar_models` need `create_with_id` for a bulk load), the base
    measured.
  - **8.2 done** (its "As built": rarity by the word, dimension 256), committed. **8.1 done** (its "As built": the base on both
    backends; the graph alone never puts the right person first). The query of the names is tried on both
    (`names_query_trial.py`), and the briefs of 8.3 and of 8.5 with 8.6 are written (`briefs/`), not given out. **8.4 done** (its "As built"; the suite every part passes,
    built before 8.3, which calls it). **8.3 done** (its "As built": the part, a hook
    in `pangloss-vectors` for what a part keeps with a generation, migration 0003; two faults of the second reading
    mended). **8.5 and 8.6 done** (their "As built"), 8.6's
    measurement at size running when this was written (`planted.py names`). **8.7 done** ("8.6 measured", "8.7 as built"). **PHASE 8 IS FINISHED** ("The end of phase 8": the whole
    suite, the code review and its four mends). `vectors-8-names` is pushed and not merged. **Paused for the user.**
  - **Phase 9 in hand (2026-11-22)** on `vectors-9-time` (from `vectors-8-names`). **9.2 done** (its "As
    built": the maths, a ring of years and no range; the planted world with dates; measured on the small scratch
    database). Next: 9.1 with 9.3 to `builder` from `notes/similarity-evaluation/briefs/9.1-9.3.md` (the package,
    the part, the suite called with dated models), **done** ("9.1 and 9.3 as built"; green on both backends); **9.4
    decided** (no time vector for an entity from the documents that name it). **Measured at size on both backends** ("9.3
    measured"). **9.5 done** ("9.5 as built"). **PHASE 9 IS FINISHED** ("The end of
    phase 9": the whole suite, the code review and its three mends; one intermittent e2e fault that is also on
    `vectors-8-names`, not understood). `vectors-9-time` is pushed and not merged. **The user answered (2026-11-22, "The user's answers after phase
    9")**: a new session, on `vectors-10-reconcile` (from `vectors-9-time`, checked out, empty), **first finds and
    fixes the intermittent `e2e/test_similar.py` failure, then mends the merge of an entity with an embedded
    object** (both in `TODO.md`), runs the whole suite, and only then starts **phase 10** (`pangloss-reconcile`,
    provisional: its steps read again first, a `Plan` agent given them and the code of phases 2, 7a, 8 and 9 and
    asked what in them cannot work, "Who builds the next phases"). The width stays 2; the demo's dated classes
    all keep their time vectors; **the demo's database is migrated and rebuilt**.
  - **The two faults mended (2026-11-22, on `vectors-10-reconcile`; "The two faults, mended")**: the e2e fault
    was three (Memgraph's vector index does not find items whose vectors repeat, so a profile of at most
    `VECTORS_EXACT_UP_TO` vectors, 20,000, is now read whole and scored exactly: a new setting, my call; two
    hearings alike by chance; a wait in a fixture that did not wait), and the merge writes what the survivor
    takes of the absorbed entity's nodes as new nodes. `e2e/test_similar.py` by itself: 24 runs of 24 passed
    (before: 2 to 5 in 20 failed). The four similarity packages: Memgraph 741 passed, their live tests and the
    merge tests on Neo4j 657. **`./run_tests.sh` whole on `201d03c6`, every stage green**: ruff, `ty`, the
    skill's check; Memgraph 1,883; without a database 4,061; `pangloss-neo4j` 174; Neo4j 1,777; e2e 353; no
    xfail left. **Paused for the user before phase 10**, as asked. **Open for the user before
    phase 10** (`TODO.md`): the setting and its default; what a large project does above it (the index misses
    items whose vectors repeat, which people who share a name do); whether to report it to Memgraph; Neo4j's
    index not tried. **Phase 10 starts by reading its steps again with that in hand.**
    **The user answered (2026-11-22)**: the setting and its default are confirmed; that the index misses
    repeated vectors above it is accepted, and phase 10 plans its candidates with it; the user reports it to
    Memgraph later; Neo4j's index untried is accepted. Nothing is waiting: **next is phase 10**.
  - **Phase 10 in hand (2026-11-22)** on `vectors-10-reconcile`. Its provisional steps were read again with a
    `Plan` agent as challenger: eleven things in them could not work, and main took a call on each (phase 10,
    "Read again (2026-11-22)", rows a to k; **none confirmed by the user**, all in `TODO.md`). The steps as now
    built are in the table there: 10.1 (a place in review's dialog), 10.2a (the core: `StandIn.named_type`,
    `checked_create`), 10.2b (the parts' `unknown`, `nearest(exact=True)`), 10.2c (the package and the service),
    10.3 (the second stage, main's), 10.4 (the interface), 10.5 **not built** (the user's: what sets it off),
    10.6 (measured, written). **10.1 done** (its "As built"), committed; **10.2a done** (its "As built"); **10.2b done** (its "As built", with the second reading and one mend); **10.2c done** (its "As built"; green on both backends; second reading: nothing written, nothing leaked). **10.3 measured** (79% right first, 99% among five). **10.3 done** ("10.3 as built": the mends, the reasons `shared`, the seeded floor; green on both backends). **10.4 done** ("10.4 as built"; seen in a browser). **The code review and the whole suite are done** ("The end of phase 10's building": three mends, four failures that pass alone, three of them a test's baseline, mended). **10.6 done** ("10.6 measured": at size on both backends, 65% right first and 96.5% among five, a request 2.2 s on Memgraph and 1.3 s on Neo4j; the docs and the guide). **PHASE 10 IS FINISHED but for 10.5** (the toolchain mode, the user's: "The end of phase 10"). `vectors-10-reconcile` is pushed and not merged. **Paused for the user.** Next is phase 11 (`pangloss-learn`), which is in outline only: its steps are to be written first. Before: (`briefs/10.1.md`, `briefs/10.2a.md`; a
    session that finds no report beside a brief gives the step out again). Next for main: the brief of 10.2b.
- **Since 10.6 (2026-11-22)** the two planted databases at size and `:7702` are rebuilt with the stand-in `Mention` declared (`planted.py rebuild --stand-in`) and have the profile `who`; `:7706` and `:7707` are stopped again.
- **Left running or stopped**: `pangloss-memgraph-planted` (`:7706`) and `pangloss-neo4j-planted` (`:7707`),
  since 9.2 the **dated** planted world at size (seed 1, 32,000 people; `planted.py write DIR --dated`), with the
  vectors of four parts and the profiles `default` and `when` (and some 40 factoids and 4 people more, of the
  measurements), stopped (`docker start` them to measure); `pangloss-memgraph-similar` (`:7702`, since 9.2 the dated planted world of 6,000 people with graph, class and name vectors) and `pangloss-neo4j-similar` (`:7703`), small,
  running; `pangloss-memgraph-identity` (`:7690`; since 2026-11-21 with some 900 factoids more, of `measure_worker.py`, and
  about 1,500 stale graph vectors; since 7a with some 600 factoids more and a hand-made index `:PGProfileVector(type)`) and `pangloss-compare-api-neo4j-core` (`:7698`) stopped.
