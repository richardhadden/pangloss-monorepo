"""The settings of `pangloss-reconcile` (`RECONCILE_PROFILE`, `RECONCILE_FETCH`, `RECONCILE_WEIGHTS` with `shared`,
`RECONCILE_LEAST_SCORE`, `RECONCILE_KEEP_DECISIONS`, `RECONCILE_SHOWN_FOR`): what each gives, each refusal by its message, the warning of a profile of the actual network
(`check_network`), and the check at `initialise()` when the app is installed"""

import warnings
from types import SimpleNamespace
from typing import Any, no_type_check

import pytest
from pangloss_core.settings import configure
from pangloss_models import Entity, ModelRegistry, initialise
from pangloss_models.exceptions import PanglossInitialisationError, PanglossModelWarning
from pangloss_reconcile import settings
from pangloss_vectors import Refreshed, parts

APPS = ["pangloss_vectors", "pangloss_reconcile"]


class Plain:
    """A part that computes nothing, and says nothing of an unknown"""

    local = True
    requires = frozenset()

    def __init__(self, name: str, weight: float = 0.0) -> None:
        self.name = name
        self.weight = weight

    def dimension(self) -> int:
        return 3

    def signature(self) -> str:
        return self.name

    async def rebuild(self, write) -> int:
        return 0

    async def refresh(self, changed, write) -> Refreshed:
        return Refreshed()

    async def overlay(self, plan) -> dict:
        return {}


class Knowing(Plain):
    """A part that can say what an unknown would be"""

    async def unknown(self, plan, unknowns) -> dict:
        return {}


@pytest.fixture(autouse=True)
def registered(monkeypatch):
    """The parts of these tests alone: `graph` and `name` say what an unknown would be, `time` does not"""
    monkeypatch.setattr(
        parts,
        "_PARTS",
        {
            "graph": Knowing("graph", 1.0),
            "name": Knowing("name"),
            "time": Plain("time"),
        },
    )


def given(**values: Any) -> SimpleNamespace:
    return SimpleNamespace(**values)


# -- RECONCILE_PROFILE ----------------------------------------------------------------------------------------------


def test_without_a_profile_named_it_is_the_one_that_weighs_the_most_parts_that_know_unknowns():
    profiles = {
        "when": {"time": 1, "graph": 1},
        "who": {"name": 1, "graph": 0.25},
    }
    assert settings.profile(given(VECTORS_PROFILES=profiles)) == "who"


def test_several_that_weigh_as_many_are_refused_and_one_has_to_be_named():
    profiles = {"who": {"name": 1, "graph": 0.25}, "also": {"name": 2, "graph": 1}}
    with pytest.raises(
        PanglossInitialisationError,
        match=r"The profiles also, who each weigh 2 .* set RECONCILE_PROFILE",
    ):
        settings.profile(given(VECTORS_PROFILES=profiles))
    assert (
        settings.profile(given(VECTORS_PROFILES=profiles, RECONCILE_PROFILE="who"))
        == "who"
    )
    # (the default profile, the parts at their own weights: the graph alone)
    assert settings.profile(given(VECTORS_PROFILES=None)) == "default"


def test_a_profile_named_is_the_one():
    profiles = {"who": {"name": 1, "graph": 0.25}, "near": {"graph": 1}}
    assert (
        settings.profile(given(VECTORS_PROFILES=profiles, RECONCILE_PROFILE="near"))
        == "near"
    )


def test_a_profile_named_that_does_not_exist_is_refused_with_the_profiles_there_are():
    with pytest.raises(
        PanglossInitialisationError,
        match=r"RECONCILE_PROFILE names 'nope', which is not a profile: the profiles are default, who",
    ):
        settings.profile(
            given(VECTORS_PROFILES={"who": {"name": 1}}, RECONCILE_PROFILE="nope")
        )


def test_a_profile_named_that_weighs_no_part_that_knows_unknowns_is_refused():
    with pytest.raises(
        PanglossInitialisationError,
        match=r"RECONCILE_PROFILE names 'when', which weighs no part that can say what an unknown would be "
        r"\(graph, name\)",
    ):
        settings.profile(
            given(VECTORS_PROFILES={"when": {"time": 1}}, RECONCILE_PROFILE="when")
        )


