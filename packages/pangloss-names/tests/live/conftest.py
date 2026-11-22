"""Fixtures for the live tests of the name part (on the backend under test: see `pangloss_testing`)"""

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
    declared with, and similarity's; the graph part beside the name part, as a project would have it)"""
    return parts.installed_apps("pangloss_fastrp", "pangloss_names")


@pytest.fixture(scope="session")
def settings_extras() -> dict:
    """(the suite's, with a profile that weighs the name part: its own weight is 0, and a part no profile weighs is
    never combined)"""
    return parts.settings_extras(
        VECTORS_PROFILES=(dict | None, {"who": {"name": 1, "graph": 0.25}}),
        NAMES_DIMENSION=(int, 256),
        # (no table of variants; a test sets one, `monkeypatch.setattr(SETTINGS, "NAMES_VARIANTS", path)`)
        NAMES_VARIANTS=(str | None, None),
    )
