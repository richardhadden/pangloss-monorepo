"""Fixtures for the live tests of matches criteria (on the backend under test: see `pangloss_testing`)"""

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
    """(the package's routes are made only for an installed app. `pangloss_derived` too, for the tests of the two
    together (`test_criteria_derived_live.py`, the churn test): its hooks are there in any case, since
    `pangloss_criteria.models` imports it; installed, its structure is made and its routes are there)"""
    return ["pangloss_derived", "pangloss_criteria"]
