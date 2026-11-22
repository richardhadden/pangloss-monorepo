"""Fixtures for the live tests of the time part (on the backend under test: see `pangloss_testing`)"""

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
    declared with, and similarity's; with `pangloss_dates`, whose dates `declare(dated=True)` uses)"""
    return parts.installed_apps("pangloss_dates", "pangloss_dates_vectors")


@pytest.fixture(scope="session")
def settings_extras() -> dict:
    """(the suite's, with a profile that weighs the time part, so that its refresh and removals keep a combined vector
    up too: its own weight is 0, and a part no profile weighs is never combined)"""
    return parts.settings_extras(
        VECTORS_PROFILES=(dict | None, {"when": {"time": 1, "class": 0.1}}),
        DATES_VECTOR_DIMENSION=(int, 128),
        DATES_VECTOR_WIDTH=(float, 2.0),
        # (none; a test sets some, `monkeypatch.setattr(SETTINGS, "VECTORS_EXCLUDE", [...])`)
        VECTORS_EXCLUDE=(list[str], []),
    )