def test_no_profile_that_weighs_a_part_that_knows_unknowns_is_refused_with_what_to_set(
    monkeypatch,
):
    monkeypatch.setattr(parts, "_PARTS", {"time": Plain("time", 1.0)})
    with pytest.raises(
        PanglossInitialisationError,
        match=r"No profile weighs a part that can say what an unknown would be \(none is registered.*"
        r"set RECONCILE_PROFILE",
    ):
        settings.profile(given(VECTORS_PROFILES=None))


# -- RECONCILE_FETCH -----------------------------------------------------------------------------------------------


def test_fetch_is_50_unless_given():
    assert settings.fetch(given()) == 50
    assert settings.fetch(given(RECONCILE_FETCH=7)) == 7


@pytest.mark.parametrize("value", [0, -1, True, 2.5, "50", 1001])
def test_a_fetch_that_is_not_a_whole_number_from_1_to_1000_is_refused(value):
    assert settings.fetch(given(RECONCILE_FETCH=1000)) == 1000
    with pytest.raises(
        PanglossInitialisationError,
        match=r"RECONCILE_FETCH is a whole number from 1 to 1,000 .*, not",
    ):
        settings.fetch(given(RECONCILE_FETCH=value))


# -- RECONCILE_MOST_UNKNOWNS, RECONCILE_REASONS -----------------------------------------------------------------------


def test_most_unknowns_is_20_and_reasons_5_unless_given():
    assert settings.most_unknowns(given()) == 20
    assert settings.most_unknowns(given(RECONCILE_MOST_UNKNOWNS=3)) == 3
    assert settings.reasons(given()) == 5
    assert settings.reasons(given(RECONCILE_REASONS=0)) == 0


@pytest.mark.parametrize("value", [0, -1, True, 2.5, "20"])
def test_a_most_unknowns_that_is_not_a_whole_number_of_1_or_more_is_refused(value):
    with pytest.raises(
        PanglossInitialisationError,
        match=r"RECONCILE_MOST_UNKNOWNS is a whole number of 1 or more .*, not",
    ):
        settings.most_unknowns(given(RECONCILE_MOST_UNKNOWNS=value))


@pytest.mark.parametrize("value", [-1, True, 2.5, "5"])
def test_reasons_that_are_not_a_whole_number_of_0_or_more_are_refused(value):
    with pytest.raises(
        PanglossInitialisationError,
        match=r"RECONCILE_REASONS is a whole number of 0 or more .*, not",
    ):
        settings.reasons(given(RECONCILE_REASONS=value))


# -- RECONCILE_WEIGHTS ---------------------------------------------------------------------------------------------

WHO = {"who": {"name": 1, "graph": 0.25}}


def test_the_weights_are_the_profile_s_with_those_given_over_them_and_shared_at_1_5():
    assert settings.weights(given(VECTORS_PROFILES=WHO)) == {
        "graph": 0.25,
        "name": 1.0,
        "shared": 1.5,
    }
    assert settings.weights(
        given(VECTORS_PROFILES=WHO, RECONCILE_WEIGHTS={"graph": 1, "time": 0.5})
    ) == {"graph": 1.0, "name": 1.0, "shared": 1.5, "time": 0.5}
    # (a part given 0 counts for nothing)
    assert settings.weights(
        given(VECTORS_PROFILES=WHO, RECONCILE_WEIGHTS={"graph": 0})
    ) == {"name": 1.0, "shared": 1.5}
    assert settings.weights(
        given(VECTORS_PROFILES=WHO, RECONCILE_WEIGHTS={"shared": 2})
    ) == {"graph": 0.25, "name": 1.0, "shared": 2.0}


def test_shared_at_0_gives_phase_10_s_weights_exactly():
    assert settings.weights(
        given(VECTORS_PROFILES=WHO, RECONCILE_WEIGHTS={"shared": 0})
    ) == {"graph": 0.25, "name": 1.0}


def test_a_weight_of_a_name_that_is_no_part_is_refused_with_what_may_be_named():
    with pytest.raises(
        PanglossInitialisationError,
        match=r"RECONCILE_WEIGHTS names 'colour', which is not a part: what may be named is the parts "
        r"\(graph, name, time\) and shared",
    ):
        settings.weights(given(VECTORS_PROFILES=WHO, RECONCILE_WEIGHTS={"colour": 1}))


