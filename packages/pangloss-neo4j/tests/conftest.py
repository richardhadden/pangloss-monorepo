import typing
from collections.abc import Callable, Generator

import docker
import neo4j
import pytest
import pytest_asyncio
from pangloss_core.settings import BaseSettings
from pangloss_models.model_registry import ModelRegistry
from pangloss_neo4j.databases.neo4j.database import Database
from pangloss_neo4j.databases.neo4j.initialise_database import (
    initialise_database,
)
from pangloss_neo4j.databases.neo4j.settings import Neo4jDatabaseSettings
from pangloss_users import current_request_username
from pydantic import AnyHttpUrl
from pytest import fixture, mark
from tenacity import retry, stop_after_delay, wait_fixed

from .helpers import BULK_URI

pytestmark = pytest.mark.asyncio(loop_scope="session")

# (its own port: the Neo4j tests use 7687, the demo 7688, and the explorations 7692)
NEO4J_URI = "bolt://localhost:7693"
NEO4J_AUTH = ("neo4j", "test-password")
NEO4J_DATABASE = "neo4j"
NEO4J_IMAGE = "neo4j:2026.10.1"


@fixture(scope="function", autouse=True)
def reset_model_registry():
    ModelRegistry._reset()
    yield


def start_container(port: int, wait: Callable[[], None]):
    """A Neo4j container of its own (not kept: `remove=True`), with the one database `neo4j`"""
    client = docker.from_env()
    container = client.containers.run(
        NEO4J_IMAGE,
        detach=True,
        remove=True,
        ports={"7687/tcp": port},
        environment={"NEO4J_AUTH": "/".join(NEO4J_AUTH)},
    )
    try:
        wait()
        yield container
    finally:
        container.stop()
        client.close()


@fixture(scope="session", autouse=True)
def assure_neo4j_container():
    try:
        check_neo4j()
    except neo4j.exceptions.DriverError, OSError:
        try:
            docker.from_env().ping()
        except docker.errors.DockerException as error:
            pytest.skip(
                f"Neo4j is not on {NEO4J_URI} and Docker is not running: {error}"
            )
        yield from start_container(7693, wait_for_neo4j)
    else:
        # An existing Neo4j instance is already available.
        yield


def check_neo4j():
    driver = neo4j.GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    try:
        driver.verify_connectivity()
    finally:
        driver.close()


@retry(stop=stop_after_delay(120), wait=wait_fixed(1))
def wait_for_neo4j():
    check_neo4j()


@fixture(scope="session")
def db_driver(
    assure_neo4j_container,
) -> Generator[neo4j.Driver]:
    driver = neo4j.GraphDatabase.driver(
        NEO4J_URI,
        auth=NEO4J_AUTH,
    )

    try:
        driver.verify_connectivity()
        yield driver
    finally:
        driver.close()


@fixture(scope="function")
def clear_database(db_driver):
    yield
    db_driver.execute_query(
        "MATCH (n) DETACH DELETE n",
        database=NEO4J_DATABASE,
    )


@fixture(scope="function", autouse=True)
def ensure_user(db_driver):
    username = current_request_username.get()

    db_driver.execute_query(
        """
        MERGE (user:PGUser {username: $username})
        """,
        parameters_={"username": username},
        database=NEO4J_DATABASE,
    )
    yield


def pytest_itemcollected(item):
    item.add_marker(mark.xdist_group("db"))


@pytest_asyncio.fixture(
    scope="session",
    loop_scope="session",
    autouse=True,
)
async def initialise_settings(
    event_loop_policy,
    db_driver,
):
    """Initialise application settings and the Neo4j database (with its indexes,
    constraints and so on)."""

    class Settings(BaseSettings[Neo4jDatabaseSettings]):
        PROJECT_NAME: str = "Test"
        BACKEND_CORS_ORIGINS: list[typing.Any] = []
        INSTALLED_APPS: list[str] = []
        DATABASE_MODULE: str = "pangloss_neo4j.databases.neo4j"
        DATABASE: Neo4jDatabaseSettings = Neo4jDatabaseSettings(
            DB_URL=NEO4J_URI,
            DB_USERNAME=NEO4J_AUTH[0],
            DB_PASSWORD=NEO4J_AUTH[1],
            DATABASE_NAME=NEO4J_DATABASE,
        )
        INTERFACE_LANGUAGES: list[str] = []
        DEFAULT_INTERFACE_LANGUAGES: str = "en"
        AUTHJWT_SECRET_KEY: str = "a secret for the tests, of a decent length"
        ENTITY_BASE_URL: AnyHttpUrl = AnyHttpUrl("http://test.com/")

    settings = Settings()
    db = Database(settings=settings)
    await db._initialise_driver()
    await initialise_database(db)

    try:
        yield
    finally:
        await db.close()


def bulk_reachable() -> None:
    driver = neo4j.GraphDatabase.driver(BULK_URI, auth=NEO4J_AUTH)
    try:
        driver.verify_connectivity()
    finally:
        driver.close()


@retry(stop=stop_after_delay(120), wait=wait_fixed(1))
def wait_for_bulk():
    bulk_reachable()


@pytest.fixture(scope="session")
def bulk_neo4j():
    """A Neo4j of its own for the tests of the bulk load (it needs an empty database)"""
    try:
        bulk_reachable()
    except neo4j.exceptions.DriverError, OSError:
        yield from start_container(7694, wait_for_bulk)
    else:
        yield
