"""What to suggest for an unknown (`pangloss_reconcile.suggest`, step 10.5c of
implementation_docs/similarity-build-plan.md), with no database: the percentages; each reason for suggesting nothing;
the most and the share of the best; `decide_for` with the settings and a fit's "none of these", which is the stored
route's `probablyNew` by the same function; the settings and their refusals by message; the dialog's limit said once
(`candidates.DISPLAYED`, the interface's `LIMIT`)."""

import random
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any, no_type_check

import pytest
from pangloss_core.settings import configure
from pangloss_learn import Model
from pangloss_models import Entity, initialise
from pangloss_models.exceptions import PanglossInitialisationError
from pangloss_reconcile import api, decisions, learning, settings
from pangloss_reconcile.candidates import DISPLAYED, KEPT, Candidate, Found
from pangloss_reconcile.suggest import (
    Alternative,
    Decision,
    decide,
    decide_for,
    percentages,
)
from pangloss_vectors import parts
from pangloss_vectors.parts import Unknown
from test_reconcile_settings import WHO, Knowing, Plain

# -- the percentages ------------------------------------------------------------------------------------------------


def test_the_percentages_are_whole_sum_to_100_each_at_least_1_in_the_order_of_the_scores():
    assert percentages([0.9, 0.6, 0.3]) == [50, 33, 17]
    assert percentages([0.3, 0.9, 0.6]) == [17, 50, 33]
    assert percentages([0.99, 0.01]) == [98, 2]
    # (a score far below the others still has its 1 per cent)
    assert percentages([1.0, 0.0001]) == [99, 1]


def test_one_alternative_is_100_and_none_is_none():
    assert percentages([0.42]) == [100]
    assert percentages([0.0]) == [100]
    assert percentages([]) == []


def test_ties_of_the_remainders_go_to_the_earlier():
    assert percentages([1, 1, 1]) == [34, 33, 33]
    assert percentages([0.5, 0.5, 0.5, 0.5, 0.5, 0.5]) == [17, 17, 17, 17, 16, 16]


def test_scores_of_nothing_or_less_share_equally():
    assert percentages([0, 0]) == [50, 50]
    assert percentages([0, -1, 0]) == [34, 33, 33]
    # (a score below 0 is taken as nothing beside one that is something)
    assert percentages([0.8, -0.5]) == [99, 1]


def test_100_alternatives_have_1_per_cent_each_and_101_are_refused():
    assert percentages([random.random() for _ in range(100)]) == [1] * 100
    with pytest.raises(ValueError, match="More than 100 alternatives"):
        percentages([0.5] * 101)


def test_over_random_scores_the_percentages_sum_to_100_each_at_least_1_and_follow_the_scores():
    """(a seeded loop: hypothesis is not used in this repository)"""
    rng = random.Random(10_5)
    for _ in range(2000):
        count = rng.randint(1, 100)
        scores = [
            rng.choice([0.0, rng.random(), round(rng.random(), 1)])
            for _ in range(count)
        ]
        found = percentages(scores)
        assert len(found) == count
        assert sum(found) == 100
        assert min(found) >= 1
        # (a higher score never has fewer per cent; equal scores differ by at most 1, the earlier not fewer)
        for a in range(count):
            for b in range(a + 1, count):
                if scores[a] > scores[b]:
                    assert found[a] >= found[b], (scores, found)
                elif scores[a] == scores[b]:
                    assert 0 <= found[a] - found[b] <= 1, (scores, found)


# -- decide ---------------------------------------------------------------------------------------------------------


def three(*scores: float) -> list[tuple[str, str, float]]:
    return [(f"p{n}", "Person", score) for n, score in enumerate(scores)]


DEFAULTS: dict[str, Any] = {"above": 0.6, "most": 3, "within": 0.7}


def test_nothing_with_no_candidate_none():
    assert decide([], **DEFAULTS) == Decision((), "none")
    assert not decide([], **DEFAULTS).suggested


def test_nothing_when_the_best_is_under_the_threshold_low():
    assert decide(three(0.59, 0.5), **DEFAULTS) == Decision((), "low")
    # (at the threshold, something)
    assert decide(three(0.6), **DEFAULTS).reason == "suggested"


def test_nothing_when_a_fit_says_the_one_meant_is_probably_new_new():
    assert decide(three(0.9, 0.8), **DEFAULTS, probably_new=True) == Decision((), "new")
    # (a list under the threshold is `low`, whatever the fit says)
    assert decide(three(0.3), **DEFAULTS, probably_new=True).reason == "low"


