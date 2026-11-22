"""The suite every part of similarity passes (implementation_docs/vectors.md, "The suite of a part";
implementation_docs/similarity-build-plan.md, step 8.4). Behaviour is said once, here; a part's live tests call it.

A part's `tests/live/conftest.py` gives the apps and settings:

    from pangloss_testing.live import *  # noqa: F403
    from pangloss_testing import parts

    @pytest.fixture(scope="session")
    def installed_apps():
        return parts.installed_apps("pangloss_names")

    @pytest.fixture(scope="session")
    def settings_extras():
        return parts.settings_extras(NAMES_DIMENSION=(int, 256))

and its test module subclasses the suite, naming the part and its slow way:

    from pangloss_testing.parts import PartSuite

    async def rebuilt(db_driver):
        ...  # what a whole rebuild of the part would give now, by id

    class TestTheNamePart(PartSuite):
        parts = {"name": rebuilt}

`writes` holds the payloads and the writes, by name, on `pangloss_testing.similar_models`; `suite` the claims."""

from pangloss_testing.parts.suite import (
    PartSuite,
    Slow,
    differences,
    drop_vector_indexes,
    installed_apps,
    one_turn,
    settings_extras,
    stored,
    the_others_done,
    vectors_left,
)

__all__ = [
    "PartSuite",
    "Slow",
    "differences",
    "drop_vector_indexes",
    "installed_apps",
    "one_turn",
    "settings_extras",
    "stored",
    "the_others_done",
    "vectors_left",
]
