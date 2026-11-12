"""The fixtures of a live test, for the backend under test. A package's `tests/live/conftest.py` imports them:

    from pangloss_testing.live import *  # noqa: F403

(They are not a plugin: a plugin's fixtures would be there for every test of a session, these only below the conftest that
imports them.)"""

import contextlib
import functools
import inspect
import logging
import os
import sys
import typing
from collections.abc import Generator

import neo4j
import pangloss_core.settings as core_settings
import pydantic
import pytest
import pytest_asyncio
from pangloss_core import BaseSettings
from pangloss_models import ModelRegistry
from pangloss_users import current_request_username
from pydantic import AnyHttpUrl
from tenacity import retry, stop_after_delay, wait_fixed

from pangloss_testing.backends import BackendUnderTest, database_group, under_test

__all__ = [
    "assure_container",
    "backend_under_test",
    "clear_database",
    "command_backend",
    "database_running",
    "db_driver",
    "ensure_user",
    "apply_changes",
    "initialise_database",
    "initialise_settings",
    "installed_apps",
    "live_database",
    "mark_database_tests",
    "reset_model_registry",
    "run",
    "run_command",
    "run_connected",
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


@contextlib.contextmanager
def database_running(backend: BackendUnderTest) -> Generator[None]:
    """The database of `backend`: the one that is there, or one started in Docker for the block (and stopped after).
    Skips the test if there is neither"""
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
            name=backend.container_name,
            detach=True,
            remove=True,
            ports={"7687/tcp": backend.port},
            environment=backend.container_environment,
            command=backend.container_command or None,
        )
        try:
            retry(stop=stop_after_delay(120), wait=wait_fixed(1))(reachable)(backend)
            yield
        finally:
            container.stop()
            client.close()
    else:
        yield  # (one is there already)


@pytest.fixture(scope="session", autouse=True)
def assure_container(backend_under_test: BackendUnderTest):
    """The database of the backend under test: the one that is there, or one in Docker (stopped at the end). Skips if there is
    neither."""
    with database_running(backend_under_test):
        yield


# More nodes than the tests ever leave behind: a database with as many is somebody's data
REAL_DATA_NODES = 20_000


def refuse_to_empty_real_data(driver: neo4j.Driver, uri: str, database: str) -> None:
    """Stop the run if the database the tests are about to empty looks like real data.

    The tests empty the database they are pointed at, on the port a new project's settings have by default
    (7687): a project with data on that port, on the machine the tests are run on, would lose it. This catches a
    database with a great deal in it (more than `REAL_DATA_NODES` nodes), which is the loss that cannot be made
    good; a small one is not told from what a test run left. `PANGLOSS_TEST_WIPE=1` says to go ahead."""
    if os.environ.get("PANGLOSS_TEST_WIPE") == "1":
        return
    records, _, _ = driver.execute_query(
        "MATCH (n) RETURN count(n) AS nodes", database_=database
    )
    nodes = records[0]["nodes"]
    if nodes > REAL_DATA_NODES:
        pytest.exit(
            f"The database on {uri} has {nodes:,} nodes: that looks like a project's data, and the tests would "
            "empty it. Give the project's database another port (the tests use this one), or, if it really is "
            "the test database, run again with PANGLOSS_TEST_WIPE=1.",
            returncode=3,
        )


@pytest.fixture(scope="session")
def db_driver(
    backend_under_test: BackendUnderTest, assure_container
) -> Generator[neo4j.Driver]:
    driver = neo4j.GraphDatabase.driver(
        backend_under_test.uri, auth=backend_under_test.auth
    )
    try:
        driver.verify_connectivity()
        refuse_to_empty_real_data(
            driver, backend_under_test.uri, backend_under_test.database
        )
        yield driver
    finally:
        driver.close()


def make_user(db_driver, backend: BackendUnderTest) -> None:
    db_driver.execute_query(
        "MERGE (user:PGUser {username: $username})",
        parameters_={"username": current_request_username.get()},
        database_=backend.database,
    )


@pytest.fixture
def clear_database(db_driver, backend_under_test: BackendUnderTest):
    """An empty database (but for the user of the tests) before the test, and after it"""
    clear = "MATCH (n) DETACH DELETE n"
    db_driver.execute_query(clear, database_=backend_under_test.database)
    make_user(db_driver, backend_under_test)
    yield
    db_driver.execute_query(clear, database_=backend_under_test.database)


@pytest.fixture(autouse=True)
def ensure_user(db_driver, backend_under_test: BackendUnderTest):
    make_user(db_driver, backend_under_test)
    yield


@pytest.fixture(scope="session")
def installed_apps() -> list[str]:
    """`INSTALLED_APPS` of the test settings: a conftest overrides this fixture for a package that needs to be there"""
    return []


@pytest.fixture(scope="session")
def settings_extras() -> dict[str, tuple[typing.Any, typing.Any]]:
    """More settings, as `{name: (type, default)}`: a conftest overrides this fixture for a package that has settings of its own"""
    return {}


