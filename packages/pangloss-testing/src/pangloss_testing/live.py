"""The fixtures of a live test, for the backend under test. A package's `tests/live/conftest.py` imports them:

    from pangloss_testing.live import *  # noqa: F403

(They are not a plugin: a plugin's fixtures would be there for every test of a session, these only below the conftest that
imports them.)"""

import typing
from collections.abc import Generator

import neo4j
import pangloss_core.settings as core_settings
import pydantic
import pytest
import pytest_asyncio
from pangloss_core.settings import BaseSettings
from pangloss_models.model_registry import ModelRegistry
from pangloss_users import current_request_username
from pydantic import AnyHttpUrl
from tenacity import retry, stop_after_delay, wait_fixed

from pangloss_testing.backends import BackendUnderTest, under_test

__all__ = [
    "assure_container",
    "backend_under_test",
    "clear_database",
    "db_driver",
    "ensure_user",
    "apply_changes",
    "initialise_database",
    "initialise_settings",
    "installed_apps",
    "mark_database_tests",
    "reset_model_registry",
    "run",
    "use_live_settings",
    "settings_extras",
]


@pytest.fixture(scope="session")
def backend_under_test() -> BackendUnderTest:
    return under_test()


@pytest.fixture(autouse=True)
def reset_model_registry():
    ModelRegistry._reset()
    yield


def reachable(backend: BackendUnderTest) -> None:
    driver = neo4j.GraphDatabase.driver(backend.uri, auth=backend.auth)
    try:
        driver.verify_connectivity()
    finally:
        driver.close()


@pytest.fixture(scope="session", autouse=True)
def assure_container(backend_under_test: BackendUnderTest):
    """The database of the backend under test: the one that is there, or one in Docker (stopped at the end). Skips if there is
    neither."""
    backend = backend_under_test
    try:
        reachable(backend)
    except neo4j.exceptions.DriverError, OSError:
        try:
            import docker

            client = docker.from_env()
            client.ping()
        except Exception as error:
            pytest.skip(
                f"There is no {backend.name} on {backend.uri} and Docker is not running: {error}"
            )
        container = client.containers.run(
            backend.image,
            detach=True,
            remove=True,
            ports={"7687/tcp": backend.port},
            environment=backend.container_environment,
            command=backend.container_command or None,
        )
        try:
            retry(stop=stop_after_delay(120), wait=wait_fixed(1))(reachable)(backend)
            yield container
        finally:
            container.stop()
            client.close()
    else:
        yield  # (one is there already)


@pytest.fixture(scope="session")
def db_driver(
    backend_under_test: BackendUnderTest, assure_container
) -> Generator[neo4j.Driver]:
    driver = neo4j.GraphDatabase.driver(
        backend_under_test.uri, auth=backend_under_test.auth
    )
    try:
        driver.verify_connectivity()
        yield driver
    finally:
        driver.close()


@pytest.fixture
def clear_database(db_driver, backend_under_test: BackendUnderTest):
    yield
    db_driver.execute_query(
        "MATCH (n) DETACH DELETE n", database_=backend_under_test.database
    )


@pytest.fixture(autouse=True)
def ensure_user(db_driver, backend_under_test: BackendUnderTest):
    db_driver.execute_query(
        "MERGE (user:PGUser {username: $username})",
        parameters_={"username": current_request_username.get()},
        database_=backend_under_test.database,
    )
    yield


@pytest.fixture(scope="session")
def installed_apps() -> list[str]:
    """`INSTALLED_APPS` of the test settings: a conftest overrides this fixture for a package that needs to be there"""
    return []


@pytest.fixture(scope="session")
def settings_extras() -> dict[str, tuple[typing.Any, typing.Any]]:
    """More settings, as `{name: (type, default)}`: a conftest overrides this fixture for a package that has settings of its own"""
    return {}


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def initialise_settings(
    backend_under_test: BackendUnderTest,
    event_loop_policy,
    db_driver,
    installed_apps,
    settings_extras,
):
    """Settings for the backend under test, its `Database`, and its indexes and constraints"""
    backend = backend_under_test
    settings_type = backend.settings_type

    Settings = pydantic.create_model(
        "Settings",
        __base__=BaseSettings[settings_type],
        PROJECT_NAME=(str, "Test"),
        BACKEND_CORS_ORIGINS=(list[typing.Any], []),
        INSTALLED_APPS=(list[str], installed_apps),
        DATABASE_MODULE=(str, backend.database_module),
        DATABASE=(
            settings_type,
            settings_type(
                DB_URL=backend.uri,
                DB_USERNAME=backend.username,
                DB_PASSWORD=backend.password,
                DATABASE_NAME=backend.database,
            ),
        ),
        INTERFACE_LANGUAGES=(list[str], []),
        DEFAULT_INTERFACE_LANGUAGES=(str, "en"),
        AUTHJWT_SECRET_KEY=(str, "a secret for the tests, of a decent length"),
        ENTITY_BASE_URL=(AnyHttpUrl, AnyHttpUrl("http://test.com/")),
        **settings_extras,
    )
    settings = Settings()
    # One `Database` for the process: the models bind to `Database.default` the first time they are used, and another
    # conftest (the backend package's own) that makes a second would have the tests and the models on different ones
    database_class = backend.module("database").Database
    existing = getattr(database_class, "default", None)
    if existing is not None and hasattr(existing, "driver"):
        database = existing
        made = False
    else:
        database = database_class(settings=settings)
        await database._initialise_driver()
        made = True
    await backend.module("initialise_database").initialise_database(database)
    try:
        yield settings
    finally:
        if made:
            await database.close()


@pytest.fixture(scope="module", autouse=True)
def use_live_settings(initialise_settings):
    """The settings of the test session are those of these tests while a module of them runs (the settings are global, and
    the tests of another package that ran before made their own)"""
    core_settings.SETTINGS = initialise_settings


def mark_database_tests(item) -> None:
    """For a conftest's `pytest_itemcollected`: the tests that use the one test database are run by one xdist worker"""
    item.add_marker(pytest.mark.xdist_group("db"))


def run(db_driver, cypher: str, **params) -> list[dict]:
    """Run a query against the test database and give each record as a dict (with the maps that Neo4j keeps flat nested
    again, as the backend gives them)"""
    backend = under_test()
    records, _, _ = db_driver.execute_query(
        cypher, parameters_=params, database_=backend.database
    )
    rows = [r.data() for r in records]
    if backend.name == "neo4j":
        return [backend.module("properties").decode(row) for row in rows]
    return rows


async def initialise_database(*args: typing.Any, **kwargs: typing.Any) -> None:
    """The backend's `initialise_database` (indexes and constraints), on the `Database` in use"""
    await under_test().module("initialise_database").initialise_database(*args, **kwargs)


async def apply_changes(*args: typing.Any, **kwargs: typing.Any) -> None:
    """The backend's `migrations.apply_changes(database, snapshot, changes)`"""
    await under_test().module("migrations").apply_changes(*args, **kwargs)
