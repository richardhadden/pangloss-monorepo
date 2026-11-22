"""More of the maths of the time part (`pangloss_dates_vectors.maths`), found while building the part (step 9.3): a
date that spans more years than the ring holds (`dimension × width`, 256 as it is given). Such dates are common: a
`DateRange` whose `not_before` is unknown runs from `DATES_EARLIEST_YEAR` (the year 1 by default), and the part gives
it a vector (an `UnknownDate` alone it does not). On a ring such a date cannot say when: what is held to here is that
it says nothing evenly, with no part of it counted twice, and that a longer ring gives it back its place."""

import pytest
from pangloss_dates.calendar import Calendar, to_jdn
from pangloss_dates_vectors import maths

G = Calendar.GREGORIAN
RING = maths.Ring()


def years(first: int, last: int | None = None) -> maths.Bounds:
    """From the first day of a year to the last of it, or of another: exactly"""
    start, end = to_jdn(first, 1, 1, G), to_jdn(last or first, 12, 31, G)
    return (start, start, end, end)


def cos(a: maths.Bounds, b: maths.Bounds, ring: maths.Ring = RING) -> float:
    first, second = maths.vectors([a, b], ring)
    return float(first @ second)


def test_a_range_whose_start_is_unknown_is_as_near_every_year_and_not_near_any():
    not_after_1500 = years(1, 1500)
    found = [cos(not_after_1500, years(year)) for year in (700, 1490, 1500, 1700)]
    assert max(found) - min(found) < 1e-4
    assert 0.1 < found[0] < 0.2
    # (every place alike: nothing of it counts twice)
    [made] = maths.vectors([not_after_1500], RING)
    assert made.max() - made.min() < 1e-9


def test_a_period_a_little_longer_than_the_ring_counts_no_year_twice():
    """(1300 to 1600 is 300 years on a ring of 256: its first and last 44 years fall on the same places)"""
    period = years(1300, 1600)
    inside, end, outside = (
        cos(period, years(1450)),
        cos(period, years(1300)),
        cos(period, years(1800)),
    )
    assert inside == pytest.approx(end, abs=1e-4)
    assert inside == pytest.approx(outside, abs=1e-4)


def test_on_a_ring_longer_than_the_period_a_year_inside_it_is_near_and_one_outside_is_not():
    ring = maths.Ring(512, 2)
    period = years(1300, 1600)
    assert cos(period, years(1450), ring) > 0.1
    assert cos(period, years(1300), ring) < cos(period, years(1450), ring)
    assert cos(period, years(1800), ring) < 1e-6
