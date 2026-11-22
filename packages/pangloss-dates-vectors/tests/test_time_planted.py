"""The quality of the time part, held to floors: on the planted world with dates (`pangloss_testing.planted`,
`dated=True`), by time alone and with no database. The floors are a little under what was measured on 2026-11-22
(at 1,500 people, the ring as it is given, seeds 1 to 3: of what happened year after year, the other report of the
year first among the reports of the thing 99.7% to 100%; of an event told twice, the other report among the nearest
hundredth of all the factoids 83% to 90%, and always among the nearest tenth). What time adds to the graph is
measured in the database (notes/similarity-evaluation/planted.py `time`). A change that costs quality fails here
(implementation_docs/similarity-build-plan.md, step 9.2)"""

import numpy as np
import pytest
import time_planted_support as support
from pangloss_dates_vectors import maths
from pangloss_testing import planted


def measured(seed: int, ring: maths.Ring):
    world = planted.world(seed=seed, people=1500, dated=True)
    labels = [factoid["label"] for factoid in world.factoids]
    return world, labels, support.time_vectors(world, labels, ring)


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_of_what_happened_year_after_year_the_other_report_of_the_year_is_first(seed):
    """(among the reports of the same thing, which nothing but the date tells apart)"""
    world, labels, vectors = measured(seed, maths.Ring())
    series = support.series_of(world)
    thing = np.array([hash(series.get(label, label)) for label in labels])

    def among_its_own(rows):
        scores = vectors[rows] @ vectors.T
        scores[thing[rows][:, None] != thing[None, :]] = -np.inf
        return scores

    assert len(series) > 300
    assert support.found_among(world, labels, among_its_own, 1, set(series)) > 0.98


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_an_event_told_twice_is_among_the_nearest_in_time_however_each_says_the_date(
    seed,
):
    world, labels, vectors = measured(seed, maths.Ring())
    once = set(support.other_reports(world)) - set(support.series_of(world))

    def scores(rows):
        return vectors[rows] @ vectors.T

    assert len(once) > 200
    assert support.found_among(world, labels, scores, len(labels) // 10, once) > 0.99
    assert support.found_among(world, labels, scores, len(labels) // 100, once) > 0.75


def test_a_shorter_ring_gives_the_same_among_dates_within_it():
    """(the planted years are within some 300: a ring of 512 years and one of 1,024 rank alike)"""
    world, labels, short = measured(1, maths.Ring(256, 2))
    _, _, long = measured(1, maths.Ring(512, 2))
    assert np.allclose(short @ short[:50].T, long @ long[:50].T, atol=1e-9)
