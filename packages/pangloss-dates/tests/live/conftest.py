"""Fixtures for the live tests of the dates (on the backend under test: see `pangloss_testing`)"""

import pangloss_core.settings as core_settings
import pytest
from pangloss_testing.live import *  # noqa: F403
from pangloss_testing.live import mark_database_tests


def pytest_itemcollected(item):
    mark_database_tests(item)


@pytest.fixture(scope="module", autouse=True)
def initialise_database(initialise_settings):
    """(Instead of the settings of the tests above, which have no database: a fixture of that name)"""
    core_settings.SETTINGS = initialise_settings
