"""`Found.best` beside `Found.candidates` (step 11.4): of one ranking by the hand-set score, the first ten of every
item found, whatever the least score and `limit`; the candidates, the first `limit` of those not under the least score.
A hand-made case, no database (`candidates.ranked`)"""

import pytest
from pangloss_reconcile.candidates import KEPT, ranked

WEIGHTS = {"name": 1.0}


def case(count: int) -> tuple[dict, dict, dict]:
    """`count` items, `p00` the nearest by name, each further than the one before, and from five on `p04b`, a twin of
    `p04` (a tie, which is ordered by id); the unknown's name vector `(1, 0)`"""
    vectors: dict[str, list[float]] = {}
    for n in range(count):
        vectors[f"p{n:02d}"] = [1.0, n / 4]
    if count > 4:
        vectors["p04b"] = vectors["p04"]
    hits = {id: "Person" for id in reversed(list(vectors))}
    return {"name": [1.0, 0.0]}, hits, {"name": vectors}


def test_best_is_the_first_ten_of_every_item_by_score_then_id_and_candidates_a_head_of_it():
    unknown, hits, of_part = case(14)

    best, candidates = ranked(unknown, hits, of_part, {}, WEIGHTS, 0.0, 10)

    assert KEPT == 10
    assert len(best) == KEPT
    assert [c.id for c in best][:6] == ["p00", "p01", "p02", "p03", "p04", "p04b"]
    scores = [c.score for c in best]
    assert scores == sorted(scores, reverse=True)
    assert candidates == best


@pytest.mark.parametrize(
    ("least", "limit"), [(0.0, 1), (0.0, 3), (0.9, 10), (0.9, 2), (1.1, 10)]
)
def test_the_cut_by_least_score_and_limit_does_not_touch_best(least, limit):
    unknown, hits, of_part = case(14)
    every, _ = ranked(unknown, hits, of_part, {}, WEIGHTS, 0.0, 100)

    best, candidates = ranked(unknown, hits, of_part, {}, WEIGHTS, least, limit)

    assert best == every
    above = [c for c in every if c.score >= least]
    assert candidates == above[:limit]
    # (the candidates are the head of the one ranking: what they share with best is the same, in the same order)
    assert candidates == best[: len(candidates)]


def test_with_fewer_than_ten_found_best_is_every_one_and_a_limit_past_ten_still_keeps_ten():
    unknown, hits, of_part = case(3)
    best, _ = ranked(unknown, hits, of_part, {}, WEIGHTS, 0.0, 10)
    assert [c.id for c in best] == ["p00", "p01", "p02"]

    unknown, hits, of_part = case(30)
    best, candidates = ranked(unknown, hits, of_part, {}, WEIGHTS, 0.0, 20)
    assert len(best) == KEPT
    assert len(candidates) == 20
    assert candidates[:KEPT] == best


def test_a_row_holds_each_part_s_cosine_the_count_shared_and_the_score():
    unknown, hits, of_part = case(2)
    sharing = {"p01": [("Ada", 2), ("mill", 1)]}
    weights = {"name": 1.0, "shared": 1.5}

    best, _ = ranked(unknown, hits, of_part, sharing, weights, 0.0, 10)

    (first,) = [c for c in best if c.id == "p01"]
    assert set(first.scores) == {"name", "shared"}
    assert len(first.shared) == 2
    assert first.scores["shared"] == pytest.approx(first.scores["name"] * 2 / 4)
