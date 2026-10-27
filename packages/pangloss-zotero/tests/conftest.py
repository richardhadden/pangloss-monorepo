import sys
from pathlib import Path

import pytest
from pangloss_models.model_registry import ModelRegistry

sys.path.insert(0, str(Path(__file__).parent))


@pytest.fixture(autouse=True)
def reset_model_registry():
    ModelRegistry._reset()
    yield


# --- a live database, for the tests of the real store (skipped when there is none) -------------------

import typing

import neo4j
import pytest_asyncio
from zotero_live import MEMGRAPH_AUTH, MEMGRAPH_DATABASE, MEMGRAPH_URI, reachable
from pangloss_core.settings import BaseSettings
from pydantic import AnyHttpUrl


def pytest_itemcollected(item):
    # (the tests of every package that use the one test database are run by one worker)
    if "live_db" in getattr(item, "fixturenames", ()):
        item.add_marker(pytest.mark.xdist_group("db"))


@pytest.fixture(scope="session")
def db_driver():
    if not reachable():
        pytest.skip("no test Memgraph on localhost:7687")
    driver = neo4j.GraphDatabase.driver(MEMGRAPH_URI, auth=MEMGRAPH_AUTH)
    yield driver
    driver.close()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def live_settings(db_driver):
    from pangloss_memgraph.databases.memgraph.database import Database
    from pangloss_memgraph.databases.memgraph.initialise_database import (
        initialise_database,
    )
    from pangloss_memgraph.databases.memgraph.settings import MemgraphDatabaseSettings

    class Settings(BaseSettings[MemgraphDatabaseSettings]):
        PROJECT_NAME: str = "Test"
        BACKEND_CORS_ORIGINS: list[typing.Any] = []
        INSTALLED_APPS: list[str] = ["pangloss_zotero"]
        DATABASE_MODULE: str = "pangloss_memgraph.databases.memgraph"
        DATABASE: MemgraphDatabaseSettings = MemgraphDatabaseSettings(
            DB_URL=MEMGRAPH_URI,
            DB_USERNAME="test",
            DB_PASSWORD="test",
            DATABASE_NAME=MEMGRAPH_DATABASE,
        )
        INTERFACE_LANGUAGES: list[str] = []
        AUTHJWT_SECRET_KEY: str = "a secret for the tests, of a decent length"
        ENTITY_BASE_URL: AnyHttpUrl = AnyHttpUrl("http://test.com/")
        ZOTERO_API_KEY: str = "key"
        ZOTERO_LIBRARIES: list[str] = ["groups/1"]

    settings = Settings()
    db = Database(settings=settings)
    await db._initialise_driver()
    await initialise_database(db)
    yield settings
    await db.close()


@pytest.fixture
def live_db(db_driver, live_settings):
    """Empty database, with the users there must be"""

    def clear():
        db_driver.execute_query("MATCH (n) DETACH DELETE n", database=MEMGRAPH_DATABASE)

    clear()
    db_driver.execute_query(
        "MERGE (:PGUser {username: 'pangloss_default_user'})",
        database=MEMGRAPH_DATABASE,
    )
    yield live_settings
    clear()


@pytest.fixture
def offline_settings():
    """Settings with a database module that needs no connection (for `initialise()`)"""
    from pangloss_core import settings as core_settings
    from pangloss_core.settings import BaseSettings, DatabaseSettings
    from pydantic import AnyHttpUrl

    class Settings(BaseSettings):
        PROJECT_NAME: str = "Test"
        BACKEND_CORS_ORIGINS: list = []
        INSTALLED_APPS: list[str] = []
        DATABASE_MODULE: str = "pangloss_sdk.databases.api"
        DATABASE: DatabaseSettings = DatabaseSettings()
        INTERFACE_LANGUAGES: list[str] = []
        DEFAULT_INTERFACE_LANGUAGE: str = "en"
        AUTHJWT_SECRET_KEY: str = "asdf"
        ENTITY_BASE_URL: AnyHttpUrl = AnyHttpUrl("http://test.com/")

    saved = core_settings.__dict__.get("SETTINGS")
    made = Settings()
    yield made
    if saved is None:
        core_settings.__dict__.pop("SETTINGS", None)
    else:
        core_settings.SETTINGS = saved
