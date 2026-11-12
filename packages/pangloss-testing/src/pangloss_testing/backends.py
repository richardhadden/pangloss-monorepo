"""The backends a live test may run on, and which one is under test (`PANGLOSS_TEST_BACKEND`)

A run may give each xdist worker a database of its own (`PANGLOSS_TEST_DATABASE_PER_WORKER=1`, as `run_tests.sh`
does): worker `gw0` has the usual one (7687, 7693), worker `gwN` the one on `SHARD_PORTS[name] + N`, started in Docker
if it is not there. Without it every worker has the usual database, and the tests that use it run one after the
other on one worker (`database_group`)."""

import dataclasses
import importlib
import os
from typing import Any


@dataclasses.dataclass(frozen=True)
class BackendUnderTest:
    name: str
    storage: str
    database_module: str
    settings_class: str
    uri: str
    username: str
    password: str
    database: str
    image: str
    port: int
    container_environment: dict[str, str]
    container_command: list[str]
    # (more of the environment of a shard's container: Docker's memory is shared by them all)
    shard_environment: dict[str, str] = dataclasses.field(default_factory=dict)

    @property
    def auth(self) -> tuple[str, str]:
        return (self.username, self.password)

    def on_shard(self, shard: int) -> "BackendUnderTest":
        """The same backend on the database of shard `shard` (0 is the usual one)"""
        if shard == 0:
            return self
        port = SHARD_PORTS[self.name] + shard
        return dataclasses.replace(
            self,
            uri=f"bolt://localhost:{port}",
            port=port,
            container_environment=self.container_environment | self.shard_environment,
        )

    @property
    def container_name(self) -> str:
        """(the name of a container the tests start: `docker rm -f` it if a run was killed and left it)"""
        return f"pangloss-test-{self.name}-{self.port}"

    def module(self, name: str) -> Any:
        return importlib.import_module(f"{self.database_module}.{name}")

    @property
    def settings_type(self) -> Any:
        return getattr(self.module("settings"), self.settings_class)


BACKENDS = {
    "memgraph": BackendUnderTest(
        name="memgraph",
        storage="pangloss_memgraph:storage",
        database_module="pangloss_memgraph.databases.memgraph",
        settings_class="MemgraphDatabaseSettings",
        uri="bolt://localhost:7687",
        username="test",
        password="test",
        database="memgraph",
        image="memgraph/memgraph-mage:3.14.0",
        port=7687,
        container_environment={"MEMGRAPH_USER": "test", "MEMGRAPH_PASSWORD": "test"},
        container_command=[
            "--log-level=WARNING",
            "--also-log-to-stderr=true",
            "--storage-properties-on-edges=true",
            "--experimental-enabled=commit-lock-narrowing",
        ],
    ),
    "neo4j": BackendUnderTest(
        name="neo4j",
        storage="pangloss_neo4j:storage",
        database_module="pangloss_neo4j.databases.neo4j",
        settings_class="Neo4jDatabaseSettings",
        uri="bolt://localhost:7693",
        username="neo4j",
        password="test-password",
        database="neo4j",
        image="neo4j:2026.10.1",
        port=7693,
        container_environment={"NEO4J_AUTH": "neo4j/test-password"},
        container_command=[],
        shard_environment={
            "NEO4J_server_memory_heap_initial__size": "512m",
            "NEO4J_server_memory_heap_max__size": "1g",
            "NEO4J_server_memory_pagecache_size": "256m",
        },
    ),
}


# The ports of the other shards' databases are these plus the number of the shard (7711, 7712, ... for Memgraph):
# clear of the ports the docs give (7687-7699)
SHARD_PORTS = {"memgraph": 7710, "neo4j": 7720}


def database_per_worker() -> bool:
    return os.environ.get("PANGLOSS_TEST_DATABASE_PER_WORKER") == "1"


def shard() -> int:
    """The shard of this process: the number of its xdist worker when each has a database, else 0"""
    if not database_per_worker():
        return 0
    worker = os.environ.get("PYTEST_XDIST_WORKER", "gw0")
    return int(worker.removeprefix("gw"))


def backend_named(name: str) -> BackendUnderTest:
    """A backend on this process's database"""
    return BACKENDS[name].on_shard(shard())


def under_test() -> BackendUnderTest:
    name = os.environ.get("PANGLOSS_TEST_BACKEND", "memgraph")
    if name not in BACKENDS:
        raise ValueError(
            f"PANGLOSS_TEST_BACKEND={name!r} is not a backend: one of {', '.join(BACKENDS)}"
        )
    return backend_named(name)


def database_group(item) -> str:
    """The xdist group of a test that uses the database: one group for all of them when there is one database, so
    they run one after the other; when each worker has its own, one for each module (its module-scoped fixtures are
    made once), or what the module names as `DATABASE_GROUP` (modules that share something else, such as a second
    database on a fixed port, run on one worker)"""
    if not database_per_worker():
        return "db"
    module = getattr(item, "module", None)
    named = getattr(module, "DATABASE_GROUP", None)
    return named or item.nodeid.split("::")[0]