@pytest.fixture(scope="session", autouse=True)
def initialise_settings(
    backend_under_test: BackendUnderTest,
    event_loop_policy,
    db_driver,
    installed_apps,
    settings_extras,
):
    """Settings for the backend under test"""
    backend = backend_under_test
    settings_type = backend.settings_type

    Settings = pydantic.create_model(
        "Settings",
        __base__=BaseSettings[settings_type],
        PROJECT_NAME=(str, "Test"),
        BACKEND_CORS_ORIGINS=(list[typing.Any], []),
        INSTALLED_APPS=(list[str], installed_apps),
        STORAGE=(str | None, backend.storage),
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
        DEFAULT_INTERFACE_LANGUAGE=(str, "en"),
        AUTHJWT_SECRET_KEY=(str, "a secret for the tests, of a decent length"),
        ENTITY_BASE_URL=(AnyHttpUrl, AnyHttpUrl("http://test.com/")),
        **settings_extras,
    )
    return Settings()


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def live_database(backend_under_test: BackendUnderTest, initialise_settings):
    """The `Database` of these tests, with its indexes and constraints"""
    database_module = backend_under_test.module("database")
    database = database_module.Database(settings=initialise_settings)
    with database_module.using(database):
        await backend_under_test.module("initialise_database").initialise_database(
            database
        )
    try:
        yield database
    finally:
        await database.close()


@pytest.fixture(scope="module", autouse=True)
def use_live_settings(
    initialise_settings, live_database, backend_under_test: BackendUnderTest
):
    """The settings and the database of these tests are the process's while a module of them runs (both are the
    process's, and the tests of another package that ran before in the same process made their own)"""
    core_settings.configure(initialise_settings)
    backend_under_test.module("database").install(live_database)


def mark_database_tests(item) -> None:
    """For a conftest's `pytest_itemcollected`: a test that uses the test database is marked `database` (`-m database`
    picks them), and the tests that use one database are run by one xdist worker (`backends.database_group`)"""
    item.add_marker(pytest.mark.database)
    item.add_marker(pytest.mark.xdist_group(database_group(item)))
    _end_background_work(item)


def _end_background_work(item) -> None:
    """What an async test left running in the background (`pangloss-review`: the others of a task, the index of
    URIs) ends before the test does. A task left when the test's event loop stops is in the middle of a
    transaction, and Neo4j then makes the delete that empties the database wait for its locks, for ever. (It has to
    be awaited in the test's own loop: a fixture is finished in another.)"""
    test = getattr(item, "obj", None)
    if not inspect.iscoroutinefunction(test):
        return

    @functools.wraps(test)
    async def ended(*args, **kwargs):
        try:
            return await test(*args, **kwargs)
        finally:
            reconcile = sys.modules.get("pangloss_review.reconcile")
            if reconcile is not None:
                await reconcile.background_done()

    item.obj = ended


@pytest.fixture
def command_backend():
    """The backend for a command run in a test (`run_command`). A command runs its own event loop (`asyncio.run`), and
    the driver the other tests share belongs to theirs: each loop gets a driver of its own, and the shared one is put
    back after"""
    from types import SimpleNamespace

    setup = under_test().module("setup")
    database = under_test().module("database").current()
    shared = database.driver

    async def connect():
        database.driver = (
            None  # (the shared one belongs to the other loop: not closed here)
        )
        driver = await database.ensure_driver()
        await driver.verify_connectivity()

    yield SimpleNamespace(connect=connect, disconnect=setup.disconnect)
    database.driver = shared


def run_command(cli, backend, *arguments: str, settings: typing.Any = None):
    """A command of an app's `cli.py` (`pangloss typology load ...`), run as `pangloss` would, on the models the test
    declared (nothing more is imported), `command_backend`'s database, and the settings given (for a command that
    asks for them). Its result: `exit_code`, `output`"""
    from types import SimpleNamespace

    from typer.testing import CliRunner

    project = SimpleNamespace(
        require_database=lambda: backend,
        import_models=lambda: None,
        require_settings=lambda: settings,
    )
    # (what is logged goes to the output the runner keeps: a query that is slow on a busy machine would put its
    # warning among the lines a test reads)
    logging.disable(logging.WARNING)
    try:
        return CliRunner().invoke(cli, list(arguments), obj=project)
    finally:
        logging.disable(logging.NOTSET)


def run_connected(backend, make):
    """A coroutine function run with `command_backend` connected, in a loop of its own (to make what a command finds)"""
    import asyncio

    async def main():
        await backend.connect()
        try:
            return await make()
        finally:
            await backend.disconnect()

    return asyncio.run(main())


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
    await (
        under_test().module("initialise_database").initialise_database(*args, **kwargs)
    )


async def apply_changes(*args: typing.Any, **kwargs: typing.Any) -> None:
    """The backend's `migrations.apply_changes(database, snapshot, changes)`"""
    await under_test().module("migrations").apply_changes(*args, **kwargs)
