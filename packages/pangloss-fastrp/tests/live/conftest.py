"""Fixtures for the live tests of the graph part (on the backend under test: see `pangloss_testing`)"""

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
    """(the apps `pangloss_testing.similar_models` is declared with, and the two of similarity)"""
    return [
        "pangloss_derived",
        "pangloss_library",
        "pangloss_criteria",
        "pangloss_vectors",
        "pangloss_fastrp",
    ]


@pytest.fixture(scope="session")
def settings_extras() -> dict:
    """(so that a test can change what the graph sees and the cap of a refresh)"""
    return {
        "VECTORS_PROFILES": (dict | None, None),
        "VECTORS_GRAPH_SEES": (str, "everyone"),
        "FASTRP_REFRESH_CAP": (int, 50_000),
    }


@pytest.fixture
def graph_sees(settings, monkeypatch):
    """Sets `VECTORS_GRAPH_SEES` for the test"""

    def set_to(value: str) -> None:
        monkeypatch.setattr(settings, "VECTORS_GRAPH_SEES", value)

    return set_to
