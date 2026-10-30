"""Fixtures for the live tests of the Zotero store (on the backend under test: see `pangloss_testing`)"""

import pytest
from pangloss_testing.live import *  # noqa: F403
from pangloss_testing.live import mark_database_tests


def pytest_itemcollected(item):
    mark_database_tests(item)


@pytest.fixture(scope="session")
def installed_apps():
    return ["pangloss_zotero"]


@pytest.fixture(scope="session")
def settings_extras():
    return {
        "ZOTERO_API_KEY": (str, "key"),
        "ZOTERO_LIBRARIES": (list[str], ["groups/1"]),
    }


@pytest.fixture
def live_db(db_driver, backend_under_test, initialise_settings):
    """Empty database, with the users there must be"""

    def clear():
        db_driver.execute_query(
            "MATCH (n) DETACH DELETE n", database_=backend_under_test.database
        )

    clear()
    db_driver.execute_query(
        "MERGE (:PGUser {username: 'pangloss_default_user'})",
        database_=backend_under_test.database,
    )
    yield initialise_settings
    clear()
