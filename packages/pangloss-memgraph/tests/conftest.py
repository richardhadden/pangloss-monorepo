import typing
from collections.abc import Generator

import docker
import neo4j
import pytest
import pytest_asyncio
from pangloss_core.settings import BaseSettings
from pangloss_memgraph.databases.memgraph.database import Database
from pangloss_memgraph.databases.memgraph.settings import MemgraphDatabaseSettings
from pangloss_models.model_registry import ModelRegistry
from pangloss_users import current_request_username
from pydantic import AnyHttpUrl
from pytest import fixture, mark
from tenacity import retry, stop_after_delay, wait_fixed

pytestmark = pytest.mark.asyncio(loop_scope="session")

MEMGRAPH_URI = "bolt://localhost:7687"
MEMGRAPH_AUTH = ("test", "test")
MEMGRAPH_DATABASE = "memgraph"
TEXT_INDEX_NAME = "label_index"


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
                "/tmp/mg_data": {
                    "bind": "/var/lib/memgraph",
                    "mode": "rw",
                },
            },
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


@fixture(scope="session", autouse=True)
def create_memgraph_indexes(db_driver):
    """Create required indexes if they do not already exist."""

    with db_driver.session(database=MEMGRAPH_DATABASE) as session:
        # SHOW INDEX INFO includes Memgraph's text-index information.
        existing_indexes = session.run("SHOW INDEX INFO").data()

        index_exists = any(TEXT_INDEX_NAME in repr(index) for index in existing_indexes)

        if not index_exists:
            # session.run() executes an implicit (auto-commit) transaction.
            # Do not use session.begin_transaction() for index creation.
            session.run(
                """
                CREATE TEXT INDEX label_index
                ON :PGIndexableNode(label);
                """
            ).consume()


@fixture(scope="function")
def clear_database(db_driver):
    yield
    db_driver.execute_query(
        "MATCH (n) DETACH DELETE n",
        database=MEMGRAPH_DATABASE,
    )


@fixture(scope="function", autouse=True)
def ensure_user(db_driver):
    username = current_request_username.get()

    db_driver.execute_query(
        """
        MERGE (user:PGUser {username: $username})
        """,
        parameters_={"username": username},
        database=MEMGRAPH_DATABASE,
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
    create_memgraph_indexes,
):
    """Initialise application settings and the Memgraph database."""

    class Settings(BaseSettings[MemgraphDatabaseSettings]):
        PROJECT_NAME: str = "Test"
        BACKEND_CORS_ORIGINS: list[typing.Any] = []
        INSTALLED_APPS: list[str] = []
        DATABASE_MODULE: str = "pangloss_memgraph.databases.memgraph"
        DATABASE: MemgraphDatabaseSettings = MemgraphDatabaseSettings(
            DB_URL=MEMGRAPH_URI,
            DB_USERNAME="test",
            DB_PASSWORD="test",
            DATABASE_NAME=MEMGRAPH_DATABASE,
        )
        INTERFACE_LANGUAGES: list[str] = []
        DEFAULT_INTERFACE_LANGUAGES: str = "en"
        AUTHJWT_SECRET_KEY: str = "asdf"
        ENTITY_BASE_URL: AnyHttpUrl = AnyHttpUrl("http://test.com/")

    settings = Settings()
    db = Database(settings=settings)
    await db._initialise_driver()

    try:
        yield
    finally:
        await db.close()
