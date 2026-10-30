"""Fixtures for the live tests of the calendar (on the backend under test: see `pangloss_testing`)"""

import pytest
from pangloss_testing.live import *  # noqa: F403
from pangloss_testing.live import mark_database_tests


def pytest_itemcollected(item):
    mark_database_tests(item)
from pangloss_testing.live import run


@pytest.fixture
def clear_calendar(db_driver):
    clear = "MATCH (n) WHERE any(l IN labels(n) WHERE l STARTS WITH 'Calendar') DETACH DELETE n"
    run(db_driver, clear)
    yield
    run(db_driver, clear)
