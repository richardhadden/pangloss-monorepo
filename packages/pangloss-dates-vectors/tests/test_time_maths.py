"""The maths of the time part (`pangloss_dates_vectors.maths`), with no database: what the cosine of two dates'
vectors is (implementation_docs/similarity-build-plan.md, step 9.2)"""

import numpy as np
import pytest
from pangloss_dates.bounds import padded_bounds
from pangloss_dates.calendar import Calendar, to_jdn
from pangloss_dates_vectors import maths

G = Calendar.GREGORIAN
RING = maths.Ring()


def day(year: int, month: int, number: int) -> maths.Bounds:
    at = to_jdn(year, month, number, G)
    return (at, at, at, at)


def years(first: int, last: int | None = None) -> maths.Bounds:
    """From the first day of a year to the last of it, or of another: exactly"""
    start, end = to_jdn(first, 1, 1, G), to_jdn(last or first, 12, 31, G)
    return (start, start, end, end)


def about(year: int, either_side: int) -> maths.Bounds:
    """A year, give or take: strict the year, fuzzy that many years either side"""
    return (
        to_jdn(year - either_side, 1, 1, G),
        to_jdn(year, 1, 1, G),
        to_jdn(year, 12, 31, G),
        to_jdn(year + either_side, 12, 31, G),
    )


def cos(a: maths.Bounds, b: maths.Bounds, ring: maths.Ring = RING) -> float:
    first, second = maths.vectors([a, b], ring)
    return float(first @ second)


def test_a_vector_is_of_the_dimension_at_length_one_and_nowhere_negative():
    made = maths.vectors([day(1500, 3, 2), years(1500), years(1480, 1530)], RING)
    assert made.shape == (3, 128)
    assert np.allclose(np.linalg.norm(made, axis=1), 1.0)
    assert (made >= 0).all()


def test_the_same_year_is_one_and_a_day_is_near_its_year():
    assert cos(years(1500), years(1500)) == pytest.approx(1.0)
    assert cos(day(1500, 6, 24), years(1500)) > 0.99
    # (and nearer its own year than the next, whenever in the year it is)
    for month in (1, 6, 12):
        assert cos(day(1500, month, 15), years(1500)) > cos(
            day(1500, month, 15), years(1501)
        )
        assert cos(day(1500, month, 15), years(1500)) > cos(
            day(1500, month, 15), years(1499)
        )


def test_the_cosine_falls_with_the_gap_and_ten_years_apart_is_near_nothing_at_a_width_of_two():
    gaps = [cos(years(1500), years(1500 + gap)) for gap in (0, 1, 2, 3, 5, 10)]
    assert gaps == sorted(gaps, reverse=True)
    assert gaps[1] > 0.9  # (a year apart is still near, at a width of 2)
    assert 0.6 < gaps[2] < 0.85
    assert gaps[4] < 0.25
    assert gaps[5] < 0.01


def test_a_narrower_bump_tells_next_year_apart_and_a_wider_one_keeps_five_years_near():
    assert cos(years(1500), years(1501), maths.Ring(128, 1)) < 0.8
    assert cos(years(1500), years(1505), maths.Ring(128, 5)) > 0.7


@pytest.mark.parametrize("gap", [0, 1, 2, 5])
def test_the_cosine_depends_on_the_gap_and_not_on_where_the_dates_are(gap):
    found = [
        cos(day(year, 1 + year % 12, 5), day(year + gap, 1 + year % 12, 5))
        for year in (903, 1500, 1533, 1601, 1999)
    ]
    assert max(found) - min(found) < 0.02


def test_overlapping_vague_dates_are_near_and_the_more_they_share_the_nearer():
    decade = years(1500, 1509)
    assert cos(years(1505), decade) > 0.8
    assert cos(day(1505, 6, 1), decade) > 0.8
    assert cos(years(1500, 1509), years(1505, 1514)) > 0.6
    # (a year inside a decade is nearer it than a year beside it, and that than a year well outside)
    assert (
        cos(years(1505), decade) > cos(years(1511), decade) > cos(years(1520), decade)
    )
    # (a year in fifty is less of the fifty than a year in ten is of the ten)
    assert cos(years(1525), years(1500, 1549)) < cos(years(1505), decade)
    assert cos(years(1500, 1509), years(1510, 1519)) < 0.2


def test_fuzzy_bounds_reach_further_than_strict_ones_and_count_for_less():
    exact, doubted = years(1500), about(1500, 3)
    # (three years off: nearer the doubted year than the exact one)
    assert cos(years(1503), doubted) > cos(years(1503), exact) + 0.05
    # (and the year itself is nearer the exact one)
    assert cos(years(1500), exact) > cos(years(1500), doubted)
    # (the doubted year is nearer its own year than the edge of its doubt)
    assert cos(years(1500), doubted) > cos(years(1503), doubted)


def test_the_bounds_pangloss_dates_works_out_for_an_approximate_year_are_taken_as_they_are():
    found = padded_bounds(1500, None, None, G)
    bounds = (
        found.earliest_fuzzy,
        found.earliest_strict,
        found.latest_strict,
        found.latest_fuzzy,
    )
    assert cos(bounds, years(1500)) > 0.9
    assert cos(bounds, years(1501)) > cos(years(1500), years(1501)) - 0.05


def test_the_years_go_round_the_ring():
    assert RING.years == 256
    # (but for the leap days, which put 1756 a part of a day from where 1500 is)
    assert cos(years(1500), years(1756)) == pytest.approx(1.0, abs=1e-5)
    assert cos(years(1500), years(1628)) < 1e-6
    # (a longer ring tells them apart)
    assert cos(years(1500), years(1756), maths.Ring(512, 2)) < 1e-6
    # (within the ring, a longer one changes nothing)
    assert cos(years(1500), years(1503)) == pytest.approx(
        cos(years(1500), years(1503), maths.Ring(512, 2)), abs=1e-9
    )


