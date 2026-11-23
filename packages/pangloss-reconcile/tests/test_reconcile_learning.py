"""What reconciliation learns from (`learning.py`, step 11.5), with no database: the examples of kept rows, the head
of a list, and the rows that lack a part"""

import math

import pytest
from pangloss_reconcile import learning
from pangloss_reconcile.learning import Decision

WEIGHTS = {"graph": 0.25, "name": 1.0, "shared": 1.5}
FEATURES = ["graph", "name", "shared"]


def row(id: str, score: float, displayed: bool = True, **scores: float) -> dict:
    return {
        "id": id,
        "type": "Person",
        "scores": scores or {"graph": score / 2, "name": score, "shared": 0.0},
        "shared": 0,
        "score": score,
        "displayed": displayed,
    }


def test_the_ranking_features_are_the_parts_by_name_then_shared_when_it_weighs():
    assert learning.ranking_features(WEIGHTS) == FEATURES
    assert learning.ranking_features({"name": 1.0, "graph": 0.25}) == ["graph", "name"]
    assert learning.ranking_features({"name": 1.0, "graph": 0, "shared": 0}) == ["name"]


def test_the_none_features_are_the_head_of_the_list_and_the_best_ones_own():
    assert learning.none_features(FEATURES) == [
        "best",
        "gap",
        "best_graph",
        "best_name",
        "best_shared",
        "rows",
    ]


def test_a_ranking_example_for_each_row_in_the_features_order_yes_on_the_one_taken():
    decision = Decision(
        "s1",
        (
            row("a", 0.9, name=0.9, graph=0.4, shared=0.3),
            row("b", 0.5, displayed=False, name=0.5, graph=0.1, shared=0.0),
        ),
        "b",
    )
    found = learning.ranking_examples([decision], FEATURES)
    assert [list(e.features) for e in found] == [FEATURES, FEATURES]
    assert [e.features for e in found] == [
        {"graph": 0.4, "name": 0.9, "shared": 0.3},
        {"graph": 0.1, "name": 0.5, "shared": 0.0},
    ]
    assert [e.yes for e in found] == [False, True]
    assert {e.group for e in found} == {"s1"}


def test_no_ranking_example_is_yes_when_nothing_was_taken():
    decision = Decision("s1", (row("a", 0.9), row("b", 0.5)), None)
    assert [e.yes for e in learning.ranking_examples([decision], FEATURES)] == [
        False,
        False,
    ]


def test_the_head_of_no_row_or_of_none_displayed_is_none():
    assert learning.head_features([]) is None
    assert learning.head_features([row("a", 0.9, displayed=False)]) is None


def test_the_head_of_one_row_has_its_score_as_its_gap():
    found = learning.head_features([row("a", 0.8, name=0.8, graph=0.2, shared=0.1)])
    assert found == {
        "best": 0.8,
        "gap": 0.8,
        "best_graph": 0.2,
        "best_name": 0.8,
        "best_shared": 0.1,
        "rows": math.log(2),
    }


def test_the_head_of_several_is_by_the_hand_set_score_of_those_displayed_only():
    rows = [
        row("hidden", 0.95, displayed=False, name=0.95, graph=0.0, shared=0.0),
        row("second", 0.6, name=0.6, graph=0.3, shared=0.0),
        row("first", 0.7, name=0.7, graph=0.1, shared=0.2),
        row("third", 0.2, name=0.2, graph=0.0, shared=0.0),
    ]
    found = learning.head_features(rows)
    assert found is not None
    assert found["best"] == 0.7
    assert found["gap"] == pytest.approx(0.1)
    assert (found["best_name"], found["best_graph"], found["best_shared"]) == (
        0.7,
        0.1,
        0.2,
    )
    assert found["rows"] == math.log(4)
    assert [r["id"] for r in learning.head(rows)] == ["first", "second", "third"]


def test_none_of_these_is_yes_when_nothing_was_taken():
    assert learning.none_taken(Decision("s", (row("a", 0.9),), None))


def test_none_of_these_is_yes_when_the_row_taken_was_not_displayed():
    rows = (row("a", 0.9), row("b", 0.3, displayed=False))
    assert learning.none_taken(Decision("s", rows, "b"))


def test_none_of_these_is_no_when_a_displayed_row_was_taken():
    rows = (row("a", 0.9), row("b", 0.3, displayed=False))
    assert not learning.none_taken(Decision("s", rows, "a"))


def test_a_none_example_for_each_decision_with_a_row_displayed():
    none = learning.none_features(FEATURES)
    decisions = [
        Decision("taken", (row("a", 0.9), row("b", 0.4)), "a"),
        Decision("new", (row("a", 0.3),), None),
        Decision("hidden", (row("a", 0.9, displayed=False),), "a"),
        Decision("empty", (), None),
    ]
    found = learning.none_examples(decisions, none)
    assert [(e.group, e.yes) for e in found] == [("taken", False), ("new", True)]
    assert all(list(e.features) == none for e in found)
    assert found[0].features["gap"] == pytest.approx(0.5)


def test_rows_lacking_a_part_are_told_apart():
    whole = [row("a", 0.9), row("b", 0.5)]
    assert learning.lacking(whole, FEATURES) == []
    # (the unknown had no vector of the graph part: no row has its cosine)
    without = [row("a", 0.9, name=0.9, shared=0.0), row("b", 0.5, name=0.5, shared=0.0)]
    assert learning.lacking(without, FEATURES) == ["graph"]
    assert learning.lacking([], FEATURES) == []
