# Code quality review, 2026-10-31

Scope: `packages/`, mostly `pangloss-core` and `pangloss-memgraph`. This covers the code, and whether the tests check what
their names say. Branch `code-review-2`, at `22cd004`.

**How it was checked.** I read all of `pangloss-core` and the main modules of `pangloss-memgraph`: the database
wrapper, `exposed_functions`, the create/update/read/list/search builders, validation, delete, users, review, and the
start of bulk load and migrations. I also ran:

- the tests: core 13 passed; memgraph 540 passed in 93 s with `-n 4`;
- `ruff check` (pyflakes and bugbear rules), `ruff format --check`, `ty`, and `vulture`;
- an AST scan for tests that have no assertion;
- small probe tests against the test Memgraph on :7687. They were written into `tests/`, run, and then deleted, so
  nothing was left behind.

Each finding below says whether it was **confirmed** (I ran it and saw the result) or **read** (found by reading the
code only).

## Priorities

| # | Finding | Kind | Effort |
|---|---|---|---|
| 1 | JSON log format does not redact double-quoted secrets | bug, security | S |
| 2 | A list search with a regex character fails (`(`), or matches everything (`.`) | bug | S |
| 3 | A failed `Settings(...)` replaces the global `SETTINGS` with a broken object | bug | S |
| 4 | `test_lock` passes with the lock removed | test does not test | S |
| 5 | `exposed_functions` binds to `Database.default` at import time | design | M |
| 6 | Memgraph and Neo4j backends are about 3,000 identical lines | duplication | L |
| 7 | The visibility `WHERE` is pasted 8 times; the creation `MATCH` differs between list branches | maintainability, latent bug | S–M |
| 8 | Dead code and leftovers | tidy | S |
| 9 | Test fixtures: teardown-only clearing, persistent `/tmp` volume, settings typo | test reliability | S |
| 10 | Weak or assertion-free tests | test quality | S |
| 11 | Packaging and formatting | tidy | S |

---

## 1. JSON logs leak double-quoted secrets: confirmed

`packages/pangloss-core/src/pangloss_core/logs.py:88-101`. `JsonFormatter` calls `json.dumps` **first** and `redact`
**after**. `json.dumps` escapes `"` to `\"`. The password pattern (`logs.py:42-44`) expects the `:` or `=` to follow an
optional quote, so it no longer matches after the escaping:

```
{"time": ..., "message": "body {\"password\": \"hunter2\"}"}      <- JSON format: leaked
2026-10-31 ... body {"password": [redacted]"}                      <- text format: redacted
```

A JSON body logged by mistake is the case this "last defence" exists for, and `LOG_FORMAT=json` is the production
format.

**Fix:** in `JsonFormatter.format`, redact `entry["message"]` and `entry["exception"]` before `json.dumps`. Do not
redact the dumped string. Add a parametrised case to `test_a_secret_in_an_exception_is_redacted_in_json_and_text` with
`{"password": "hunter2"}` (double quotes). The current test uses only single quotes and a JWT, so it passes in both
formats.

Minor: the text format leaves a stray quote (`[redacted]"`). The pattern could swallow a closing quote that matches the
opening one.

## 2. List search puts raw user input into a regex: confirmed

`packages/pangloss-memgraph/src/pangloss_memgraph/databases/memgraph/build_list_query.py:156-159`:

```python
return [f".*{word}.*" for word in (search_terms or "").split()]
```

`?q=` arrives from `GET /api/<Model>?q=` (`pangloss-api/.../routes/models.py:262`) without any change. I probed it
through `Person.list(search_terms=...)`:

| `q` | Result |
|---|---|
| `(` (plain or `deep`) | `neo4j.exceptions.ClientError: Tantivy error: Unable to create regex search query`, an unhandled 500 |
| `.` | every label (`Tony Blair`, `C++ Programmer`) |
| `Tony`, `TONY`, `C++` | as expected |

Autocomplete does not have this problem: `pangloss_models.autocomplete.search_words` cuts the input to `\w+`, which is
how the index tokenises. The list search should do the same.

**Fix:** make `search_patterns` use `search_words` (or `re.escape` each word). Add tests to `test_list.py` for `(`,
`.`, `[a`, and `C++` in both plain and deep mode. The Neo4j copy needs checking too: it builds its patterns with its own
`schema.search_patterns`.

## 3. `SETTINGS` is replaced before validation: confirmed

`packages/pangloss-core/src/pangloss_core/settings.py:51-57`. `ClientSettings.__init__` assigns the global **before**
`super().__init__` validates. A construction that fails therefore leaves `SETTINGS` pointing at an object with no
fields:

```
validation failed: ValidationError
SETTINGS is the good one: False
reading SETTINGS: AttributeError 'Good' object has no attribute 'DATABASE_MODULE'
```

