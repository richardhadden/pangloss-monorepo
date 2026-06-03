from typing import Generator

import docker
import neo4j
from pangloss_models.model_registry import ModelRegistry
from pytest import fixture
from tenacity import retry, stop_after_delay, wait_fixed


@fixture(scope="function", autouse=True)
def reset_model_registry():

    ModelRegistry._reset()
    yield


@fixture(scope="session", autouse=True)
def memgraph_container():
    client = docker.from_env()
    container = client.containers.run(
        "memgraph/memgraph-mage",
        detach=True,
        remove=True,
        ports={
            "7687/tcp": 7687,
            "7444/tcp": 7444,
        },
        environment={
            "MEMGRAPH_USER": "test",
            "MEMGRAPH_PASSWORD": "test",
        },
        command=[
            "--log-level=WARNING",
            "--also-log-to-stderr=true",
            "--storage-properties-on-edges=true",
        ],
        volumes={
            "/tmp/mg_data": {"bind": "/var/lib/memgraph", "mode": "rw"},
        },
    )

    wait_for_memgraph()

    yield container

    container.stop()


@retry(stop=stop_after_delay(30), wait=wait_fixed(0.5))
def wait_for_memgraph():

    driver = neo4j.GraphDatabase.driver(
        "bolt://localhost:7687",
        auth=("test", "test"),
    )
    driver.verify_connectivity()
    driver.close()


@fixture
def db_driver() -> Generator[neo4j.Driver, None, None]:
    driver = neo4j.GraphDatabase.driver(
        "bolt://localhost:7687",
        auth=("test", "test"),
    )
    driver.verify_connectivity()
    yield driver
    driver.close()
