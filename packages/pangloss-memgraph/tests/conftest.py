import typing
from collections.abc import Generator

import docker
import neo4j
import pangloss_core.settings as core_settings
import pytest
import pytest_asyncio
from pangloss_core import BaseSettings
from pangloss_memgraph.databases.memgraph.database import Database, install
from pangloss_memgraph.databases.memgraph.initialise_database import (
    initialise_database,
)
from pangloss_memgraph import MemgraphDatabaseSettings
from pangloss_models import ModelRegistry
from pangloss_testing.backends import backend_named, database_group
from pangloss_users import current_request_username
from pydantic import AnyHttpUrl
from pytest import fixture, mark
from tenacity import retry, stop_after_delay, wait_fixed

from .helpers import BULK_URI

pytestmark = pytest.mark.asyncio(loop_scope="session")

# (this process's test database: 7687, or a worker's own, `pangloss_testing.backends`)
BACKEND = backend_named("memgraph")
MEMGRAPH_URI = BACKEND.uri
MEMGRAPH_AUTH = BACKEND.auth
MEMGRAPH_DATABASE = BACKEND.database


@fixture(scope="function", autouse=True)
def reset_model_registry():
    ModelRegistry._reset()
    yield


@fixture(scope="session", autouse=True)
def assure_memgraph_container():
    try:
        check_memgraph()
    except Exception:
        client = docker.from_env()
        container = client.containers.run(
            BACKEND.image,
            name=BACKEND.container_name,
            detach=True,
            remove=True,
            ports={"7687/tcp": BACKEND.port},
            environment=BACKEND.container_environment,
            command=BACKEND.container_command,
        )

        try:
            wait_for_memgraph()
            yield container
        finally:
            container.stop()
            client.close()
    else:
        # An existing Memgraph instance is already available.
        yield


def check_memgraph():
    driver = neo4j.GraphDatabase.driver(
        MEMGRAPH_URI,
        auth=MEMGRAPH_AUTH,
    )
    try:
        driver.verify_connectivity()
    finally:
        driver.close()


@retry(stop=stop_after_delay(30), wait=wait_fixed(0.5))
def wait_for_memgraph():
    check_memgraph()


@fixture(scope="session")
def db_driver(
    assure_memgraph_container,
) -> Generator[neo4j.Driver]:
    driver = neo4j.GraphDatabase.driver(
        MEMGRAPH_URI,
        auth=MEMGRAPH_AUTH,
    )

    try:
        driver.verify_connectivity()
        yield driver
    finally:
        driver.close()


def make_user(db_driver) -> None:
    db_driver.execute_query(
        "MERGE (user:PGUser {username: $username})",
        parameters_={"username": current_request_username.get()},
        database=MEMGRAPH_DATABASE,
    )


@fixture(scope="function")
def clear_database(db_driver):
    """An empty database (but for the user of the tests) before the test, and after it. (Before as well: a run that was
    stopped, or tests that do not clear, leave things behind)"""
    db_driver.execute_query("MATCH (n) DETACH DELETE n", database=MEMGRAPH_DATABASE)
    make_user(db_driver)
    yield
    db_driver.execute_query("MATCH (n) DETACH DELETE n", database=MEMGRAPH_DATABASE)


@fixture(scope="function", autouse=True)
def ensure_user(db_driver):
    make_user(db_driver)
    yield


def pytest_itemcollected(item):
    item.add_marker(mark.database)
    item.add_marker(mark.xdist_group(database_group(item)))


@pytest_asyncio.fixture(
    scope="session",
    loop_scope="session",
    autouse=True,
)
async def initialise_settings(
    event_loop_policy,
    db_driver,
):
    """Initialise application settings and the Memgraph database (with its indexes,
    constraints and so on)."""

    class Settings(BaseSettings[MemgraphDatabaseSettings]):
        PROJECT_NAME: str = "Test"
        BACKEND_CORS_ORIGINS: list[typing.Any] = []
        INSTALLED_APPS: list[str] = []
        STORAGE: str | None = "pangloss_memgraph:storage"
        DATABASE: MemgraphDatabaseSettings = MemgraphDatabaseSettings(
            DB_URL=MEMGRAPH_URI,
            DB_USERNAME="test",
            DB_PASSWORD="test",
            DATABASE_NAME=MEMGRAPH_DATABASE,
        )
        INTERFACE_LANGUAGES: list[str] = []
        DEFAULT_INTERFACE_LANGUAGE: str = "en"
        AUTHJWT_SECRET_KEY: str = "a secret for the tests, of a decent length"
        ENTITY_BASE_URL: AnyHttpUrl = AnyHttpUrl("http://test.com/")

    settings = Settings()
    database = install(Database(settings=settings))
    await initialise_database(database)
    try:
        yield settings, database
    finally:
        await database.close()


@pytest.fixture(scope="module", autouse=True)
def use_test_settings(initialise_settings):
    """The settings and the database of these tests are the process's while a module of them runs (both are the
    process's, and the tests of another package that ran before in the same process made their own)"""
    settings, database = initialise_settings
    core_settings.configure(settings)
    install(database)


def bulk_reachable() -> None:
    driver = neo4j.GraphDatabase.driver(BULK_URI, auth=("test", "test"))
    try:
        driver.verify_connectivity()
    finally:
        driver.close()


@pytest.fixture(scope="session")
def bulk_memgraph():
    try:
        bulk_reachable()
    except Exception:
        client = docker.from_env()
        container = client.containers.run(
            "memgraph/memgraph-mage:3.14.0",
            detach=True,
            remove=True,
            ports={"7687/tcp": 7691},
            environment={"MEMGRAPH_USER": "test", "MEMGRAPH_PASSWORD": "test"},
            command=[
                "--log-level=WARNING",
                "--also-log-to-stderr=true",
                "--storage-properties-on-edges=true",
            ],
        )
        try:
            retry(stop=stop_after_delay(60), wait=wait_fixed(0.5))(bulk_reachable)()
            yield container
        finally:
            container.stop()
            client.close()
    else:
        yield
