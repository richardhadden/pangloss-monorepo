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

**8.7 The demo and the docs.** `builder`. `implementation_docs/names.md` (✅ with what is built), `vectors.md`
(the parts), `status.md`, `guide/vectors/` (a page on names), the demo (a profile `who` of name and graph on
`Person`, a small table of variants; a migration that is one more index; **`:7688` untouched**).

**Phase 8 is done when** a search by a name returns variants and namesakes ranked, on both backends, and the
figures of 8.6 are written.

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

## Phases 11 to 13, in outline

Each is a package of [similarity-plan.md](similarity-plan.md) (its stages 10 to 13), and each gets its steps
written on this page's pattern when it is reached.

| Phase | What | Tests in a line | Needs |
|---|---|---|---|
| 11. `pangloss-learn`, and reconciliation learning | `fit`, `Model`, a document of weights; retraining from review's decisions | Pure: planted weights are recovered; retraining is reproducible. Live: no decisions still works | 10 |
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
- **Left running or stopped**: `pangloss-memgraph-similar` (`:7702`) and `pangloss-neo4j-similar` (`:7703`), small,
  running; `pangloss-memgraph-identity` (`:7690`; since 2026-11-21 with some 900 factoids more, of `measure_worker.py`, and
  about 1,500 stale graph vectors; since 7a with some 600 factoids more and a hand-made index `:PGProfileVector(type)`) and `pangloss-compare-api-neo4j-core` (`:7698`) stopped.
