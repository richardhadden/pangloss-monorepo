"""How a candidate is scored against an unknown (`pangloss_reconcile.score`, step 10.2c of
implementation_docs/similarity-build-plan.md): the cosine of each part, a part missing on either side, the weights,
the order and ties; and the entities shared (step 11.2)"""

import math

import pytest
from pangloss_reconcile.score import (
    cosine,
    lead,
    part_scores,
    ranked,
    score,
    shared_score,
    with_shared,
)

WEIGHTS = {"name": 1.0, "graph": 0.25}


def test_the_cosine_of_two_vectors_is_that_of_their_directions():
    assert cosine([1, 0], [2, 0]) == pytest.approx(1.0)
    assert cosine([1, 0], [0, 3]) == pytest.approx(0.0)
    assert cosine([1, 1], [-1, -1]) == pytest.approx(-1.0)
    assert cosine([3, 4], [4, 3]) == pytest.approx(24 / 25)


def test_a_vector_of_length_zero_is_like_nothing_and_vectors_of_two_lengths_are_refused():
    assert cosine([0, 0], [1, 0]) == 0.0
    with pytest.raises(ValueError, match="one length"):
        cosine([1, 0], [1, 0, 0])


def test_each_part_the_unknown_has_is_scored_and_one_the_candidate_lacks_is_0():
    unknown = {"name": [1, 0], "graph": [0, 1]}
    assert part_scores(unknown, {"name": [1, 0]}, WEIGHTS) == {
        "graph": 0.0,
        "name": pytest.approx(1.0),
    }


def test_a_part_the_unknown_lacks_is_not_scored_whatever_the_candidate_has():
    assert part_scores(
        {"name": [1, 0]}, {"name": [1, 1], "graph": [1, 0]}, WEIGHTS
    ) == {"name": pytest.approx(math.sqrt(0.5))}


def test_a_part_at_weight_0_or_of_no_weight_is_not_scored():
    unknown = {"name": [1, 0], "class": [1, 0], "time": [1, 0]}
    found = part_scores(unknown, unknown, {"name": 1.0, "class": 0.0})
    assert found == {"name": pytest.approx(1.0)}


def test_the_score_is_the_weighted_mean_of_the_parts_the_unknown_has():
    assert score({"name": 1.0, "graph": 0.2}, WEIGHTS) == pytest.approx(
        (1.0 + 0.25 * 0.2) / 1.25
    )
    # (a part the candidate lacks still counts below the line: it is not lifted for lacking it)
    assert score({"name": 1.0, "graph": 0.0}, WEIGHTS) == pytest.approx(0.8)
    assert score({"name": 1.0}, WEIGHTS) == pytest.approx(1.0)
    assert score({}, WEIGHTS) == 0.0


def test_the_weights_change_the_order():
    near_by_name = {"name": 1.0, "graph": 0.0}
    near_by_graph = {"name": 0.5, "graph": 1.0}
    assert score(near_by_name, WEIGHTS) > score(near_by_graph, WEIGHTS)
    even = {"name": 1.0, "graph": 1.0}
    assert score(near_by_name, even) < score(near_by_graph, even)


def test_candidates_are_ranked_by_score_then_by_id_and_cut_to_the_limit():
    scored = {"c": 0.5, "a": 0.9, "b": 0.5, "d": 0.1}
    assert ranked(scored, 10) == ["a", "b", "c", "d"]
    assert ranked(scored, 2) == ["a", "b"]
    assert ranked({}, 3) == []


def test_a_part_whose_vector_of_the_unknown_is_all_zeros_is_as_if_it_said_nothing():
    unknown = {"name": [1, 0], "graph": [0.0, 0.0]}
    scores = part_scores(unknown, {"name": [1, 0], "graph": [1, 0]}, WEIGHTS)
    assert scores == {"name": pytest.approx(1.0)}
    # (not in the sum below the line either)
    assert score(scores, WEIGHTS) == pytest.approx(1.0)


def test_a_stored_vector_of_another_length_is_as_if_the_candidate_had_none():
    unknown = {"name": [1, 0], "graph": [0, 1]}
    scores = part_scores(unknown, {"name": [1, 0], "graph": [0, 1, 0]}, WEIGHTS)
    assert scores == {"name": pytest.approx(1.0), "graph": 0.0}
    assert score(scores, WEIGHTS) == pytest.approx(0.8)


# -- the entities shared (step 11.2) --------------------------------------------------------------------------------

WITH_SHARED = {"name": 1.0, "graph": 0.25, "shared": 1.5}