@pytest.mark.parametrize("value", [-0.5, True, "1"])
@pytest.mark.parametrize("name", ["name", "shared"])
def test_a_weight_that_is_not_a_number_of_0_or_more_is_refused(name, value):
    with pytest.raises(
        PanglossInitialisationError,
        match=rf"RECONCILE_WEIGHTS\['{name}'\] is a weight of 0 or more, not",
    ):
        settings.weights(given(VECTORS_PROFILES=WHO, RECONCILE_WEIGHTS={name: value}))


@pytest.mark.parametrize(
    "others", [{"time": 1}, {"shared": 1}], ids=["another part", "shared"]
)
def test_weights_that_leave_no_part_the_profile_weighs_above_0_are_refused(others):
    """(`shared` alone is not enough: with no part nothing is found)"""
    with pytest.raises(
        PanglossInitialisationError,
        match=r"RECONCILE_WEIGHTS gives each part the profile 'who' weighs \(graph, name\) a weight of 0: .*"
        r"\(shared alone is not enough\)",
    ):
        settings.weights(
            given(
                VECTORS_PROFILES=WHO,
                RECONCILE_WEIGHTS={"name": 0, "graph": 0, **others},
            )
        )


def test_weights_that_are_not_a_mapping_are_refused():
    with pytest.raises(
        PanglossInitialisationError,
        match=r"RECONCILE_WEIGHTS is a weight for each part",
    ):
        settings.weights(given(VECTORS_PROFILES=WHO, RECONCILE_WEIGHTS=[1, 2]))


# -- RECONCILE_LEAST_SCORE ------------------------------------------------------------------------------------------


def test_the_least_score_is_0_15_unless_given():
    assert settings.least_score(given()) == 0.15
    assert settings.least_score(given(RECONCILE_LEAST_SCORE=0)) == 0.0
    assert settings.least_score(given(RECONCILE_LEAST_SCORE=1)) == 1.0
    assert settings.least_score(given(RECONCILE_LEAST_SCORE=0.45)) == 0.45


@pytest.mark.parametrize("value", [-0.1, 1.5, True, "0.2", None])
def test_a_least_score_that_is_not_a_number_from_0_to_1_is_refused(value):
    with pytest.raises(
        PanglossInitialisationError,
        match=r"RECONCILE_LEAST_SCORE is a number from 0 to 1 \(the least score of a candidate given\), not",
    ):
        settings.least_score(given(RECONCILE_LEAST_SCORE=value))


# -- RECONCILE_KEEP_DECISIONS and RECONCILE_SHOWN_FOR ---------------------------------------------------------------


def test_decisions_are_kept_for_30_minutes_unless_given():
    assert settings.keep_decisions(given()) is True
    assert settings.keep_decisions(given(RECONCILE_KEEP_DECISIONS=False)) is False
    assert settings.shown_for(given()) == 30.0
    assert settings.shown_for(given(RECONCILE_SHOWN_FOR=5)) == 5.0
    assert settings.shown_for(given(RECONCILE_SHOWN_FOR=0.5)) == 0.5


@pytest.mark.parametrize("value", [1, 0, "yes", None])
def test_keep_decisions_that_is_not_true_or_false_is_refused(value):
    with pytest.raises(
        PanglossInitialisationError,
        match=r"RECONCILE_KEEP_DECISIONS is True or False \(whether what the stored route offers, and what is "
        r"chosen of it, is kept\), not",
    ):
        settings.keep_decisions(given(RECONCILE_KEEP_DECISIONS=value))


# -- RECONCILE_LEARN_FROM_SUGGESTIONS (step 10.5f) -------------------------------------------------------------------


def test_learning_from_confirmed_suggestions_is_on_unless_given():
    assert settings.learn_from_suggestions(given()) is True
    assert (
        settings.learn_from_suggestions(given(RECONCILE_LEARN_FROM_SUGGESTIONS=False))
        is False
    )


