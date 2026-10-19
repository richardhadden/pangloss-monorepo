Testing
=======

`./run_tests.sh` runs all tests so far (`uv run pytest --dist=loadgroup -n auto`), across every package.

The Memgraph tests need a database. If none is reachable on `bolt://localhost:7687` (user/password `test`/`test`), the test fixtures start a dockerised `memgraph/memgraph-mage` instance themselves, so Docker must be running. An already-running Memgraph is reused instead.