Any test that checks a settings validation error (`pangloss-api/tests/test_cors.py` does this) breaks the global for
whatever runs next. That is probably why `pangloss-memgraph/tests/conftest.py:198` needs `use_test_settings` to put the
settings back for every module.

**Fix:** assign after `super().__init__()` returns. Better still, let the app set `SETTINGS` explicitly rather than as
a side effect of construction. Also, `SETTINGS: BaseSettings` (line 114) is only an annotation, so reading it too early
gives an `AttributeError` on the module. A `get_settings()` that raises a clear message would help.

## 4. `test_lock.py` does not test the lock: confirmed

`packages/pangloss-memgraph/tests/test_lock.py`. I replaced `await lock(tx, key)` with `pass` and ran it:

- `test_transactions_that_lock_one_key_do_not_lose_each_others_changes` **still passes**. Every writer `SET`s the same
  `Counter` node, and Memgraph's snapshot isolation already makes those writes conflict and retry. The lock's purpose,
  as `backend.lock`'s docstring says, is to make transactions conflict when they write **different** nodes. This test
  never does that.
- `test_one_lock_node_is_made_...` fails, but only because it counts `l.writes`, which `lock` increments. It says
  nothing about serialisation.

The property is tested for real in `pangloss-typology/tests/live/test_typology_live.py:544` (racing moves never make a
loop). The unit test in the backend should still prove it on its own.

**Fix:** have each writer read `count(:Item)` and then `CREATE (:Item {seen: n})` (disjoint writes, no shared node).
Assert that the `seen` values are `0..WRITERS-1` with no repeats. Run it once without `lock` to confirm it fails. Do the
same in the Neo4j copy.

## 5. `exposed_functions` binds to a database at import time: confirmed

`exposed_functions.py` decorates about 30 functions with `@Database.default.read_transaction` /
`write_transaction`. The bound instance is whichever `Database` existed **when the module was imported**:

```
$ python -c "import pangloss_memgraph.databases.memgraph.exposed_functions"
AttributeError: type object 'Database' has no attribute 'default'
```

Consequences:

- Import order is load-bearing.
- A second `Database` made later (another settings object, a test, a CLI with other settings) is silently ignored by
  every exposed function.
