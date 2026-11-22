"""Fixtures for the live tests of the graph part (on the backend under test: see `pangloss_testing`)"""

import pangloss_core.settings as core_settings
import pytest
from pangloss_testing import parts
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
    """(the apps of the suite of the parts, `pangloss_testing.parts`: those `pangloss_testing.similar_models` is
    declared with, and the two of similarity)"""
    return parts.installed_apps("pangloss_fastrp")


@pytest.fixture(scope="session")
def settings_extras() -> dict:
    """(the suite's, so that a test can change what the graph sees; and the cap of a refresh)"""
    return parts.settings_extras(FASTRP_REFRESH_CAP=(int, 50_000))


@pytest.fixture
def graph_sees(settings, monkeypatch):
    """Sets `VECTORS_GRAPH_SEES` for the test"""

    def set_to(value: str) -> None:
        monkeypatch.setattr(settings, "VECTORS_GRAPH_SEES", value)

    return set_to
