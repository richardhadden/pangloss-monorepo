"""The tests that every backend passes, written once (`docs/database-abstraction-plan.md`, phase 9).

They run on the backend that `PANGLOSS_TEST_BACKEND` names (Memgraph if it names none): `run_tests.sh` runs them on each.
They go through the models where they can. What they look at underneath is through `helpers` (`run`, `labels_of`, ...):
Cypher, so a test that uses the test database's driver needs a backend that has the `cypher` capability, and is skipped
on one that has not. What a backend does that the others do not (DDL, bulk modes, snapshots, query plans) is tested in the
backend's own `tests/`."""
