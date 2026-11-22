"""How a candidate is scored against an unknown (`pangloss_reconcile.score`, step 10.2c of
implementation_docs/similarity-build-plan.md): the cosine of each part, a part missing on either side, the weights,
the order and ties"""

import math

import pytest
from pangloss_reconcile.score import cosine, part_scores, ranked, score

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
