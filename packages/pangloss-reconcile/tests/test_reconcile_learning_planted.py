"""The seeded floor of learning (implementation_docs/similarity-build-plan.md, "Testing the next phases", 4; step
11.7), with no database: what `notes/similarity-evaluation/planted.py learn` measures through the service, done in
memory on the planted world of `test_reconcile_planted.py` (1,500 people; name 1, graph 0.25, shared 1.5).

Each mention's candidates are scored as that file scores them, and the ten best (`candidates.KEPT`, by score then
id) kept as rows exactly as `decisions.rows_of` makes them, the first five not under the least score (0.15)
displayed. Of every second mention the person is taken out of the candidates before the ten are cut ("someone
new"). The decision's `taken` is the person if among the rows, else None. The mentions are dealt in two halves (of
each kind, kept and taken out, the even places to one half and the odd to the other); the "none of these" model is
fitted on one half (`learning.none_examples`, `pangloss_learn.fit`, the ridge of `fits.py`) and asked of the other
(`learning.none_likelihood`), and the other way round. How often it calls a held-out list rightly at a half is set
against always answering the commoner of the held-out lists, and its AUC against the best score's alone (a lower
best, more likely none)"""

import bisect
import types
from collections.abc import Sequence

import pytest
from pangloss_learn import fit
from pangloss_reconcile import decisions, learning
from pangloss_reconcile.candidates import DISPLAYED, KEPT, Candidate
from pangloss_reconcile.fits import RIDGE
from pangloss_reconcile.learning import Decision
from pangloss_reconcile.score import ranked
from pangloss_reconcile.settings import DEFAULT_LEAST_SCORE
from test_reconcile_planted import WITH_SHARED, scored

SEEDS = (1, 2, 3)

# The floors, a little under what was measured here on seeds 1, 2 and 3 (2026-11-23, 287, 291 and 292 mentions, each
# with a row displayed; 143, 145 and 146 of them "none of these", every mention kept having its person among the ten):
# called rightly at a half 82.2%, 79.7%, 78.1%, always the commoner 50.2%, 50.2%, 50.0% (32.1, 29.6 and 28.1 points
# better); the model's AUC 0.884, 0.865, 0.858, the best score's alone 0.822, 0.785, 0.826 (0.062, 0.080 and 0.031
# better)
RIGHT_GAIN = 0.25
AUC_FLOOR = 0.83
AUC_GAIN = 0.02


def decisions_of(seed: int) -> list[tuple[Decision, bool]]:
    """For each mention of the world of `seed`: its decision, and whether its person was taken out"""
    _, found = scored(seed, WITH_SHARED)
    made = []
    for n, (mention, candidates) in enumerate(found):
        gone = n % 2 == 1
        order = [
            id
            for id in ranked(
                {id: c.score for id, c in candidates.items()}, len(candidates)
            )
            if not (gone and id == mention.person)
        ][:KEPT]
        best = [
            Candidate(
                id,
                "Person",
                candidates[id].score,
                candidates[id].scores,
                # (`rows_of` keeps how many entities are shared: what they are does not matter here)
                tuple((f"shared-{k}", 1) for k in range(candidates[id].shared)),
            )
            for id in order
        ]
        displayed = [c.id for c in best if c.score >= DEFAULT_LEAST_SCORE][:DISPLAYED]
        rows = decisions.rows_of(types.SimpleNamespace(best=best), displayed)
        taken = mention.person if any(r["id"] == mention.person for r in rows) else None
        made.append((Decision(mention.id, tuple(rows), taken), gone))
    return made


def auc(yes: Sequence[float], no: Sequence[float]) -> float:
    """How likely a list of "none of these" is put above one that is not, by a figure (ties count a half)"""
    ordered = sorted(no)
    wins = sum(
        bisect.bisect_left(ordered, v)
        + 0.5 * (bisect.bisect_right(ordered, v) - bisect.bisect_left(ordered, v))
        for v in yes
    )
    return wins / (len(yes) * len(no))


def held_out(made: Sequence[tuple[Decision, bool]]) -> dict[str, float]:
    """The "none of these" model fitted on each half and asked of the other: of the held-out lists with a row
    displayed, how often it calls them rightly at a half, how often always answering their commoner does, its AUC
    and the best score's alone"""
    halves: list[list[Decision]] = [[], []]
    for kind in (False, True):
        of_kind = [decision for decision, gone in made if gone == kind]
        for place, decision in enumerate(of_kind):
            halves[place % 2].append(decision)
    features = learning.none_features(learning.ranking_features(WITH_SHARED))
    called: list[tuple[float, float, bool]] = []
    for fitted_on, asked in ((0, 1), (1, 0)):
        model = fit(
            learning.none_examples(halves[fitted_on], features), features, ridge=RIDGE
        )
        for decision in halves[asked]:
            likelihood = learning.none_likelihood(model, decision.rows)
            if likelihood is None:
                continue
            best = learning.head_features(decision.rows)
            assert best is not None
            called.append((likelihood, best["best"], learning.none_taken(decision)))
    yes = [c for c in called if c[2]]
    no = [c for c in called if not c[2]]
    return {
        "lists": len(called),
        "right": sum(1 for c in called if (c[0] >= 0.5) == c[2]) / len(called),
        "commoner": max(len(yes), len(no)) / len(called),
        "auc": auc([c[0] for c in yes], [c[0] for c in no]),
        "best_auc": auc([-c[1] for c in yes], [-c[1] for c in no]),
    }


@pytest.fixture(scope="module")
def made() -> dict[int, list[tuple[Decision, bool]]]:
    """(made once for the module: the decisions of each seed's world)"""
    return {seed: decisions_of(seed) for seed in SEEDS}


@pytest.mark.parametrize("seed", SEEDS)
def test_the_rows_kept_are_ten_at_most_by_score_then_id_and_five_displayed_at_most(
    made, seed
):
    for decision, gone in made[seed]:
        rows = decision.rows
        assert 0 < len(rows) <= KEPT
        assert list(rows) == sorted(rows, key=lambda r: (-r["score"], r["id"]))
        shown = [r for r in rows if r["displayed"]]
        assert len(shown) <= DISPLAYED
        assert all(r["score"] >= DEFAULT_LEAST_SCORE for r in shown)
        assert set(rows[0]) == {"id", "type", "scores", "shared", "score", "displayed"}
        if gone:
            assert decision.taken is None


@pytest.mark.parametrize("seed", SEEDS)
def test_none_of_these_is_called_rightly_more_often_than_the_commoner_answer(
    made, seed
):
    found = held_out(made[seed])
    assert found["right"] > found["commoner"] + RIGHT_GAIN, found


@pytest.mark.parametrize("seed", SEEDS)
def test_none_of_these_orders_the_lists_better_than_the_best_score_alone(made, seed):
    found = held_out(made[seed])
    assert found["auc"] > AUC_FLOOR, found
    assert found["auc"] > found["best_auc"] + AUC_GAIN, found
