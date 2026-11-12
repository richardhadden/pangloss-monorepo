"""Which database a worker of a test run has (`pangloss_testing.backends`)"""

from types import SimpleNamespace

from pangloss_testing.backends import BACKENDS, backend_named, database_group, shard


def test_without_a_database_per_worker_every_worker_has_the_usual_one(monkeypatch):
    monkeypatch.delenv("PANGLOSS_TEST_DATABASE_PER_WORKER", raising=False)
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw3")
    assert shard() == 0
    assert backend_named("memgraph") == BACKENDS["memgraph"]
    assert database_group(SimpleNamespace(nodeid="a/test_x.py::test_y")) == "db"


def test_with_a_database_per_worker_each_has_its_own_port(monkeypatch):
    monkeypatch.setenv("PANGLOSS_TEST_DATABASE_PER_WORKER", "1")
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw0")
    assert backend_named("memgraph").uri == "bolt://localhost:7687"

    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw2")
    memgraph, neo4j = backend_named("memgraph"), backend_named("neo4j")
    assert (memgraph.uri, memgraph.port) == ("bolt://localhost:7712", 7712)
    assert (neo4j.uri, neo4j.port) == ("bolt://localhost:7722", 7722)
    assert memgraph.container_name == "pangloss-test-memgraph-7712"
    # (a shard's Neo4j is given less memory: Docker's is shared by them all)
    assert neo4j.container_environment["NEO4J_AUTH"] == "neo4j/test-password"
    assert "NEO4J_server_memory_heap_max__size" in neo4j.container_environment
    assert (
        "NEO4J_server_memory_heap_max__size"
        not in BACKENDS["neo4j"].container_environment
    )


def test_with_a_database_per_worker_the_tests_are_grouped_by_module_or_as_the_module_says(
    monkeypatch,
):
    monkeypatch.setenv("PANGLOSS_TEST_DATABASE_PER_WORKER", "1")
    plain = SimpleNamespace(nodeid="a/test_x.py::test_y", module=SimpleNamespace())
    named = SimpleNamespace(
        nodeid="a/test_z.py::test_y", module=SimpleNamespace(DATABASE_GROUP="bulk")
    )
    assert database_group(plain) == "a/test_x.py"
    assert database_group(named) == "bulk"
