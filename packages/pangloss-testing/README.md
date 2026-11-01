# pangloss-testing

The tests that every backend passes (the conformance suite), and fixtures for the tests that need a live database, on whichever
backend is under test. See `docs/backend-neutral-addons.md`.

```python
# tests/live/conftest.py of the package
from pangloss_testing.live import *  # noqa: F403  (the fixtures)
```

`PANGLOSS_TEST_BACKEND` chooses the backend: `memgraph` (the default; the test Memgraph on `localhost:7687`) or `neo4j` (a
Neo4j on `localhost:7693`). Either is started in Docker if it is not there, and the tests are skipped if Docker is not running.
`./run_tests.sh` runs the live tests of the add-on packages once for each.

Fixtures: `db_driver` (a driver), `clear_database` (empties the database after the test), `ensure_user`, `initialise_settings`
(settings, `Database`, and the indexes and constraints; once for the session), `reset_model_registry`. `run(db_driver, cypher, **params)`
runs a query and gives the records as dicts.

## The conformance suite

`src/pangloss_testing/conformance/` has the tests of the models on a real database that every backend passes: create, read,
update, delete, list, search, autocomplete, inline entities, versions, users, review, history, the API and the SDK over it,
and the migrations through the CLI functions. They were the tests of `pangloss-memgraph` and `pangloss-neo4j`, each a copy
of the other; now there is one copy. `./run_tests.sh` runs them on Memgraph (in the run of the packages) and on Neo4j
(`PANGLOSS_TEST_BACKEND=neo4j uv run pytest packages/pangloss-testing/src/pangloss_testing/conformance`).

- What they need of the backend's own modules they import from `pangloss_testing.under_test`, which is the database module
  of the backend under test (`from pangloss_testing.under_test.database import current`).
- What they look at underneath is in `conformance/helpers.py`: `run` (Cypher written as for Memgraph, translated for Neo4j's
  flat `meta`), `labels_of`, `count_nodes`, `index_labels`. A test that uses the driver (`db_driver`) is marked
  `requires("cypher")`, and is skipped on a backend without that capability.
- The database is cleared before and after each test that asks for it (`clear_database`).
- Each test of writes at the same time says in its docstring that it was seen to fail with what it tests taken out.

What a backend does that the others do not (its DDL, bulk modes, snapshots, query plans, its command line) is tested in
its own `tests/`, which `NOT_PORTED.md` there lists.
