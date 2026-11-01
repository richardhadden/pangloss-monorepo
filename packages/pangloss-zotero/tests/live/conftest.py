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
def live_db(clear_database, initialise_settings):
    """An empty database, with the user of the tests (`clear_database`)"""
    yield initialise_settings