def test_a_date_longer_than_the_ring_is_near_every_date_alike():
    always = years(1, 1600)
    found = [cos(always, years(year)) for year in (900, 1500, 1533)]
    assert max(found) - min(found) < 0.01
    assert 0 < found[0] < 0.3


def test_an_item_with_several_dates_is_near_each_and_one_with_none_has_no_vector():
    both = maths.vector([years(1500), years(1540)], RING)
    first, second, between = maths.vectors(
        [years(1500), years(1540), years(1520)], RING
    )
    assert both is not None
    assert float(both @ first) == pytest.approx(float(both @ second))
    assert float(both @ first) > 0.7
    assert float(both @ between) < 0.01
    assert np.linalg.norm(both) == pytest.approx(1.0)
    assert maths.vector([], RING) is None


def test_the_vectors_of_many_items_at_once_are_what_each_is_alone():
    dates = [years(1500), years(1540), day(1520, 3, 2), years(1500, 1509)]
    made = maths.of_items(
        [dates[0], dates[1], dates[2], dates[0], dates[3]], [0, 0, 2, 3, 3], 4, RING
    )
    assert np.allclose(made[0], maths.vector([dates[0], dates[1]], RING))
    assert not made[1].any()
    assert np.allclose(made[2], maths.vector([dates[2]], RING))
    assert np.allclose(made[3], maths.vector([dates[0], dates[3]], RING))
    assert maths.of_items([], [], 2, RING).shape == (2, 128)


def test_a_long_period_does_not_drown_a_day_of_the_same_item():
    made = maths.vector([years(1400, 1460), day(1500, 3, 2)], RING)
    assert made is not None
    [alone] = maths.vectors([day(1500, 3, 2)], RING)
    assert float(made @ alone) > 0.6


def test_a_recurring_event_s_years_are_apart_and_each_year_s_two_reports_together():
    """(the rent of 1500 by one source as a day and by another as the year, and so on for six years: each report
    is nearest the other of its year)"""
    reports = []
    for year in range(1500, 1506):
        reports += [day(year, 9, 29), years(year)]
    made = maths.vectors(reports, maths.Ring(128, 1))
    likeness = made @ made.T
    np.fill_diagonal(likeness, -1)
    assert [int(n) for n in likeness.argmax(axis=1)] == [
        n + 1 if n % 2 == 0 else n - 1 for n in range(len(reports))
    ]
    wide = maths.vectors(reports, RING)
    likeness = wide @ wide.T
    np.fill_diagonal(likeness, -1)
    assert [int(n) for n in likeness.argmax(axis=1)] == [
        n + 1 if n % 2 == 0 else n - 1 for n in range(len(reports))
    ]


def test_many_dates_at_once_are_what_each_is_alone():
    rng = np.random.default_rng(5)
    dates = []
    for _ in range(300):
        start = to_jdn(int(rng.integers(900, 1900)), 1, 1, G) + int(
            rng.integers(0, 365)
        )
        a, b, c = (int(n) for n in rng.integers(0, [800, 4000, 800]))
        if rng.random() < 0.5:
            a = c = 0
        dates.append((start, start + a, start + a + b, start + a + b + c))
    dates.append(years(1, 1600))
    together = maths.vectors(dates, RING)
    for n, date in enumerate(dates):
        assert np.allclose(together[n], maths.vectors([date], RING)[0], atol=1e-12)


def test_the_blur_is_the_date_summed_over_its_days():
    """(the closed form against the plain way: each day of the date, weighed by how far the date could be then,
    as a logistic bump at each centre; on a ring long enough that nothing goes round)"""
    ring = maths.Ring(512, 2)
    date = about(1500, 2)
    a, b, c, d = date
    days = np.arange(a, d + 1)
    could = np.where(
        days < b,
        (days - a + 0.5) / (b - a),
        np.where(days > c, (d - days + 0.5) / (d - c), 1.0),
    )
    centres = np.arange(ring.dimension) * ring.width
    at = np.asarray(maths.year_of(days + 0.5))
    # (the years of the ring's places that are nearest the date: none of it goes round)
    turn = np.round((at.mean() - centres) / ring.years) * ring.years
    x = (centres[None, :] + turn[None, :] - at[:, None]) / ring.scale
    bump = 1.0 / (4.0 * ring.scale * np.cosh(x / 2.0) ** 2)
    plain = (could[:, None] * bump).sum(axis=0) / maths.DAYS_IN_A_YEAR
    [closed] = maths.blurred([date], ring)
    assert np.allclose(closed, plain, atol=2e-3 * plain.max())


def test_bounds_out_of_order_and_a_ring_that_cannot_be_are_refused():
    with pytest.raises(ValueError, match="in order"):
        maths.vectors([(10, 9, 11, 12)], RING)
    with pytest.raises(ValueError, match="width"):
        maths.Ring(128, 0)
    with pytest.raises(ValueError, match="places"):
        maths.Ring(1, 2)


def test_the_year_of_a_day_number():
    assert maths.year_of(to_jdn(1, 1, 1, G)) == 1.0
    assert maths.year_of(to_jdn(1500, 1, 1, G)) == pytest.approx(1500.0, abs=0.01)
    assert maths.year_of(to_jdn(1500, 7, 2, G)) == pytest.approx(1500.5, abs=0.01)