def test_the_most_alternatives_are_the_best_in_their_order():
    found = decide(three(0.9, 0.85, 0.8, 0.75, 0.7), **DEFAULTS)
    assert found.reason == "suggested" and found.suggested
    assert [a.id for a in found.alternatives] == ["p0", "p1", "p2"]
    assert sum(a.percent for a in found.alternatives) == 100
    assert decide(three(0.9, 0.85, 0.8), above=0.6, most=1, within=0.7) == Decision(
        (Alternative("p0", "Person", 100),), "suggested"
    )


def test_within_0_keeps_every_one_up_to_the_most_and_1_those_equal_to_the_best():
    scores = three(0.9, 0.9, 0.5, 0.1)
    kept = decide(scores, above=0.6, most=10, within=0.0)
    assert [a.id for a in kept.alternatives] == ["p0", "p1", "p2", "p3"]
    kept = decide(scores, above=0.6, most=10, within=1.0)
    assert [a.id for a in kept.alternatives] == ["p0", "p1"]
    assert [a.percent for a in kept.alternatives] == [50, 50]
    # (at the defaults: 0.63 of 0.9 is kept, 0.62 is not)
    kept = decide(three(0.9, 0.63, 0.62), **DEFAULTS)
    assert [a.id for a in kept.alternatives] == ["p0", "p1"]


def test_the_best_is_always_kept():
    for within in (0.0, 0.5, 1.0):
        for most in (1, 3, 10):
            found = decide(three(0.61, 0.2), above=0.6, most=most, within=within)
            assert found.alternatives[0].id == "p0"
    # (and a most of 0 or less is taken as 1)
    found = decide(three(0.9, 0.9), above=0.6, most=0, within=0.7)
    assert [a.id for a in found.alternatives] == ["p0"]


# -- decide_for -----------------------------------------------------------------------------------------------------


def found_of(*scores: float) -> Found:
    return Found(
        Unknown(id="u", type="Person", label="Jon Smyth"),
        [
            Candidate(f"p{n}", "Person", score, {"name": score, "graph": score / 2})
            for n, score in enumerate(scores)
        ],
    )


# (a "none of these" model that weighs the best score alone: the lower it is, the likelier "none of these")
NONE_MODEL = Model(features=("best",), weights=(-10.0,), constant=7.0)


@pytest.fixture
def project(project_settings):
    def made(**values: Any) -> None:
        configure(project_settings(**values))

    return made


def test_decide_for_takes_the_list_as_the_dialog_is_answered_and_the_settings(
    project,
):
    project()
    # (the first five alone: a sixth that would be kept is not asked about)
    found = decide_for(found_of(0.9, 0.9, 0.9, 0.9, 0.9, 0.9), None)
    assert [a.id for a in found.alternatives] == ["p0", "p1", "p2"]
    assert decide_for(found_of(0.59), None).reason == "low"
    assert decide_for(found_of(), None).reason == "none"
    project(
        RECONCILE_SUGGEST_ABOVE=0.5,
        RECONCILE_SUGGEST_MOST=5,
        RECONCILE_SUGGEST_WITHIN=0.0,
    )
    found = decide_for(found_of(0.55, 0.5, 0.4, 0.3, 0.2, 0.1), None)
    assert [a.id for a in found.alternatives] == ["p0", "p1", "p2", "p3", "p4"]


def test_decide_for_suggests_nothing_when_the_fit_says_what_the_stored_route_says_probably_new(
    project,
):
    project()
    weak, strong = found_of(0.65, 0.6), found_of(0.95, 0.6)
    for found, new in ((weak, True), (strong, False)):
        said = learning.probably_new(
            NONE_MODEL, [(c.score, c.scores) for c in found.candidates], 0.5
        )
        assert said is not None
        likelihood, probably = said
        assert probably is new
        # (the stored route's answer, of the same candidates, says the same)
        answer = {
            "unknowns": [
                {
                    "id": "u",
                    "candidates": [
                        {"id": c.id, "score": c.score, "scores": c.scores}
                        for c in found.candidates
                    ],
                }
            ]
        }
        now = {name: "today" for name in decisions.SIGNATURES}
        fit = {"id": "f", "at": None, "decisions": 100, "none": NONE_MODEL.to_json()}
        (said,) = api.none_of_these(answer, {**fit, **now}, now, 0.5)["unknowns"]
        assert said["probablyNew"] is new and said["new"] == likelihood
    assert decide_for(weak, NONE_MODEL) == Decision((), "new")
    assert decide_for(weak, None).reason == "suggested"
    assert decide_for(strong, NONE_MODEL).reason == "suggested"
    # (`RECONCILE_NEW_ABOVE` says where "probably new" begins, for both)
    project(RECONCILE_NEW_ABOVE=0.99)
    assert decide_for(weak, NONE_MODEL).reason == "suggested"