@pytest.mark.parametrize("value", [1, 0, "yes", None])
def test_learn_from_suggestions_that_is_not_true_or_false_is_refused(value):
    with pytest.raises(
        PanglossInitialisationError,
        match=r"RECONCILE_LEARN_FROM_SUGGESTIONS is True or False \(whether a fit learns from the examples a "
        r"person's confirmation of a suggestion of the worker made\), not",
    ):
        settings.learn_from_suggestions(given(RECONCILE_LEARN_FROM_SUGGESTIONS=value))


@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan"), True, "30", None])
def test_a_shown_for_that_is_not_a_finite_number_above_0_is_refused(value):
    with pytest.raises(
        PanglossInitialisationError,
        match=r"RECONCILE_SHOWN_FOR is a finite number of minutes above 0 \(how long what was offered is an "
        r"example of a decision made of it\), not",
    ):
        settings.shown_for(given(RECONCILE_SHOWN_FOR=value))


# -- RECONCILE_LEARN_FROM ------------------------------------------------------------------------------------------


def test_a_fit_is_put_in_use_from_100_decisions_unless_given():
    assert settings.learn_from(given()) == 100
    assert settings.learn_from(given(RECONCILE_LEARN_FROM=1)) == 1
    assert settings.learn_from(given(RECONCILE_LEARN_FROM=5000)) == 5000


@pytest.mark.parametrize("value", [0, -1, 1.5, True, "100", None])
def test_a_learn_from_that_is_not_a_whole_number_of_1_or_more_is_refused(value):
    with pytest.raises(
        PanglossInitialisationError,
        match=r"RECONCILE_LEARN_FROM is a whole number of 1 or more \(the fewest decisions a fit is made of for it "
        r"to be put in use\), not",
    ):
        settings.learn_from(given(RECONCILE_LEARN_FROM=value))


# -- RECONCILE_NEW_ABOVE -------------------------------------------------------------------------------------------


def test_probably_new_is_above_0_5_unless_given():
    assert settings.new_above(given()) == 0.5
    assert settings.new_above(given(RECONCILE_NEW_ABOVE=0)) == 0.0
    assert settings.new_above(given(RECONCILE_NEW_ABOVE=1)) == 1.0
    assert settings.new_above(given(RECONCILE_NEW_ABOVE=0.8)) == 0.8


@pytest.mark.parametrize("value", [-0.1, 1.5, True, "0.5", None, float("nan")])
def test_a_new_above_that_is_not_a_number_from_0_to_1_is_refused(value):
    with pytest.raises(
        PanglossInitialisationError,
        match=r"RECONCILE_NEW_ABOVE is a number from 0 to 1 \(the likelihood that the one meant is none of those "
        r"offered, above which the answer says it is probably someone new\), not",
    ):
        settings.new_above(given(RECONCILE_NEW_ABOVE=value))


# -- the structural network, not the actual one ---------------------------------------------------------------------


@pytest.fixture
def actual_registered(monkeypatch):
    """The parts of these tests and `actual`, which can say what an unknown would be (as `pangloss-fastrp`'s does)"""
    monkeypatch.setitem(parts._PARTS, "actual", Knowing("actual"))


def warned_of_network(settings_given: SimpleNamespace) -> list[str]:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        settings.check_network(settings_given)
    return [
        str(warning.message)
        for warning in caught
        if issubclass(warning.category, PanglossModelWarning)
    ]


@pytest.mark.parametrize(
    "weights", [{"actual": 1}, {"actual": 1, "name": 1}], ids=["alone", "with-name"]
)
def test_a_profile_that_weighs_the_actual_network_and_not_the_graph_is_warned_of(
    actual_registered, weights
):
    with pytest.warns(
        PanglossModelWarning,
        match=r"RECONCILE_PROFILE names 'who_met', which weighs the part 'actual' and not the part 'graph': the "
        r"actual network leaves out what is denied, and being named together in a denial is evidence of who someone "
        r"is\. Weigh 'graph' in 'who_met' \(VECTORS_PROFILES\), or set RECONCILE_PROFILE to a profile that weighs it",
    ):
        settings.check_network(
            given(VECTORS_PROFILES={"who_met": weights}, RECONCILE_PROFILE="who_met")
        )


