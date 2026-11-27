"""The setting of comparison (`COMPARE_MOST_PAIRS`, checked at `initialise()` with the app installed) and each compared
class's rules as the verdict takes them (`pangloss_compare.rules`). No database."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from typing import Any, no_type_check

import pytest
from pangloss_compare import maths, settings
from pangloss_compare.rules import rules
from pangloss_models.exceptions import PanglossInitialisationError


def conftest() -> Any:
    """This folder's `conftest.py` (not importable by its name: `tests/live` has one too)"""
    spec = importlib.util.spec_from_file_location(
        "pangloss_compare_tests_conftest", Path(__file__).parent / "conftest.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_most_pairs_are_200_unless_the_settings_say():
    assert settings.most_pairs(SimpleNamespace()) == 200
    assert settings.most_pairs(SimpleNamespace(COMPARE_MOST_PAIRS=1)) == 1
    assert settings.most_pairs(SimpleNamespace(COMPARE_MOST_PAIRS=5000)) == 5000


@pytest.mark.parametrize("value", [0, -1, 2.0, True, "200", None])
def test_most_pairs_that_is_not_a_whole_number_of_1_or_more_is_refused(value):
    with pytest.raises(
        PanglossInitialisationError,
        match="COMPARE_MOST_PAIRS is a whole number of 1 or more",
    ):
        settings.most_pairs(SimpleNamespace(COMPARE_MOST_PAIRS=value))


@no_type_check
def test_a_project_with_the_app_installed_has_its_setting_refused_at_initialise():
    from pangloss_testing.similar_models import declare

    here = conftest()
    APPS, make_settings = here.APPS, here.make_settings
    make_settings(INSTALLED_APPS=[*APPS, "pangloss_compare"], COMPARE_MOST_PAIRS=0)
    try:
        with pytest.raises(PanglossInitialisationError, match="COMPARE_MOST_PAIRS"):
            declare(compared=True)
        # (and without the app, it is not read)
        make_settings(COMPARE_MOST_PAIRS=0)
        declare(compared=True)
    finally:
        make_settings()


@no_type_check
def test_the_rules_are_each_compared_class_s_setting():
    from pangloss_testing.similar_models import declare

    declare(compared=True)

    assert rules() == {
        "Birth": maths.Rules(("person",), once_per="person"),
        "Making": maths.Rules(("made_by", "made"), once_per="made"),
        "MakingOfPicture": maths.Rules(("made_by", "made"), once_per="made"),
        "Activity": maths.Rules(("carried_out_by", "participants")),
        "Transfer": maths.Rules(("given_by", "given_to"), recurs=True),
        "Attendance": maths.Rules(("attended_by", "assembly_of")),
        "Order": maths.Rules(("ordered_by", "ordered_to")),
        "Rule": maths.Rules(("ruled_by", "binds")),
    }