def test_decide_for_a_fit_that_gives_no_figure_says_nothing():
    model = Model(features=("best_time",), weights=(1.0,), constant=0.0)
    assert decide_for(found_of(0.9), model).reason == "suggested"


# -- the settings ---------------------------------------------------------------------------------------------------


def given(**values: Any) -> SimpleNamespace:
    return SimpleNamespace(**values)


def test_the_settings_are_0_6_3_and_0_7_unless_given():
    assert settings.suggest_above(given()) == 0.6
    assert settings.suggest_most(given()) == 3
    assert settings.suggest_within(given()) == 0.7
    assert settings.suggest_above(given(RECONCILE_SUGGEST_ABOVE=1)) == 1.0
    assert settings.suggest_most(given(RECONCILE_SUGGEST_MOST=10)) == 10
    assert settings.suggest_within(given(RECONCILE_SUGGEST_WITHIN=0)) == 0.0


@pytest.mark.parametrize("value", [-0.1, 1.5, True, "0.6", None])
def test_a_threshold_that_is_not_a_number_from_0_to_1_is_refused(value):
    with pytest.raises(
        PanglossInitialisationError,
        match=r"RECONCILE_SUGGEST_ABOVE is a number from 0 to 1 \(the least score of the best candidate for a "
        r"suggestion to be made\), not",
    ):
        settings.suggest_above(given(RECONCILE_SUGGEST_ABOVE=value))


@pytest.mark.parametrize("value", [0, 11, -1, True, 2.0, "3"])
def test_a_most_that_is_not_a_whole_number_from_1_to_10_is_refused(value):
    with pytest.raises(
        PanglossInitialisationError,
        match=r"RECONCILE_SUGGEST_MOST is a whole number from 1 to 10 \(the most alternatives a suggestion has\), "
        r"not",
    ):
        settings.suggest_most(given(RECONCILE_SUGGEST_MOST=value))


@pytest.mark.parametrize("value", [-0.1, 1.01, False, "0.7"])
def test_a_share_of_the_best_that_is_not_a_number_from_0_to_1_is_refused(value):
    with pytest.raises(
        PanglossInitialisationError,
        match=r"RECONCILE_SUGGEST_WITHIN is a number from 0 to 1 \(the least share of the best candidate's score "
        r"that another suggested with it scores\), not",
    ):
        settings.suggest_within(given(RECONCILE_SUGGEST_WITHIN=value))


@pytest.fixture
def registered(monkeypatch):
    """(the parts of `test_reconcile_settings.py`)"""
    monkeypatch.setattr(
        parts,
        "_PARTS",
        {
            "graph": Knowing("graph", 1.0),
            "name": Knowing("name"),
            "time": Plain("time"),
        },
    )


@no_type_check
def people() -> None:
    class Person(Entity):
        pass

    initialise()


@pytest.mark.parametrize(
    "setting",
    ["RECONCILE_SUGGEST_ABOVE", "RECONCILE_SUGGEST_MOST", "RECONCILE_SUGGEST_WITHIN"],
)
def test_each_setting_is_checked_at_initialise(registered, project, setting):
    apps = ["pangloss_vectors", "pangloss_reconcile"]
    project(INSTALLED_APPS=apps, VECTORS_PROFILES=WHO, **{setting: -1})
    with pytest.raises(PanglossInitialisationError, match=setting):
        people()
    from pangloss_models import ModelRegistry

    ModelRegistry._reset()
    project(
        INSTALLED_APPS=apps,
        VECTORS_PROFILES=WHO,
        RECONCILE_SUGGEST_ABOVE=0.5,
        RECONCILE_SUGGEST_MOST=1,
        RECONCILE_SUGGEST_WITHIN=1,
    )
    people()


# -- the dialog's limit -----------------------------------------------------------------------------------------------


def test_the_dialog_s_limit_is_said_once_and_the_interface_asks_for_it():
    import pangloss_reconcile

    api_ts = (
        Path(pangloss_reconcile.__file__).parent / "interface" / "src" / "api.ts"
    ).read_text()
    (limit,) = re.findall(r"export const LIMIT = (\d+);", api_ts)
    assert int(limit) == DISPLAYED == 5
    # (a row displayed is always among those kept: `candidates.ranked`)
    assert DISPLAYED <= KEPT