def test_a_profile_chosen_without_a_name_is_warned_of_as_chosen(actual_registered):
    # (the actual part counts as one that can say what an unknown would be: of the name and the actual network, two,
    # beats `default`'s one, the graph)
    with pytest.warns(
        PanglossModelWarning,
        match=r"The profile candidates are found by, chosen without RECONCILE_PROFILE, is 'who_met', which weighs "
        r"the part 'actual' and not the part 'graph'",
    ):
        settings.check_network(
            given(VECTORS_PROFILES={"who_met": {"actual": 1, "name": 1}})
        )


@pytest.mark.parametrize(
    "weights",
    [{"graph": 0.25, "actual": 1, "name": 1}, {"graph": 1}, {"name": 1, "graph": 0.25}],
    ids=["both", "graph-alone", "name-and-graph"],
)
def test_a_profile_that_weighs_the_graph_is_not_warned_of_whether_or_not_it_weighs_the_actual_network(
    actual_registered, weights
):
    assert (
        warned_of_network(
            given(VECTORS_PROFILES={"who": weights}, RECONCILE_PROFILE="who")
        )
        == []
    )


def test_nothing_is_warned_of_when_no_part_actual_is_registered():
    assert "actual" not in parts.parts()
    assert (
        warned_of_network(
            given(VECTORS_PROFILES={"who": {"name": 1}}, RECONCILE_PROFILE="who")
        )
        == []
    )


# -- at initialise() -----------------------------------------------------------------------------------------------


@no_type_check
def people():
    class Person(Entity):
        pass

    initialise()


@pytest.mark.parametrize(
    "setting",
    [
        "RECONCILE_FETCH",
        "RECONCILE_MOST_UNKNOWNS",
        "RECONCILE_REASONS",
        "RECONCILE_LEAST_SCORE",
        "RECONCILE_KEEP_DECISIONS",
        "RECONCILE_SHOWN_FOR",
        "RECONCILE_LEARN_FROM",
        "RECONCILE_LEARN_FROM_SUGGESTIONS",
        "RECONCILE_NEW_ABOVE",
    ],
)
def test_each_setting_is_checked_at_initialise(project_settings, setting):
    configure(
        project_settings(INSTALLED_APPS=APPS, VECTORS_PROFILES=WHO, **{setting: -1})
    )
    with pytest.raises(PanglossInitialisationError, match=setting):
        people()


def test_the_settings_are_checked_at_initialise_when_the_app_is_installed(
    project_settings,
):
    configure(
        project_settings(INSTALLED_APPS=APPS, VECTORS_PROFILES=WHO, RECONCILE_FETCH=0)
    )
    with pytest.raises(PanglossInitialisationError, match="RECONCILE_FETCH"):
        people()


def test_a_profile_that_is_wrong_is_refused_at_initialise(project_settings):
    configure(
        project_settings(
            INSTALLED_APPS=APPS, VECTORS_PROFILES=WHO, RECONCILE_PROFILE="nope"
        )
    )
    with pytest.raises(PanglossInitialisationError, match="RECONCILE_PROFILE"):
        people()


def test_nothing_is_checked_when_the_app_is_not_installed(project_settings):
    configure(
        project_settings(
            INSTALLED_APPS=["pangloss_vectors"],
            VECTORS_PROFILES=WHO,
            RECONCILE_FETCH=0,
        )
    )
    people()


def test_settings_that_are_right_pass_at_initialise(project_settings):
    configure(
        project_settings(
            INSTALLED_APPS=APPS,
            VECTORS_PROFILES=WHO,
            RECONCILE_WEIGHTS={"name": 2, "shared": 0.5},
            RECONCILE_LEAST_SCORE=0.3,
            RECONCILE_NEW_ABOVE=0.7,
        )
    )
    people()


def test_a_profile_of_the_actual_network_alone_is_warned_of_at_initialise_and_the_project_still_starts(
    project_settings, actual_registered
):
    configure(
        project_settings(
            INSTALLED_APPS=APPS,
            VECTORS_PROFILES={"who_met": {"actual": 1}},
            RECONCILE_PROFILE="who_met",
        )
    )
    with pytest.warns(PanglossModelWarning, match="RECONCILE_PROFILE names 'who_met'"):
        people()
    assert ModelRegistry._model_dict["Person"].Create is not None
