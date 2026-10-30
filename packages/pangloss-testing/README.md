# pangloss-testing

Fixtures for the tests of an add-on package (typology, calendar, zotero) that need a live database, on whichever backend is
under test. See `docs/backend-neutral-addons.md`.

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