def test_sharing_n_entities_is_worth_n_over_n_plus_2():
    assert [shared_score(n) for n in range(4)] == [0.0, 1 / 3, 0.5, 0.6]
    assert shared_score(1000) == pytest.approx(1000 / 1002)
    with pytest.raises(ValueError, match="0 or more"):
        shared_score(-1)


def test_the_lead_is_the_part_weighed_most_and_of_several_alike_the_first_by_name():
    assert lead({"graph": 0.4, "name": 0.9}, WITH_SHARED) == "name"
    assert lead({"graph": 0.4, "name": 0.9}, {"graph": 2.0, "name": 1.0}) == "graph"
    assert lead({"graph": 0.4, "name": 0.9}, {"graph": 1.0, "name": 1.0}) == "graph"
    # (`shared` is no part, and never the lead, whatever its weight)
    assert lead({"name": 0.9, "shared": 0.5}, {"name": 1.0, "shared": 9.0}) == "name"
    assert lead({}, WITH_SHARED) is None


def test_shared_is_the_lead_s_cosine_times_n_over_n_plus_2_one_more_term_of_the_mean():
    scores = with_shared({"name": 0.8, "graph": 0.4}, 2, WITH_SHARED)
    assert scores == {"graph": 0.4, "name": 0.8, "shared": pytest.approx(0.4)}
    assert score(scores, WITH_SHARED) == pytest.approx(
        (0.8 + 0.25 * 0.4 + 1.5 * 0.4) / 2.75
    )
    # (another lead by the weights: the graph's cosine)
    by_graph = {"name": 0.5, "graph": 2.0, "shared": 1.0}
    assert with_shared({"name": 0.8, "graph": 0.4}, 2, by_graph)[
        "shared"
    ] == pytest.approx(0.2)


def test_a_lead_of_0_gives_0_whatever_is_shared_and_so_does_no_part_scored():
    for n in (0, 1, 10, 1000):
        assert with_shared({"name": 0.0, "graph": 0.9}, n, WITH_SHARED)["shared"] == 0
        assert with_shared({}, n, WITH_SHARED) == {"shared": 0.0}
    # (someone of another name altogether, the graph near, sharing much: far under a namesake who shares nothing)
    other = score(with_shared({"name": 0.0, "graph": 0.9}, 5, WITH_SHARED), WITH_SHARED)
    namesake = score(
        with_shared({"name": 1.0, "graph": 0.0}, 0, WITH_SHARED), WITH_SHARED
    )
    assert other < 0.15 < namesake


def test_sharing_nothing_is_0_and_still_counts_below_the_line():
    scores = with_shared({"name": 1.0, "graph": 0.4}, 0, WITH_SHARED)
    assert scores["shared"] == 0.0
    assert score(scores, WITH_SHARED) == pytest.approx((1.0 + 0.25 * 0.4) / 2.75)
    # (so a candidate who shares is lifted above a namesake who does not, at the same parts)
    assert score(with_shared({"name": 1.0}, 1, WITH_SHARED), WITH_SHARED) > score(
        with_shared({"name": 1.0}, 0, WITH_SHARED), WITH_SHARED
    )


def test_at_weight_0_shared_is_not_there_and_the_score_is_phase_10_s():
    parts = {"name": 1.0, "graph": 0.4}
    for weights in (WEIGHTS, {**WEIGHTS, "shared": 0.0}):
        scores = with_shared(parts, 3, weights)
        assert scores == parts
        assert "shared" not in scores
        assert score(scores, weights) == score(parts, WEIGHTS)


def test_the_least_score_is_where_a_name_of_cosine_0_41_that_shares_nothing_is():
    """(the default weights and least score: phase 10's dialog cut at a name's cosine of 0.375)"""
    assert score(
        with_shared({"name": 0.41, "graph": 0.0}, 0, WITH_SHARED), WITH_SHARED
    ) == pytest.approx(0.15, abs=0.001)


def test_the_score_with_shared_stays_between_0_and_1():
    for n in (0, 1, 5, 100):
        for name in (0.0, 0.5, 1.0):
            value = score(
                with_shared({"name": name, "graph": 1.0}, n, WITH_SHARED), WITH_SHARED
            )
            assert 0.0 <= value <= 1.0


def test_a_lead_under_0_makes_what_is_shared_count_nothing_not_against():
    from pangloss_reconcile.score import with_shared

    found = with_shared(
        {"name": -0.4, "graph": 0.2}, 3, {"name": 1, "graph": 0.25, "shared": 1.5}
    )
    assert found["shared"] == 0.0
