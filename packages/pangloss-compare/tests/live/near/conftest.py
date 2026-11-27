"""The apps and settings of the live tests of the pairs through near entities (step 6.4): similarity's, the graph and
name parts, and a profile `who` that weighs the name and the graph, as the demo's (the settings of the other live tests
are made once, from the fixtures of the conftest above, and have no vectors: so these have a directory of their own,
as `pangloss-vectors`' suite has)"""

import pytest
from pangloss_testing import parts
from pangloss_testing.live import *  # noqa: F403


@pytest.fixture(scope="session")
def installed_apps() -> list[str]:
    return parts.installed_apps(
        "pangloss_fastrp", "pangloss_names", "pangloss_dates", "pangloss_compare"
    )


@pytest.fixture(scope="session")
def settings_extras() -> dict:
    """(the suite's, with the profile `who`, named as the profile near entities are found by; the package's own
    settings at their defaults, here so that a test can change one)"""
    return parts.settings_extras(
        VECTORS_PROFILES=(dict | None, {"who": {"name": 1, "graph": 0.25}}),
        NAMES_DIMENSION=(int, 256),
        NAMES_VARIANTS=(str | None, None),
        FASTRP_REFRESH_CAP=(int, 50_000),
        COMPARE_MOST_PAIRS=(int, 200),
        COMPARE_LEARN_FROM=(int, 100),
        COMPARE_PROFILE=(str | None, "who"),
        COMPARE_NEAR_K=(int, 5),
        COMPARE_NEAR=(float, 0.6),
    )
