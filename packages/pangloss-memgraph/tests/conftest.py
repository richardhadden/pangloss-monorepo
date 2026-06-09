import typing
from typing import Generator

import docker
import neo4j
from pangloss_core.settings import BaseSettings, DatabaseSettings
from pangloss_memgraph.databases.memgraph.database import Database
from pangloss_memgraph.databases.memgraph.settings import MemgraphDatabaseSettings
from pangloss_models.model_registry import ModelRegistry
from pydantic import AnyHttpUrl, AnyUrl
from pytest import fixture, mark
from tenacity import retry, stop_after_delay, wait_fixed


@fixture(scope="function", autouse=True)
def reset_model_registry():
    ModelRegistry._reset()
    yield


@fixture(scope="function")
def clear_database(db_driver):
    yield
    db_driver.execute_query("MATCH (n) DETACH DELETE n", database="memgraph")


@fixture(scope="session", autouse=True)
def assure_memgraph_container():
    memgraph_already_running = False
    try:
        check_memgraph()
        memgraph_already_running = True
    except Exception:
        pass

    if memgraph_already_running:
        yield
    else:
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


def check_memgraph():
    driver = neo4j.GraphDatabase.driver(
        "bolt://localhost:7687",
        auth=("test", "test"),
    )
    driver.verify_connectivity()
    driver.close()


@retry(stop=stop_after_delay(30), wait=wait_fixed(0.5))
def wait_for_memgraph():

    driver = neo4j.GraphDatabase.driver(
        "bolt://localhost:7687",
        auth=("test", "test"),
    )
    driver.verify_connectivity()
    driver.close()


@fixture(scope="module")
def db_driver() -> Generator[neo4j.Driver, None, None]:
    driver = neo4j.GraphDatabase.driver(
        "bolt://localhost:7687",
        auth=("test", "test"),
    )
    driver.verify_connectivity()
    yield driver
    driver.close()


def pytest_itemcollected(item):
    item.add_marker(mark.xdist_group("db"))


@fixture(scope="module", autouse=True)
def initialise_settings():
    """Creates a Settings instance for testing. Use memgraph database (i.e. this module)"""

    class Settings(BaseSettings[MemgraphDatabaseSettings]):
        PROJECT_NAME: str = "Test"
        BACKEND_CORS_ORIGINS: list[typing.Any] = []
        INSTALLED_APPS: list[str] = []
        DATABASE_MODULE: str = "pangloss_memgraph.databases.memgraph"
        DATABASE: MemgraphDatabaseSettings = MemgraphDatabaseSettings(
            DB_URL="bolt://localhost:7687",
            DB_USERNAME="test",
            DB_PASSWORD="test",
            DATABASE_NAME="memgraph",
        )
        INTERFACE_LANGUAGES: list[str] = []
        DEFAULT_INTERFACE_LANGUAGE: str = "en"
        AUTHJWT_SECRET_KEY: str = "asdf"
        INTERFACE_LANGUAGES: list[str] = []
        ENTITY_BASE_URL: AnyHttpUrl = AnyHttpUrl("http://test.com/")

    settings = Settings()
    Database(settings=settings)

    yield
