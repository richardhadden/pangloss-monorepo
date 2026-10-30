"""The backends a live test may run on, and which one is under test (`PANGLOSS_TEST_BACKEND`)"""

import dataclasses
import importlib
import os
from typing import Any


@dataclasses.dataclass(frozen=True)
class BackendUnderTest:
    name: str
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

    @property
    def auth(self) -> tuple[str, str]:
        return (self.username, self.password)

    def module(self, name: str) -> Any:
        return importlib.import_module(f"{self.database_module}.{name}")

    @property
    def settings_type(self) -> Any:
        return getattr(self.module("settings"), self.settings_class)


BACKENDS = {
    "memgraph": BackendUnderTest(
        name="memgraph",
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
    ),
}


def under_test() -> BackendUnderTest:
    name = os.environ.get("PANGLOSS_TEST_BACKEND", "memgraph")
    if name not in BACKENDS:
        raise ValueError(
            f"PANGLOSS_TEST_BACKEND={name!r} is not a backend: one of {', '.join(BACKENDS)}"
        )
    return BACKENDS[name]
