"""Fixtures for the live tests of the vectors (on the backend under test: see `pangloss_testing`)"""

import pangloss_core.settings as core_settings
import pytest
from pangloss_testing.live import *  # noqa: F403
from pangloss_testing.live import mark_database_tests


def pytest_itemcollected(item):
    mark_database_tests(item)


@pytest.fixture(scope="module", autouse=True)
def settings(initialise_settings):
    """(Instead of the settings of the tests above, which have no database)"""
    core_settings.SETTINGS = initialise_settings
    return initialise_settings


@pytest.fixture(scope="session")
def installed_apps() -> list[str]:
    return ["pangloss_vectors"]


@pytest.fixture(scope="session")
def settings_extras() -> dict:
    """(so that a test can give profiles of its own, none by default, and change the class part's decay and what
    the graph sees)"""
    return {
        "VECTORS_PROFILES": (dict | None, None),
        "VECTORS_CLASS_DECAY": (float, 0.5),
        "VECTORS_GRAPH_SEES": (str, "everyone"),
    }
