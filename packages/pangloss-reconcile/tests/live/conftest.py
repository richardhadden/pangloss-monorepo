"""Fixtures for the live tests of reconciliation (on the backend under test: see `pangloss_testing`)"""

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
    """(the apps `pangloss_testing.similar_models` is declared with, similarity's, the graph and name parts, and this
    one)"""
    return parts.installed_apps(
        "pangloss_fastrp", "pangloss_names", "pangloss_reconcile"
    )


@pytest.fixture(scope="session")
def settings_extras() -> dict:
    """(the suite's, with a profile that weighs the name and the graph, as the demo's `who`, named as the profile
    candidates are found by: the default profile weighs the class and the graph, two parts too, and comes first by
    its name)"""
    return parts.settings_extras(
        VECTORS_PROFILES=(dict | None, {"who": {"name": 1, "graph": 0.25}}),
        NAMES_DIMENSION=(int, 256),
        NAMES_VARIANTS=(str | None, None),
        FASTRP_REFRESH_CAP=(int, 50_000),
        RECONCILE_PROFILE=(str | None, "who"),
        RECONCILE_FETCH=(int, 50),
        RECONCILE_WEIGHTS=(dict, {}),
        RECONCILE_MOST_UNKNOWNS=(int, 20),
        RECONCILE_REASONS=(int, 5),
        RECONCILE_LEAST_SCORE=(float, 0.2),
        RECONCILE_KEEP_DECISIONS=(bool, True),
        RECONCILE_SHOWN_FOR=(float, 30.0),
        RECONCILE_LEARN_FROM=(int, 100),
        RECONCILE_NEW_ABOVE=(float, 0.5),
        # (step 10.5c's and 10.5d's, at their defaults: here so that a test can change one)
        RECONCILE_SUGGEST_ABOVE=(float, 0.6),
        RECONCILE_SUGGEST_MOST=(int, 3),
        RECONCILE_SUGGEST_WITHIN=(float, 0.7),
        RECONCILE_SUGGEST_ON_SAVE=(bool, False),
        RECONCILE_SUGGEST_AS=(str, "IdentificationByToolchainFromText"),
        RECONCILE_TOOLCHAIN=(str, "pangloss-reconcile"),
        RECONCILE_WORKER_IN_SERVER=(bool, True),
    )
