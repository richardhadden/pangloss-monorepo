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


@pytest.fixture(autouse=True)
def compile_rules_afresh():
    """Each test compiles its rules again: the Cypher of a rule is kept by its name and hash (`store._compiled`), and a
    process that runs a test after another (mutmut forks each mutant's from one that ran them all) would otherwise
    reuse what was compiled before"""
    from pangloss_derived import store

    store._compiled.clear()
    yield
