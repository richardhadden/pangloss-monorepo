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

- **Finished**: phase 0; of phase 1 (branch `vectors-1-hooks`, from `graph-embeddings-update`), steps 1.1 and 1.2
  (2026-11-20), and the trials by hand of 1.3 to 1.5 (`notes/similarity-evaluation/README.md`, "What phase 1's
  trials found").
- **Next**: 1.3, 1.4 and 1.5, by one `builder`, from the trials' findings (the brief is in "As built" of phase 1
  once written; if a session stopped with the work half done, read `git status` and give it out again).
- **Half done**: nothing committed is half done.
- **Waiting for the user**: nothing. (After phase 1: the go-ahead for phase 2.)
- **Left running or stopped**: `pangloss-memgraph-similar` (`:7702`) and `pangloss-neo4j-similar` (`:7703`), small,
  running; `pangloss-memgraph-identity` (`:7690`) and `pangloss-compare-api-neo4j-core` (`:7698`) stopped.
