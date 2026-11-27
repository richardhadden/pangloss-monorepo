"""Fixtures for the live tests of comparison (on the backend under test: see `pangloss_testing`)"""

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
    """(the apps `pangloss_testing.similar_models` is declared with, `pangloss_dates`, whose dates
    `declare(compared=True)` uses, and this one)"""
    return [
        "pangloss_derived",
        "pangloss_library",
        "pangloss_criteria",
        "pangloss_dates",
        "pangloss_compare",
    ]


@pytest.fixture(scope="session")
def settings_extras() -> dict:
    """(the package's settings at their defaults: here so that a test can change one)"""
    return {
        "COMPARE_MOST_PAIRS": (int, 200),
        "COMPARE_LEARN_FROM": (int, 100),
    }
