"""The apps and settings of the suite of the parts (`pangloss_testing.parts`), for the class part: the models of
`pangloss_testing.similar_models` need apps the other live tests of this package do not install (and the settings of
those tests are made once, from the fixtures of the conftest above, so the suite has a directory of its own)"""

import pytest
from pangloss_testing import parts
from pangloss_testing.live import *  # noqa: F403


@pytest.fixture(scope="session")
def installed_apps() -> list[str]:
    return parts.installed_apps()


@pytest.fixture(scope="session")
def settings_extras() -> dict:
    return parts.settings_extras(VECTORS_CLASS_DECAY=(float, 0.5))
