# Backend-neutral add-on packages 🚧

Status: plan written 2026-10-30; steps are checked off as they are built (§5).

The add-on packages should run on any backend (`pangloss-memgraph`, `pangloss-neo4j`, a later one) chosen by `DATABASE_MODULE`,
without naming one. This is what it takes.

## 1. What was found

| Package | Hard-wired to Memgraph? | Detail |
|---|---|---|
| `pangloss-history` | No | Records go to SQLite; no graph access. |
| `pangloss-zotero` | Tests only | The source goes through the models. `tests/conftest.py` builds a Memgraph connection by hand; `pyproject.toml` lists `pangloss-memgraph` as a dependency. |
| `pangloss-review`, `pangloss-users` | No | They call `{DATABASE_MODULE}.exposed_functions`: the pattern to copy. |
| `pangloss-typology` | Yes | `graph.py` holds all its Cypher; it imports `Database`, `Transaction`, `unpublished_visible`; the CLI imports `user_exists`. |
| `pangloss-calendar` | Yes | `graph.py` holds all its Cypher; it imports `Database`, `Transaction`, `timeout_from_setting`, `unpublished_visible`, and catches the driver's `TransientError` to tell a timeout. |

Most of the Cypher is standard and runs on both (`MERGE`, `UNWIND`, `*0..` paths, `CALL {… UNION …}`, `properties()`). The
calendar's `Date` fields are scalars and lists, so the Neo4j backend's flattening of maps does not touch them.

What differs, or must be tested rather than assumed:

1. The imports.
2. **Timeouts:** Memgraph raises `TransientError`, Neo4j a `ClientError` with a `TransactionTimedOut…` code.
3. **The hierarchy lock** (typology `lock_hierarchy`): uses `ORDER BY id(l)` and Memgraph's write conflict; on Neo4j the lock node, made by a plain `MERGE`, could be made twice by concurrent writers.
4. To test: `DELETE e RETURN count(e)` (calendar `detach`); the order of `labels(e)` (typology `entities_of`); `properties(t)` through the Neo4j decoding wrapper.
5. The live tests (typology, calendar, zotero) build a Memgraph connection by hand.

## 2. The abstractions

No query builder or dialect objects: the differences are too few. Five things:

1. **A loader in `pangloss-core`**, `pangloss_core.backend`: `current()` imports `settings.DATABASE_MODULE` and returns a `Backend` that gives `Database`, `Transaction`, `timeout_from_setting`, `unpublished_visible`, `user_exists` and `lock`. Replaces every `from pangloss_memgraph…` in the add-ons.
2. **Timeout translation in the backend's transaction decorators:** `read_transaction` raises `PanglossSearchTimeoutError`; the add-on catches no driver exception.
3. **`lock(tx, key)`**, supplied by each backend: Memgraph by writing to a node (a write conflict, retried by the driver); Neo4j by taking a node lock. The lock node is made by the backend, with a unique constraint on its key.
4. **A conformance test** (extends `test_contract.py`): every name the add-ons take from the backend exists on both with the same signature.
5. **Backend-neutral test fixtures:** one fixture set, chosen by an environment variable (`PANGLOSS_TEST_BACKEND`, default `memgraph`), giving settings, `Database` and an empty database. The live tests of the add-ons use it.

Dependencies: an add-on does not require a backend at install time; `pangloss-memgraph` moves to its dev group.

## 3. Decisions (recommended, agreed 2026-10-30)

- The loader lives in `pangloss-core`.
- Add-on dependencies on a backend move to dev groups.
- The typology lock moves to the backend.

## 4. Order of work

1. The loader and the five names.
2. Timeout translation in the backends.
3. `lock(tx, key)` in both backends; typology's lock on it.
4. Replace the imports in typology and calendar; the shared fixtures; move their live tests (and zotero's) onto them.
5. Fix what fails on the second backend.

## 5. Progress

- [x] 1. Loader: `pangloss_core.backend`, a `backend.py` in each backend, typology and calendar on it, their dependency on `pangloss-memgraph` moved to a dev group, a contract test (2026-10-30)
- [x] 2. Timeout translation: a read that declares `timeout_from_setting` raises `PanglossSearchTimeoutError` from inside the transaction in both backends (`translating_timeouts`; inside, so that Memgraph's driver does not retry it for 10 s); `is_timeout` lives in each `database.py`. The handlers in `exposed_functions` are now redundant and left alone
- [x] 3. `lock(tx, key)` and `ensure_lock(key)` in both backends (`:PGLock {key}`, unique, shipped migration `0004`); typology's hierarchy lock is on them. `ensure_lock` must be awaited before the transaction opens: on Memgraph a transaction that creates the node is refused at its commit when two do at once (not retried), and a transaction does not see a node committed after it began; so the node cannot be made inside `lock` (the plan said `lock(tx, key)` alone)
- [x] 4. (part) `pangloss-testing` (fixtures chosen by `PANGLOSS_TEST_BACKEND`); live tests moved to `tests/live/` of typology, calendar, dates and zotero, green on Memgraph; `run_tests.sh` runs them on Neo4j too
- [ ] 5. Second backend green