- Conftests have to reuse `Database.default` (`conftest.py:174-182`, and the "two conftests that each make a `Database`
  break each other" note).

**Fix:** make the decorators resolve `Database.default` **at call time**, for example a module-level
`read_transaction(func)` that looks up `Database.default` inside its wrapper. The call sites stay the same, and the
import-order coupling goes away.

Related cleanup in `database.py`:

- `_instances` (151), `_initialised` (152), the `instance_identifier` parameter (161), `with_database` (264-275) and
  `initialise_default_database` (277-281) are unused. `with_database` would raise `KeyError`, because `_instances` is
  never filled.
- `Database(settings=None)` returns a half-made object (162-163).
- `_check_driver` reads the driver's private `_closed`, and raises `AttributeError` if `_initialise_driver` was never
  called. Meanwhile 17 call sites in `src/` repeat `if not hasattr(database, "driver"): await
  database._initialise_driver()`. One public `await database.ensure_driver()` should replace all of them.
- `list_items` and `search` (`exposed_functions.py:168-174`, `205-211`) catch `TransientError` timeouts by hand. The
  `translating_timeouts` wrapper that `read_transaction` already applies (the functions carry `timeout_from_setting`)
  does the same job. Delete the inline copies.

## 6. Two backends, one codebase copied: read, measured

`docs/neo4j-implementation.md:58` records the decision to copy, not share. The drift is now measurable. I normalised
the names and diffed:

| File | Lines | Lines that differ |
|---|---|---|
| `build_create_query.py` | 795 | 5 |
| `validate_write.py` | 289 | 6 |
| `build_update_query.py` | 172 | 12 |
| `delete_node.py`, `read_incoming.py`, `review.py`, `users.py`, `lookup.py`, `build_tree.py`, `from_database.py`, `visibility.py` | 1,042 | 0 |

The tests are copied too (about 20k lines each). Every fix in this report except 1 and 3 has to be made twice.

**Recommendation:** extract the identical files (about 2,300 lines) into a shared package now, while they are still
identical. Leave the dialect files (list, search, initialise, bulk, migration backend) per backend. The contract tests
in `pangloss-neo4j/tests/test_contract.py` are the safety net for this. If that is not wanted yet, at least add a CI
check that fails when the identical files diverge.

## 7. Cypher that is pasted, and has drifted: read

`build_list_query.py` contains the same four-line visibility filter 8 times, with different variable names. The lines
are pasted unindented (lines 56-59, 79-82, 89-92, 235-238, 293-296, 303-306):

```
WHERE NOT coalesce(CASE WHEN n:Entity THEN n.deleted ELSE coalesce(n_head, n).deleted END, false)
AND (n:Entity OR $see_unpublished OR coalesce(coalesce(n_head, n).published, true))
AND ($published IS NULL OR ...)
AND ($review_status IS NULL OR ...)
```

`build_read_query.py:35-36` and `build_search_query.py` have more copies. `docs/review.md` lists these places by hand.
That list is the thing a helper `visible(node, head) -> str` would remove.

Drift that is already there: the creation record is joined with `MATCH` in the plain list
(`build_list_query.py:315`) and the deep list (`:111`), but with `OPTIONAL MATCH` in the text-search list (`:252`). A
node whose head has no `PGCreation` (bulk data, a partial migration) is therefore counted in `total` but missing from
the plain and deep pages. In the text search it appears, with `created_by: null`. Pick one behaviour (probably
`OPTIONAL`) and test it.

Smaller items in the builders:

- `build_create_query.py:699-709`: both branches set `id_condition = "true"`. Remove the variable and the
  `WHERE true AND`.
- `build_create_query.py:214-216`: `to_query_string` means to raise a clear error when `return_identifier` is unset.
  But the attribute is never initialised in `__init__`, so you get an `AttributeError` instead. Set it to `None` in
  `__init__`.
- The inline-entity `CREATE ... -[:created_by]->(user)` (`build_create_query.py:646`) depends on a `user` variable
  matched elsewhere, by the head create or update query. Pass the identifier in, as is done for every other variable.

## 8. Dead code and leftovers: confirmed by grep and vulture

- `pangloss_core/__init__.py`: the `hello()` template stub.
- `build_create_query.py:41` `compress` and `:68` `QuerySubstring`: unused here and in the Neo4j copy. There is also the
  commented `# "data": compressed_data` at `:767`.
- `databases/memgraph/indexes.py` (empty) and the `pangloss_memgraph/tooling/` package (empty `__init__`): unused.
- `migrations/operations.py:1943`: `label, properties` are computed in `remove_index` and never used (F841). The same
  function compares the text index name without `ident()`, while `add_index` uses it (`:1932` and `:1952`). The two are
  equivalent today, but the inconsistency invites a mismatch later.
- `bulk.py:57-60`: the comment "What an empty database may hold…" sits above `QUIET_DURING_LOAD_MS`, not above
  `ALLOWED_LABELS`. `bulk.py` also imports the private `_session` from `migration_backend`. Make it public.
- `tests/test_experiment.py`: a leftover sanity test (`CREATE (node:Node {name: 'Tony'})`). Delete it.
- `test_create.py:271` and `:317`: the comment `# type of concerned person is deliberately wrong!` is no longer true
  of the code below it.
- `database.py:120-127`: unformatted. This is the only memgraph source file that `ruff format` would change.

## 9. Test fixtures: read

`packages/pangloss-memgraph/tests/conftest.py`:

- **Clearing happens only on teardown** (`clear_database`, line 112). A run that is killed, or the add-on live tests
  sharing :7687, leaves data behind. The first test of the next run then starts dirty, and every `count_nodes(...) ==
  1` assertion depends on the order the tests run in. Clear on setup **and** teardown.
- **The fallback container mounts `/tmp/mg_data`** (line 61). Data persists between runs of a container that is meant
  to be throwaway. Drop the volume.
- **`ensure_user` is autouse** (line 121). Every test, including the pure unit tests (`test_build_tree.py`,
  `test_connection_log.py`, `test_shipped_migrations.py`), needs Memgraph and joins the `db` xdist group. That makes
  them slower and stops them running in parallel. Move it into `clear_database`, or mark the DB tests explicitly.
- `DEFAULT_INTERFACE_LANGUAGES` (line 162) is a typo for `DEFAULT_INTERFACE_LANGUAGE`. It declares a new field instead
  of setting the real one.
- `test_create.py:86` `test_document_write_with_different_types` writes without `clear_database`.

## 10. Tests that check less than their names say: confirmed by AST scan, then read

memgraph:

- `test_create.py:420` `test_massive_write` has **no assertion**. It writes 200 entities and one `Action` that refers
  to all of them, and checks nothing. Assert 200 forward and 200 reverse edges. At 3.6 s it is also the 4th slowest
  test, so it should earn its time.
- `test_create.py:338` `test_write_edge_properties` asserts only `p_created.id`. It is a superseded version of
  `test_edge_properties_are_written_to_both_edges` (`:1706`). Delete it.
- Several early tests in `test_create.py` (e.g. `:260-335`, `:362-415`) end with `assert data["p"]; assert
  data["st"]`. The real check is that `records[0]` exists, which fails with an `IndexError` rather than an assertion
  message. Write `assert len(records) == 1`.
- `test_edit_cycle.py` and `test_sdk_contract.py` gather failures across all kitchen-sink models with `except
  Exception`. That is good for coverage, but an `AttributeError` from a test bug is reported the same way as a real
  round-trip failure. Catch `(AssertionError, PanglossError, ValidationError)` and let the rest raise.
- Not covered by any memgraph test (grep): the `write_with_retries` path that retries after a commit-time unique
  violation from a concurrent writer. Two concurrent creates of the same inline entity URL would exercise it.

Other packages (`/tmp/test_audit.py`-style scan; most hits are deliberate "does not raise" tests, the rest are listed
here):

- `pangloss-models/tests/generated_models/test_create_db_model.py:1722` `test_recursive_type`: its docstring says
  "for debugging a problem", and it has no assertion. Assert the resulting field types, or delete it.
- `pangloss-api/tests/test_migration_check.py:110` checks the warning for `"warn"`, but not that `"off"` emits none.
  Wrap `start("off")` in `warnings.catch_warnings(); simplefilter("error")`.
- `pangloss-core/tests/test_logs.py::test_configure_from_settings` sets `LOG_FORMAT = "json"`, but asserts only the
  level.

Coverage of `pangloss_memgraph` and `pangloss_core`: see [Appendix: coverage](#appendix-coverage).

## 11. Packaging and tooling: confirmed

- `pangloss-memgraph/pyproject.toml:15` and `pangloss-neo4j` list `pytest-asyncio` as a **runtime** dependency. It is
  already in the dev group.
- `ruff format --check` would reformat 18 files: `pangloss-memgraph` `database.py`, `tests/test_api_models.py` and
  `tests/test_search_wrappers_live.py`, plus files in the api, calendar, interface, models, neo4j, testing and zotero
  packages. Add `ruff format --check` and `ruff check --select F,B` to `run_tests.sh` or CI.
- In the root `pyproject.toml`, `[tool.coverage] source_pkgs = ["pangloss_models"]` with `fail_under = 94` means the
  coverage gate measures one package. A `--source` on the command line does not override it (my first coverage run
  reported only `pangloss_models`). Either widen it or document that the gate is for models only.
- `ty` passes on core and memgraph, but `build_*_query.py` and `exposed_functions.py` turn off 16 rules
  (root `pyproject.toml`), so the type check says little about them.
- Ruff bugbear's B023 hits in `migrations/runner.py:177-213` (closures over loop variables) are **not** bugs: each
  closure is awaited within its iteration. `window_work` binds `after` as a default and the others do not; making them
  consistent would silence the warning.

## Suggested order

1. Items 1, 2, 3 and the `test_lock` rewrite (4): small, and each has a test that fails today.
2. Item 9 (clear on setup, drop the volume, fix the typo) and the deletions in 8 and 10.
3. Item 5 (call-time binding, `ensure_driver`), then item 7 (`visible()` helper, one creation-join behaviour).
4. Item 6, once the above has been applied to both backends.

## Appendix: coverage

Run serially with a dedicated rcfile (`source_pkgs = pangloss_memgraph, pangloss_core`): 553 passed, **93% line
coverage** (3,200 statements, 225 missed). 23 files are fully covered. The uncovered lines worth acting on:

| Where | Lines | What it means |
|---|---|---|
| `exposed_functions.py` | 481, 483 | The `write_with_retries` retry and its `PanglossConflictError` never run. A concurrency path with no test (see 10). |
| `exposed_functions.py` | 171, 208 | The inline timeout handlers are unreachable, because `translating_timeouts` catches the error first. This confirms they can be deleted (see 5). |
| `exposed_functions.py` | 461, 563, 573 | The "Nothing was written/updated" guards. The validators run first, so these may be unreachable; if so, say so in a comment. |
| `database.py` | 139, 163, 182, 270-281 | The non-timeout re-raise in `translating_timeouts` (139) has no test; the rest is the dead code from 5. |
| `cli.py` | 115-162, 177-181 | The `bulk-load` / `bulk-recover` bodies. `test_bulk_load_cli.py` runs them in a subprocess, so coverage cannot see them. They are tested, just not measured. |
| `backend.py` (memgraph) | 56-64 | `user_exists` is not tested in this package (the add-on live tests use it). |
| `pangloss_core/backend.py` | all | Not tested in core. It is exercised from `pangloss-neo4j/tests/test_contract.py` and the add-ons. |
| `pangloss_core/settings.py` | 18-33 | `normalise_cors_origins` is not tested in core. It is tested in `pangloss-api/tests/test_cors.py`. |
| `migrations/operations.py` | 54 lines | Mostly error branches (`PanglossMigrationError` for an unknown model or name) and the text-index branches of `add_index`/`remove_index`. |
| `build_create_query.py` | 43-48, 70 | `compress` and `QuerySubstring`: dead (see 8). |
