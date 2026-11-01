# Database abstraction: implementation plan

**Status: plan (2026-10-31). Nothing here is built.** It turns [database-abstraction.md](database-abstraction.md)
into ordered work, includes the fixes from [code-review-2026-10-31.md](code-review-2026-10-31.md), and adds what a
survey of the other packages' Cypher found ([§2](#2-cypher-outside-the-backends)).

## 1. Decisions

| # | Question | Answer | Effect on the plan |
|---|---|---|---|
| 1 | Is a non-Cypher (RDF) backend a goal? | Not now; it will be considered later | The typed `Storage` port is **deferred** ([§5](#5-deferred-the-storage-port)). The phases keep the seams it needs: a neutral write plan, a neutral read shape, no driver exceptions escaping the kit, and a conformance suite that goes through the models, not Cypher. |
| 2 | Package name | `pangloss-cypher` | |
| 3 | Replace `DATABASE_MODULE` with a `STORAGE` factory, and keep an alias for how long? | Yes, now (answered again 2026-10-31, when the plan was approved) | Done in phase 1: `STORAGE = "pangloss_memgraph:storage"` names a typed `pangloss_core.storage.Storage` (name, capabilities, parts). `DATABASE_MODULE` is still read, with a `DeprecationWarning`. The full port of [§5](#5-deferred-the-storage-port) is still deferred: the parts it names are the modules of today. |
| 4 | Fold accents on both backends? | Yes | Phase 5: Memgraph gets a folded label, and `zurich` finds "Zürich" on both backends. |

## 2. Cypher outside the backends

I searched every package except the two backends for Cypher:

| Package | Cypher | Kind |
|---|---|---|
| `pangloss-api`, `-cli`, `-dates`, `-history`, `-interface`, `-review`, `-sdk`, `-sdk-server`, `-users`, `-zotero` | none in `src/` | They go through the models, or through the backend's `exposed_functions` (users, review). Zotero's live `conftest` clears the database with raw Cypher. |
| `pangloss-models` | `RunCypher` (`migrations/changes.py:712`): Cypher written **by hand in a project's migration files** | user-written; it runs on whatever backend is installed |
| `pangloss-testing` | `live.py`: clearing and inspecting the test database | test support |
| `pangloss-calendar` | `graph.py`, 512 lines | see below |
| `pangloss-typology` | `graph.py`, 414 lines | see below |

The calendar and typology queries fall into three groups. Each needs something different:

**A. The add-on's own graph.** This is data no model owns: calendar `CalendarDay`/`CalendarMonth`/`CalendarYear`/
`CalendarSpan` with `NEXT`, `CONTAINS` and `CHARACTERISED_BY` (`MERGE_DAYS`, `LINK_RULE_EDGES`, `attach`, `detach`, …),
and the `PGLock` nodes. It is standard Cypher and already runs on both backends. **No change needed**, except that the
add-on should declare that it needs a Cypher backend.

**B. Reading model data through the storage format.** These queries know how the kit stores models:

- labels per class;
- field names as edge types (`` -[:`when`]-> ``, `-[:start]->`);
- embedded `Date` objects as nodes;
- `head_node_id` and `HeadNode`;
- `reverse: true` on reverse edges;
- the visibility rules.

They are typology's `types`, `entities_of`, `entity_counts` and `uses`, and calendar's `CHARACTERISATIONS` and
`DATED_BETWEEN`. Each has **its own copy of the visibility rule**: typology's `SEEN` (`graph.py:25`), calendar's
`DATED_BETWEEN` (`graph.py:464-466`) and `CHARACTERISATIONS` (`:214`, deleted only). Two more copies, besides the
kit's. They must use the kit's `visible()` and storage-format helpers (phase 4).

**C. Writing model data around the model write path.** Typology's `move` and `merge` (`graph.py:200-262`, `322-414`)
delete and create `is_subtype_of`/`is_supertype_of` and `has_type`/`type_of` edges directly. These are relations of
the models (`Typed[...]` fields, and a type's supertype). Because the writes bypass `save()`, I expect, from reading the
code but not from running it:

- no `PGUpdate` is recorded, so the version of the type, or of the entity or document that has the type, does not change;
- no write event fires, so `pangloss-history` records nothing, and restoring an earlier version of a document puts back
  a `has_type` to a type that `merge` has since deleted;
- `expected_version` checks do not see the change, so an editor holding an older read can save over the move or merge
  without a conflict;
- `MERGE (e)-[:has_type]->(b)` creates the edge with no properties, so if a `Typed` relation ever carries edge
  properties, `merge` drops them.

This is a correctness issue as well as an abstraction one. Phase 8 fixes it.

**`RunCypher`** is the same problem one level up: a project's migration file contains Cypher for one backend's storage
format. On Neo4j, `meta` and annotated values are flattened, so a hand-written `SET n.meta.x = …` that works on
Memgraph fails or does something different on Neo4j. On a future RDF backend it cannot run at all. Phase 10 addresses
it.

## 3. Rules for every phase

- **Both backends at once.** Until phase 3 is done, a fix lands in `pangloss-memgraph` and `pangloss-neo4j` in the same
  commit.
- **`./run_tests.sh` passes at the end of every phase**, on Memgraph and on Neo4j, and the add-ons' live tests run on
  both.
- **Moving code changes no behaviour.** A phase that moves code does not also change what it does. Behaviour changes
  are their own commits, each with a test that failed before it.
- **Measure the phases that change query text** (4, 5, 7, 10) on the large-data scratch database (:7689, see
  `docs/large-data.md`), before and after, for list, deep list, search, read, and the typology tree. Record the numbers
  in the phase's "as built" note. The plan cache keys on query text, and the shapes were tuned per planner.
- **Docs follow:** `docs/memgraph.md`, `docs/neo4j-implementation.md`, `docs/backend-neutral-addons.md` and this plan
  get an "as built" line per phase.

## 4. Phases

Sizes are estimates for focused work.

```
0 review fixes ─┬─ 1 binding ─── 2 move identical ─── 3 dialect + write path ─┬─ 4 visibility & format helpers ─┬─ 5 folding
                │                                                             │                                 ├─ 7 read/list/search in kit
                │                                                             ├─ 6 WritePlan ─── 8 typology writes
                └─ (9 conformance suite: starts after 2, runs alongside 3–8) ─┴─ 10 migrations & RunCypher
```

### Phase 0: the review's fixes, in both backends (2–3 days)

The fixes are small, each has a test that fails today, and they should not be carried into the move.

| Fix | Where | Test first |
|---|---|---|
| JSON log redaction before `json.dumps` | `pangloss-core/logs.py:88-101` | `{"password": "hunter2"}` (double quotes) in the json case of `test_logs.py` |
| `SETTINGS` assigned after validation | `pangloss-core/settings.py:51-57` | failed construction leaves the previous `SETTINGS` |
| List search words: Memgraph uses `search_words` (Neo4j already escapes) | `build_list_query.py:156` | `(`, `.`, `[a`, `C++`, plain and deep, in `test_list.py` of both |
| `test_lock`: disjoint writes, so it fails without the lock | `test_lock.py` of both | run once with `lock` removed: must fail |
| Remove the redundant timeout handlers | `exposed_functions.py` of both (lines 168-174, 205-211 in memgraph) | coverage shows them unreachable; existing timeout tests still pass |
| Fixtures: clear on setup too; drop the `/tmp/mg_data` volume; fix the `DEFAULT_INTERFACE_LANGUAGES` typo | memgraph `conftest.py`, `pangloss-testing/live.py` | — |
| Deletions: `test_experiment.py`, `test_write_edge_properties`, `compress`, `QuerySubstring`, empty `indexes.py` and `tooling/`; `pytest-asyncio` out of runtime deps | both backends | — |
| Assertions for `test_massive_write`; a concurrent-create test for `write_with_retries` | `test_create.py`, new | the retry test must reach `exposed_functions.py:481-483` |

**Done when** the review's findings 1–4 and 8–11 are closed in both backends.

**As built (2026-10-31).** All of the table, in both backends. Each new test was seen to fail first:

- the JSON redaction case;
- the settings case;
- the punctuation search, which raised a `ClientError` on Memgraph;
- `test_lock`, run with `lock` taken out: `[0, 1, 1, 1, 1, 1]` on Memgraph and `[0, 0, 0, 0, 0, 0]` on Neo4j.

Also:

- the bulk helper `_session` is now the public `open_session`;
- `id_condition` is gone, and `return_identifier` starts as `None`;
- `test_edit_cycle` and `test_sdk_contract` collect only `AssertionError`, `ValidationError`, `Neo4jError` and the
  Pangloss errors;
- `test_recursive_type` and the `"off"` migration check have assertions;
- `run_tests.sh` starts with `ruff format --check` and `ruff check --select F`;
- the coverage gate is documented as `pangloss_models` only.

Left as they are:

- `ensure_user` is still autouse;
- the 65 bugbear (`B`) findings are not in the check;
- the review's finding 7 (visibility, creation join, the inline `user` variable) waits for phases 4 and 7.

Found on the way: a bare `SemanticSpace[...]` field was accepted, though it should not be (a semantic space is a
subclass). Fixed 2026-11-01: `initialise()` refuses it with a `PanglossModelError`.
`test_recursive_type` now uses `Subjunctive[...]`.

### Phase 1: explicit database binding (3 days)

As proposed in the review discussion: decorators look up the database at call time; `connect(settings)` and
`using(db)` replace the `Database.default` class attribute; `ensure_driver()` replaces the 17 `hasattr(database,
"driver")` checks; `bulk_loading` moves from the class to the context; settings get `configure()` and `get_settings()`.

- **Files:** `database.py` and `exposed_functions.py` of both backends; `pangloss_core/backend.py` (`current()` gives
  the connected database: `backend.current().database()`); `pangloss_core/settings.py`; the API lifespan;
  `pangloss_cli/users.py` (`run_with_database`); `pangloss_testing/live.py`; the typology and calendar `_database()`.
- **Done when:**
  - `import pangloss_memgraph.databases.memgraph.exposed_functions` works with no database;
  - the conftests no longer need to reuse `Database.default` or re-set the settings per module;
  - a test that connects a second database inside `using()` reads from it.

**As built (2026-10-31).**

- **The database.** Each backend's `database.py` has:
  - `Database(settings)`, with no side effects, and `ensure_driver()`;
  - `install(database)`, `current()` and `using(database)`;
  - module-level `read_transaction` and `write_transaction`, which find the database when they are called;
  - `Database.run_read` and `run_write`, which the instance decorators use too.

  `Database.default`, `_instances`, `with_database`, `initialise_default_database`, `_check_driver`, and the 17
  `hasattr(database, "driver")` checks are gone. `setup.create_database(settings)` installs a database if there is
  none.
- **The add-on API.** `backend.current()` gives the add-on API, and `.database()` the database in use.
- **`STORAGE`** (decision 3, brought forward):
  - `pangloss_core.storage` has `Storage` (name, package, `capabilities`, and the parts `operations`, `setup`,
    `migration_backend` and `cypher`), `Capabilities`, and `storage_of(settings)`;
  - `pangloss_memgraph:storage`, `pangloss_neo4j:storage`, and `pangloss_sdk.storage:api` and `:api_sync`;
  - the models, users, review, the API, the CLI and the add-ons find the backend through it;
  - the project template, the demo and every test use `STORAGE`.

  `Capabilities` is defined, but the CLI and the API do not ask it yet: that is still phase 3.
- **Settings.** `configure(settings)` and `get_settings()`.

Done-when checks:

- **Import with no database:** met, and tested in `test_database_binding.py` (a subprocess).
- **The conftests:** they make and install their own `Database`. They still re-set the settings and the database per
  module, because other packages' tests in the same xdist worker make their own, and both are process-wide by
  design.
- **`using()`:** met. `test_another_database_is_used_within_using` writes to and lists from the bulk-load server
  inside `using()`, and from the main one outside it, on both backends.

### Phase 2: `pangloss-cypher`, and the identical files moved into it (1–2 days)

- Create `packages/pangloss-cypher` (depends on `pangloss-models`, `pangloss-users`, `neo4j`).
- Move these files **unchanged**: `delete_node`, `read_incoming`, `review`, `users`, `lookup`, `build_tree`,
  `from_database`, `visibility` (about 1,040 lines, no differences between the backends today). Both backends import
  them from `pangloss_cypher`.
- Add a CI check (a test in `pangloss-cypher`) that fails if the backends contain a module whose text matches a module
  in the kit, so that nothing gets copied back.
- **Done when** both backends' tests pass using the moved modules, and the duplicated files are deleted.

**As built (2026-10-31).**

- **Moved** to `packages/pangloss-cypher`, unchanged: `delete_node`, `review`, `users`, `lookup`, `build_tree`,
  `from_database` and `visibility`. Both backends import them from `pangloss_cypher`.
- **Moved with them**, because they are identical and the moved files need them:
  - `Transaction` (`transaction.py`);
  - `VERSION_OF_HEAD` (`heads.py`);
  - `check_user_exists` (`checks.py`);
  - `native_datetime` (`values.py`).

  The backends' modules import these back, so their old names still work.
- **Not moved: `read_incoming`.** It calls `build_fetch_incoming_query`, which differs between the backends, so it waits
  for the dialect (phase 7).
- **Tests:**
  - `test_build_tree` is now one copy, in `pangloss-cypher/tests`;
  - `test_no_copies.py` fails if a backend has a module with a kit module's name, or its text (seen to fail with a
    renamed copy of `lookup.py`);
  - the Neo4j contract test no longer compares `users` and `review`, which exist once.

### Phase 3: the `Dialect`, transactions, and the write path (1 week)

- `pangloss_cypher/dialect.py`: the `Dialect` protocol. **Only** the methods the diffs require at this point:
  - `tree_below`;
  - `encode_properties` / `decode` / `meta_expr`;
  - `entity_by_id`;
  - `is_timeout` / `is_unique_violation`;
  - `before_replace` (Neo4j takes the node lock) and `retry_on_check_conflict`.

  `MemgraphDialect` and `Neo4jDialect` live in their backends.
- `pangloss_cypher/transactions.py`: one `read_transaction`/`write_transaction` implementation, with logging, timeout
  translation through `dialect.is_timeout`, and migration refusal. Neo4j's `DecodingTransaction` becomes the generic
  `dialect.decode` wrapper. Each backend keeps only how it makes its driver.
- Move `build_create_query` (5 lines differ), `validate_write` (6), `build_update_query` (12) and the write half of
  `exposed_functions` (`create_head_node`, `update_head_node`, `write_with_retries`, delete/undelete) into the kit,
  through the dialect.
- `Capabilities` (snapshots, fast bulk load, accent folding, deep search, cypher) as a frozen dataclass on each
  backend's `backend` module. The CLI and the API ask it instead of using `hasattr(migration_backend, "backup")`. This
  is cheap now, and it is the first piece of the deferred port.
- **Done when:**
  - both backends' write tests pass;
  - no `neo4j.exceptions` name appears in the kit outside `dialect.py` implementations and `transactions.py`;
  - `exposed_functions.py` in each backend is a thin re-export.

**As built (2026-10-31).**

- **`pangloss_cypher/dialect.py`, the `Dialect` protocol.** Its methods:
  - `driver_options` and `wrap_transaction` (Neo4j's decodes);
  - `is_timeout` and `is_unique_violation`;
  - `retry_on_check_conflict` and `before_replace` (Neo4j's takes the node lock);
  - `encode_properties` (Neo4j flattens);
  - `has_meta` and `meta_of`;
  - `entity_labels`;
  - `tree_below`.

  `MemgraphDialect` and `Neo4jDialect` are in each backend's `dialect.py`. The rendered query text is the same as
  before on each backend; I compared the fragments.
- **`pangloss_cypher/transactions.py`, the one transaction layer.** It has `Database`, `install`, `current`, `using`,
  `read_transaction`, `write_transaction`, `dialect()`, the logging, the timing, the timeouts and the migration
  refusal. The loggers keep each backend's name: `pangloss.<dialect>.transactions`.
  - A backend's `database.py` is now a subclass that names its dialect, plus re-exports.
  - `test_connection_log` is one copy, in the kit.
- **Moved into the kit:**
  - `build_create_query`, `validate_write` and `build_update_query`;
  - `write_functions.py`: the write half of `exposed_functions` (create, update, replace, delete, undelete, `announce`,
    `write_with_retries`) and the user and review wrappers.

  The backends' `exposed_functions` import these from the kit and keep only the reads, about 330 lines each (it was
  730). So the done-when "a thin re-export" is met for the writes; the reads wait for phase 7.
- **Driver exceptions.** None are named in the kit outside `transactions.py`. The kit catches unique violations
  through `dialect().is_unique_violation`. On both backends that is a `ConstraintError`, or a `ClientError` saying
  "unique constraint". This is slightly wider than before: Memgraph's write retry used to look only at the
  `ClientError` text.
- **`Capabilities`.** The CLI's `backups`, `restore` and `migrate --backup` ask `capabilities.snapshots`, not `hasattr`.
  `test_a_backend_without_snapshots_says_so` covers a backend without them.
- **Tests:** `./run_tests.sh` passes in full: Memgraph 2,479, Neo4j 584, the add-ons' live tests on Neo4j, and 57
  browser tests.

### Phase 4: one visibility rule, and storage-format helpers for add-ons (3–4 days)

- `pangloss_cypher/fragments.py`:
  - `visible(node, head)` (deleted, published, `$see_unpublished`, `$published`, `$review_status`);
  - `head_of(node, as_)`: the `OPTIONAL MATCH (h:HeadNode {id: n.head_node_id})` / `coalesce(h, n)` idiom;
  - `field_edge(field)`: a backticked, checked edge type;
  - `label(name)`: a checked label.
- Use them in the kit's list, read, search and autocomplete. This replaces the 8 copies in `build_list_query.py` and
  the ones in `build_read_query.py` and `build_search_query.py`.
- **Add-ons:** typology's `SEEN`, and calendar's `DATED_BETWEEN` and `CHARACTERISATIONS`, use `visible()` and
  `head_of()` from `backend.current()` (the `Backend` protocol in `pangloss_core.backend` gains `fragments`).
  `CHARACTERISATIONS` gets the published rule it lacks, if characterisations can be documents. Today it filters
  `deleted` only.
- Typology and calendar declare `requires = {"cypher"}`. Start-up checks it against `Capabilities` and gives a clear
  error.
- **Done when:**
  - `grep -n "coalesce(.*deleted" packages/*/src` finds the rule only in `fragments.py`;
  - the add-ons' live tests pass on both backends;
  - the measurements show no slower query (each fragment produces the same text as the code it replaces, so the plans
    should not change).

**As built (2026-11-01):**

- **`pangloss_cypher/fragments.py`.** It has:
  - `visible(node)` for a head node;
  - `visible(node, head, filters=...)` for any node, where `head` is its head node. Only `deleted` counts for an
    entity. `filters` adds `$published` and `$review_status`;
  - `hidden(head)`, its negation, for the search's `NOT EXISTS`;
  - `deleted`, `not_deleted` and `published`;
  - `head_of(node, as_)`, a `HeadOf` with `.match`, which writes itself as `coalesce(as_, node)`;
  - `label` and `field_edge`, which backtick a name and refuse anything that is not an identifier.
- **The kit and the backends use them.** That covers list (the 8 copies, and Neo4j's own `visible` in the plain list),
  read and search on both backends; autocomplete; and the kit's `delete_node`, `review` and `build_update_query`.
  - A script built the list, read and autocomplete queries for a document and an entity class, with and without
    search and deep search, before and after the change. Apart from whitespace, the text is the same.
  - The search changes were word-for-word: the same strings, now from the fragments.
- **Add-ons.**
  - Typology's `seen()` and `not_deleted()` and calendar's queries take the fragments from `backend.current().fragments`.
    The `Backend` protocol and both backends' `backend.py` now provide `fragments`.
  - Calendar's `CHARACTERISATIONS`, `MANUAL_BETWEEN` and `DATED_BETWEEN` became functions that build the query when
    called, because the backend is not known at import time.
  - `DATED_BETWEEN` checks its class and field with `label` and `field_edge`, replacing its own `IDENTIFIER` regex.
  - The query text is the same, except typology's `SEEN`, whose two conditions are now in the usual order (same
    meaning).
  - `CHARACTERISATIONS` keeps only the `deleted` test: characterisations are entities, and an entity is always
    published.
- **`requires`.**
  - Typology and calendar declare `requires = {"cypher"}`.
  - `pangloss_core.storage.check_requirements(settings)` checks each installed app's `requires` against the backend's
    `Capabilities`. A name that is not a capability is an error too.
  - The API (`prepare_models`) and the CLI (`load_database`) call it at start-up.
- **Tests.**
  - `pangloss-cypher/tests/test_fragments.py`. Its last test is the done-when grep: no line in `packages/*/src` outside
    `fragments.py` matches `coalesce(.*deleted`. It failed before this phase.
  - `pangloss-core/tests/test_storage.py` covers `check_requirements`.
  - `./run_tests.sh` passes: Memgraph 2,497, Neo4j 585 (the contract test now leaves `fragments`, a module, out of the
    signatures, and checks both backends give the kit's), typology 19, calendar 16, dates 4, zotero 7 on Neo4j, and 57
    browser tests.
- **Not measured on :7689.** The list, read, search and autocomplete text is unchanged apart from whitespace, so the
  plans cannot change. The scratch database was not running, so I did not run the large-data timings.

### Phase 5: accent folding on both backends (4–5 days)

Neo4j folds already (`standard-folding` analyzer, and `schema.fold` on the words searched for). For Memgraph:

1. **Move `fold`** from `pangloss_neo4j/.../schema.py:207-217` to `pangloss_models.text` (with `FOLDED`). Both
   backends and `pangloss_models.autocomplete.search_words` use it, so the words searched for are folded the same
   way everywhere.
2. **A folded label on Memgraph:** every node written with a `label` also gets `label_folded = fold(label)`.
   - It is written in one place: the kit's property encoding, as `MemgraphDialect.encode_properties` adding it (Neo4j's
     analyzer folds, so it adds nothing).
   - Through that, it covers creates, updates, inline entities and the bulk loader.
3. **The text index moves** to `label_folded` (`label_text` on `PGIndexableNode(label_folded)`), in
   `initialise_database` and the `structure()` that migrations snapshot.
4. **A shipped migration**, `pangloss_memgraph/migrations/0006_…`, which:
   - backfills `label_folded` in batches (the runner's window batching);
   - drops and remakes the text index.

   Neo4j gets an empty `0005` only if the snapshots need to stay aligned.
5. **Searches fold the words:** list, deep list, the truncation query, and autocomplete (`search_words` folds).
   Autocomplete's "label begins with" ordering compares against `label_folded`.
6. **Labels written outside the kit:**
   - migration operations that set `label` (renames, `RunCypher`): phase 10 routes them through the dialect;
   - until then, add `pangloss memgraph refold`, which re-runs the backfill, and mention it in the migration docs;
   - typology writes labels through `Type.Create`/`Update`, so it is covered by step 2.
7. **Conformance test:** `zurich`, `ZURICH` and `Zürich` all find "Zürich", and `strasse` finds "Straße", on both
   backends (list, deep list, autocomplete). Also update the "accent folding" capability and the open question in
   `neo4j-implementation.md`.

- **Measure:** index size and write time (a second text-indexed property costs about the same as the first; the text
  index costs about 4.5 ms per commit, see the memory note on text-index write cost). Check that the index is on
  `label_folded` **instead of** `label`, not as well as it.
- **Done when** the conformance test passes on both backends and a migrated copy of the demo database finds "Zürich"
  with `zurich`.

**As built (2026-11-01):**

- **`pangloss_models.text`** has `fold` and `FOLDED`, moved from Neo4j's `schema.py`, which now imports them.
  `search_words` folds, so both backends fold the words of a list, deep list, truncation query and autocomplete in
  the same way.
- **`label_folded` on Memgraph.** `MemgraphDialect.encode_properties(properties, node=True)` adds
  `label_folded = fold(label)`.
  - A label of null gives a null `label_folded`, so `SET +=` clears it.
  - Edges are encoded with `node=False` and get nothing. The `Dialect` protocol gained the `node` keyword for this.
  - Creates, updates, inline entities and the bulk load all write through it.
- **The text index** is `label_text` on `PGIndexableNode(label_folded)`, instead of `label`: there is still one text
  index.
  - `initialise_database` moves an index left on `label`, and fills in the folded labels.
  - Autocomplete's "label begins with" ranking compares `label_folded` on Memgraph. Neo4j still compares
    `toLower(label)` with the words as typed, as before.
- **Shipped migration `0006_removeindex_runpython_addindex`** has three steps:
  - `RemoveIndex` (on `label`);
  - `RunPython` `folding.refold_in_migration`, in batches of 10,000 inside the migration's transaction;
  - `AddIndex` (on `label_folded`).

  The planner proposed `AddIndex` + `RemoveIndex`, with the same schema hash. I put the removal first so that the
  two indexes, which share a name, never both exist. Neo4j needs no migration.
- **`pangloss memgraph refold`** writes the folded labels in transactions of 10,000 (`folding.refold`). It is for
  labels set outside the models, for example by a `RunCypher`; `docs/migrations.md` says so.
- **`Capabilities.accent_folding`** is now on for Memgraph.
- **Tests.**
  - `test_accent_folding_live.py`, the same file in both backends: `zurich`, `ZURICH`, `Zürich`, `zür`, `strasse` and
    `Straße` find "Hauptstraße, Zürich" in list and deep list. Autocomplete is covered too, and so is a changed label
    being found only by its new words.
  - In `test_initialise_database.py`: an index on `label` is moved, and `zurich` then finds "Zürich" through it.
  - `test_refold_writes_the_folded_labels_of_labels_written_without_them`.
  - `./run_tests.sh` passes: Memgraph 2,516, Neo4j 602, typology 19, calendar 16, dates 4, zotero 7 on Neo4j, and 57
    browser tests.
- **Not done.**
  - No measurement on :7689: the scratch database was not running. There is still one indexed text property, now
    `label_folded`, so the cost per write should be the same.
  - I did not migrate a copy of the demo database, because I don't touch the demo Memgraph. The live test of the
    shipped migrations and the index-move test cover the same path.

### Phase 6: separate the write plan from the Cypher (1 week)

- `pangloss_cypher/write_plan.py`: `WritePlan` (nodes with labels and encoded-free properties; edge pairs with
  names and properties; references to check; URLs; inline entities). It is produced from a `CreateDB`/`UpdateDB`
  instance with no database and no Cypher. **Design it as if SPARQL will render it** (decision 1): no Cypher variable
  names, and no `reverse: true` in it (the renderer adds the reverse edges).
- `render_write.py`: `WritePlan` → Cypher through the dialect. The validators read the plan.
- Unit tests of the planner in `pangloss-cypher/tests`, with no database: the shapes now covered only by live tests in
  `test_create.py` (nesting, semantic spaces, `Fulfils` labels, subclassed edges, inline entities, edge properties).
- Keep the query text the same for a document of the same shape. `test_a_write_of_the_same_shape_is_the_same_query_text`
  must pass unchanged.
- **Done when** `build_create_query.py` is gone and the planner has its own unit tests.

**As built (2026-11-01):**

- **`pangloss_cypher/write_plan.py`.**
  - `plan_create(instance)` and `plan_update(instance, previous_meta)` give a `WritePlan`, a tree of `PlannedNode`s
    (id, type, class labels, properties, URLs) and their `Relation`s.
  - A relation has the `(forward, backward)` names of its edges (the field's, then each subclassed parent field's),
    its edge properties, and a target: a `PlannedNode`, a `ReferenceToExisting` or an `InlineEntity` (which carries
    the entity's own node).
  - The plan has no Cypher variables, no `reverse: true`, no `HeadNode`/`PGIndexableNode`, no `PGCreation`/
    `PGUpdate`, no user match, and no dialect encoding. All of those belong to the renderer.
  - The hooks (`properties_for_new_head`) and `previous_meta` are planning inputs.
  - `walk(existing)` goes through the relations in render order. It writes an inline entity once, at its first
    place, and only if it does not exist.
  - `inline_entities`, `references(existing)`, `nodes_to_write(existing)`, `urls_to_write(existing)` and
    `created_entities(existing)` are built on `walk`.
- **`render_write.py`.** `render(plan, existing)` gives the `QueryObject` (match and create parts, `QueryParams`).
  `PropertyAssignments` encodes through the dialect. `build_head_create_query(instance, existing)` is `render(plan_create(...))`.
- **Checks.** `validate_write`'s checks read the plan: `check_references_exist(tx, plan, existing)`,
  `check_ids_available(tx, plan, existing)` (`is_update` comes from the plan) and `check_urls_available(tx, plan,
  existing)`. `write_functions.checked_plan` runs them for both create and update. The plan is made once; the
  builder used to build the query twice when the document had inline entities.
- **Small modules.** `params.py` (`Identifier`, `QueryParams`) and `values.convert_type_for_writing`, which the reads
  also use.
- **`build_create_query.py` is gone.** `build_update_query.build_head_update_query` is `render(plan_update(...))`.
  `build_replace_head_query` is unchanged.
- **Same query text.** A script recorded the old builder's output for an `Order` with every shape and then compared
  the planner and renderer against it, on both dialects. The shapes were:
  - an inline entity, new and existing, by id and by URL, given twice;
  - references by id, twice, and by URL;
  - edge properties, subclassed edges, a semantic space, a conjunction, a reified relation, an embedded object and an
    annotated value;
  - an entity with a URL;
  - an update with `previous_meta`.

  The query text is the same apart from whitespace: two empty lines are gone, from the `set`/`merge` parts that were
  never used. The parameters (`x1`, `x2`… with the same values), references, nodes, URLs, inline entities and created
  entities are exactly the same in all 17 cases.

  `test_a_write_of_the_same_shape_is_the_same_query_text` is unchanged apart from its import, which is now
  `pangloss_cypher.render_write`.
- **Tests.**
  - `pangloss-cypher/tests/test_write_plan.py`: 7 planner tests with no database. They cover nesting, subclassed
    edges with edge properties, references by URL, semantic spaces, `Fulfils` labels, inline entities (repeated,
    by URL, existing) and an update keeping creation `meta`.
  - `./run_tests.sh` passes: Memgraph 2,523, Neo4j 602, typology 19, calendar 16, dates 4, zotero 7 on Neo4j, and 57
    browser tests.

### Phase 7: read, list, search and autocomplete in the kit (1 week)

- Move `build_read_query`, `build_list_query`, `build_search_query` and `build_autocomplete_query` into the kit, using
  the phase 4 fragments and these dialect methods: `label_param`, `text_search`, `search_patterns`, `tie_break`,
  `facets_from`.
- The **override hatch**: each kit query has a name (`"list.plain"`, `"list.deep.entities"`, `"read.document"`, …), and
  `dialect.query(name, default)` may replace it whole (same parameters, same columns). Use it only where the
  measurements show that one shared text is slow on one backend.
- The read path returns a `GraphFragment` (root, labels, edges, meta) to `build_tree`. This is the neutral read shape
  the deferred port would use.
- Settle the creation-record join: `OPTIONAL MATCH` in every list branch (review finding 7), with a test of a head that
  has no `PGCreation`.
- **Done when** `exposed_functions.py` in each backend is gone or a few lines long, and the measurements show no
  regression.

**As built (2026-11-01):**

- **In the kit.** `pangloss_cypher.read_query` (the read of a document or entity, what refers to an entity, what wrappers
  hold), `list_query`, `search_query` (`Compiler`, `build_search_query`), `autocomplete_query`, `read_incoming`, and
  `read_functions` (`list_items`, `search`, `autocomplete`, `get_document`, `get_entity`, `get_entity_for_edit`).
  `operations` gathers these and the writes. **Each backend's `exposed_functions.py` is now three lines**, a re-export
  of `pangloss_cypher.operations`. The ten `build_*_query.py` and `read_incoming.py` files of the backends are gone.
- **The dialect's new parts.** Besides the plan's `text_search`, `search_patterns`, `tie_break` and `facets_from` (with
  `read_facets`, which makes Neo4j's list of `{type, nodes}` a map), it needed:
  - `autocomplete_start` and `folded_label`;
  - `meta_property` (`n.meta.x` on Memgraph, `` n.`meta.x` `` on Neo4j);
  - the walks `down_tree`, `up_reverse` and `through_wrappers` (BFS and lambda filters on Memgraph, quantified path
    patterns on Neo4j);
  - `search_compiler`;
  - `query(name, default, **context)`, the override hatch.

  `label_param` was not needed: the only `$label` that differed is in the part Neo4j replaces.
- **Where the backends keep their own text.**
  - **`list.plain.page`** (`pangloss_neo4j/.../queries.py`): Neo4j sorts the ids and slices them, because `SKIP` after
    `ORDER BY` made it plan a `Top` that ran out of memory. It is the only use of `query()`.
  - **`Neo4jCompiler`** (`pangloss_neo4j/.../search.py`): it finds what is related to given ids, or to a pattern, once,
    in a subquery before the `MATCH`, where Memgraph tests it from each node in an `EXISTS`. It also looks up the head
    node of a document by its id, rather than walking up to it.
- **One text where Neo4j's form works on Memgraph.** Memgraph 3.14 takes `CALL (x) { ... }` (with `UNION` inside), so
  the deep list uses it on both. The read query collects in two steps on both (`collect(rp) AS root_paths`, then the
  sum), as Neo4j needs.
- **Checked by snapshot.** A script recorded 63 queries from each backend's old builders, with the demo's models and
  their parameters. The cases were:
  - lists of four classes: plain, text search, deep, with punctuation, with and without filters;
  - the truncation check;
  - read, read of an entity, incoming, held;
  - autocomplete;
  - 24 structured searches.

  The results:
  - **Neo4j:** all 63 are exactly the same.
  - **Memgraph:** 39 are exactly the same and 13 search queries differ only in variable names. The changed text is:
    - the walks' lambda variables (`(e, n | …)` is now `(tree_edge, tree_to | …)`);
    - the deep list's scoped subqueries (`$targetType` is now used directly rather than through `WITH … AS
      targetType`);
    - the read query's two extra `WITH` steps.

  The parameters are the same in all of them.
- **Measured** on the scratch database (:7689, 642,551 nodes), best of three through the models, in ms. "Before" is
  phase 6; "moved" is this commit. (The scratch data were loaded under older demo models, so a read fails validation
  after its queries have run; the times are of the queries.)

  | | Before | Moved |
  |---|---|---|
  | list Person, page 1 / page 200 | 45 / 42 | 46 / 44 |
  | list Factoid, page 1 / page 100 | 26 / 25 | 25 / 25 |
  | list, text search: Person "person 42" / Factoid "factoid 123" | 164 / 70 | 151 / 71 |
  | deep list: Factoid "person 4242" / Person "factoid 12345" | 529 / 78 | 516 / 80 |
  | read Factoid / Person / busy Person with what refers to it | 2 / 3 / 14 | 2 / 3 / 13 |
  | autocomplete "person 42" / "pla" | 5 / 4 | 5 / 4 |
  | search: year / source is / activity by / `$mentions` / through `Negative` / `$incoming` | 2 / 32 / 49 / 333 / 37 / 10 | 2 / 33 / 50 / 332 / 37 / 9 |

  There is no regression. The changes are within the run-to-run variation, which is about 10%. Neo4j's text did not
  change, so it was not measured again.
- **The creation-record join (review finding 7), in its own commit.** Every list branch now joins `PGCreation` and its
  user with `OPTIONAL MATCH`. Before, the plain and deep lists used `MATCH`: a head with no `PGCreation` was counted,
  but left off its page (and when every item lacked one, the page and the count were empty). The text-search list,
  which already used `OPTIONAL MATCH`, failed instead: a document's reference view refused `created_when: null`.
  `_DocumentReferenceViewAPIMeta.created_when` may now be `None`; its default is unchanged.

  A new test, `test_what_has_no_record_of_its_creation_is_listed_all_the_same`, is the same in both backends. It
  deletes the `PGCreation` of an entity and a document, then lists each plainly, by text and deep. It failed before
  the change. The timings with it were the same as above, within the variation (deep Factoid 532 ms, list Person 47
  ms, text search 149 ms).
- **The read shape.** `build_tree.GraphFragment` (root, labels, edges, meta) is what `get_document` and `read_entity`
  build the tree from (`GraphFragment.from_record(record).tree()`).
- **Tests.**
  - A new contract test checks that both dialects have every part of the `Dialect` protocol with its signature, and
    that a dialect's search compiler is the kit's or a subclass of it.
  - The timeout tests patch `pangloss_cypher.read_functions`.
  - `test_read` and `test_model_indexes_live` import from the kit.

### Phase 8: typology writes through the model layer (4–5 days)

The bypass in [§2 C](#2-cypher-outside-the-backends). Two operations, in the kit (shared by both backends, and later
part of the port):

- **`move`**: a type's supertype is its own `is_subtype_of` field. Do it as an update of the type
  (`Type.Update(..., is_subtype_of=…).save(expected_version=…)`), inside the hierarchy lock. The loop check stays in the
  same transaction. This needs the write path to accept a pre-write hook that runs inside the transaction (for the lock
  and the loop check). Phase 3's `before_replace` is the place.
- **`merge` (relink)**: "everything that has A as `has_type` now has B" may touch thousands of heads. Calling `save()`
  for each is too slow. Add a kit operation, `relink(field, from_id, to_id)`, which in one transaction (or batches, like
  the migration runner):
  - rewires the edge pairs;
  - **keeps edge properties**;
  - records one `PGUpdate` per affected head (an entity, or the head of a document whose nested node had the edge);
  - after commit, emits one write event per head, so that history records the change.
- Calendar does not write model data (group A only), so it needs nothing here.
- **Tests (both backends):**
  - after `move` and after `merge`, the versions of the affected heads go up by one;
  - `pangloss-history` has a record for each;
  - an edit from the old version gets `PanglossVersionConflictError`;
  - a `has_type` with edge properties keeps them through `merge`.
- **Decision before starting:** should `merge` bump the version of every document that refers to the merged type? It
  is what keeps history and conflict checks correct, but it means a merge on a large vocabulary is a large write.
  *Recommendation: yes, batched, with the count reported by the command.*

**As built (2026-11-01):**

- **The decision.** The plan asked first whether `merge` should bump the version of every document that refers to the
  merged type. It went ahead with the recommendation, without a new answer: yes, batched, with the count reported.
  This is easy to change, in `relink`, if the answer is no.
- **`move`** (`pangloss_typology.service.move_type`) is `Type.Update(..., is_subtype_of=[to]).save(expected_version=…,
  before_write=…)`. The update path has a new hook, `before_write(tx)` (`write_functions.BeforeWrite`). It runs first
  in `replace_head_node`'s transaction, before the backend's own `before_replace` and the version read. Typology
  passes `graph.check_move`, which takes the hierarchy lock and checks the type, the target and the loop again. If
  the type is changed between its read and the update, the move reads it again, up to three times.
- **`relink(field, reverse, from_id, to_id, *, keep=(), before=None, batch_size=1000)`** (`pangloss_cypher.relink`, in
  `operations`). In each batch's transaction it:
  - checks the user;
  - runs `before`;
  - finds up to 1,000 nodes with the relation, and their heads (`coalesce(head_node_id, id)`);
  - takes each head's `before_replace` lock (Neo4j);
  - creates the new edge pair with `properties(old)`, unless the node already has the relation to the target;
  - deletes the old pairs;
  - records a `PGUpdate` for each head.

  After each commit it sends one write event per head. Its payload is what the head is now, read and made into an
  `Update`, and it is read only if something listens. It gives the number of heads. A batch that finds edges but
  deletes none raises an error rather than looping.
- **`merge`** (`service.merge_counted`; `merge` gives the `TypeOut` as before):
  - if the target is below the source, it first moves the target into the source's place (an update);
  - it relinks the subtypes, under the lock, with `graph.check_merge` refusing if the target is below the source;
  - it relinks `has_type`;
  - it moves the source to the root (an update), then deletes it.
- **`graph.py`** no longer writes the hierarchy. `move` and `merge` are gone; `check_move`, `check_merge` and
  `is_below` are what is left.
- **Tests**, in typology's live tests, which run on both backends (Memgraph in the package run, and Neo4j with
  `PANGLOSS_TEST_BACKEND=neo4j`, 22 passed):
  - `test_a_move_is_an_update_of_the_type`: the version goes up by one, there is one write event with a payload, and
    an edit from the old version gets `PanglossVersionConflictError`;
  - `test_a_merge_writes_a_new_version_of_each_head_it_changes`: a typed entity, a letter whose nested statement has
    the type, and a subtype each go up one version and get an event; the counts are (1 subtype, 2 heads); an old edit
    is refused;
  - `test_a_merge_keeps_the_properties_of_the_edges`: `ViaEdge[Typed[...], Certainty]`. The properties are on both
    edges after the merge.

  All three failed before the change. The third was a real bug: the old `MERGE` dropped the edge's properties, and
  the entity could no longer be read (`edgeProperties` field required). The events stand in for `pangloss-history`'s
  records, since history is a listener of exactly these.

### Phase 9: one conformance suite (2 weeks, alongside 3–8)

- `pangloss_testing/conformance/`: test modules written against **the models** (`Person.Create(...).save()`, `.get`,
  `.list`, `.search`, delete, review, users, migrations through the CLI functions). Because they use the model API and
  not the kit, they are already the tests a future non-Cypher backend would run (decision 1).
- `Inspect` (`count(kind)`, `labels_of(id)`, `edges(from, name, to)`, `raw(query)`) for the checks that look underneath.
  The kit supplies the Cypher implementation, through `dialect.decode`. A test that needs `raw` is marked
  `@requires("cypher")` or with its backend.
- Move the tests file by file, starting with the largest overlaps (`test_create`, `test_update`, `test_read`,
  `test_read_entity`, `test_list`, `test_delete`, `test_inline_entities`). As each file moves, delete it from **both**
  backends. Each backend's `tests/` keeps only what `NOT_PORTED.md` lists: DDL, bulk modes, snapshots, query plans, and
  the dialect's unit tests.
- The add-ons' live tests replace their raw clear/inspect Cypher with `Inspect` and the shared `clear_database`.
- The suite's rules (from the review):
  - clear the database on setup and teardown;
  - no blanket `except Exception`;
  - every concurrency test is shown once to fail with its mechanism removed, and the note goes in the test's
    docstring.
- **Done when** each backend's own test folder is under about 3,000 lines, and the suite runs on both backends from one
  copy.

### Phase 10: migration operations and `RunCypher` (1 week)

- Move `migrations/operations.py`, `runner.py` and `conversion.py` into the kit, through the dialect (for `meta`, maps,
  labels and `id()`). Each backend keeps only its DDL operations (`add_index`, `remove_index`, constraints) and its
  snapshots.
- Operations that set `label` keep `label_folded` right, through `encode_properties`. Then `pangloss memgraph refold`
  can be deprecated.
- **`RunCypher` names its dialect:** `RunCypher(query=…, dialect="memgraph")`. `makemigrations` fills it in from the
  installed backend. `migrate` refuses a `RunCypher` for another dialect with a clear message ("this migration was
  written for Memgraph; give a Neo4j version with `RunCypher(..., dialect="neo4j")` next to it"). A change may hold
  one query per dialect. Existing files without `dialect` are taken as written for the backend that applied them, and
  `pangloss migrate` warns about them once. On a backend without the `cypher` capability (the RDF future),
  `RunCypher` is refused and `RunPython` is the way.
- **Done when** a project's migrations apply the same on both backends, and a foreign-dialect `RunCypher` is refused
  with that message.

## 5. Deferred: the `Storage` port

Not in this plan (decision 1). What the phases above leave for it:

- a neutral write plan (6) and read shape (7);
- a conformance suite that goes through the models (9);
- `Capabilities` (3), and `cypher` declared by the add-ons (4);
- a relink operation that already sits at operation level (8);
- no driver exceptions above the kit (3).

When it is wanted: define `Storage` in `pangloss_models.storage` as in
[database-abstraction.md §4](database-abstraction.md#4-layer-1-the-storage-port), make `CypherStorage` implement it,
and answer decision 3 then. That decision is whether `DATABASE_MODULE` stays, or becomes an alias of a `STORAGE =
"pangloss_memgraph:MemgraphStorage"` setting with a deprecation warning, which would mean every project's settings file
needs a one-line edit.

## 6. Total

About 8 to 10 weeks with phase 9 running alongside, against 4 to 6 in the abstraction doc. The difference is the
review fixes (0), folding (5), the typology writes (8) and `RunCypher` (10), which that estimate did not include.

**Stopping points**, each worth having on its own:

| After phase | What you have |
|---|---|
| 2 | Fixes made once for the shared files |
| 4 | One visibility rule everywhere, add-ons included |
| 5 | The same search results on both backends |
| 8 | Typology changes that are versioned and recorded in history |
