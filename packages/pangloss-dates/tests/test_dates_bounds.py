"""The four bounds, the padding convention and the sort day"""

import pytest
from pangloss_dates.bounds import (
    Bounds,
    InvalidBounds,
    Padding,
    Precision,
    SortBy,
    exact_bounds,
    ongoing_bounds,
    padded_bounds,
    precision_of,
    shift_month,
    spanning_bounds,
)
from pangloss_dates.calendar import Calendar, InvalidDate, from_jdn, to_jdn

J = Calendar.JULIAN


def ymd(jdn):
    return tuple(from_jdn(jdn, J))


def test_bounds_must_be_in_order():
    Bounds(1, 2, 3, 4)
    Bounds(1, 1, 1, 1)
    for bad in [(2, 1, 3, 4), (1, 3, 2, 4), (1, 2, 4, 3), (1, 2, 3, 2)]:
        with pytest.raises(InvalidBounds):
            Bounds(*bad)


def test_exact_bounds_for_a_year_a_month_a_day():
    year = exact_bounds(1500, None, None, J)
    assert (ymd(year.earliest_strict), ymd(year.latest_strict)) == (
        (1500, 1, 1),
        (1500, 12, 31),
    )
    assert year.earliest_fuzzy == year.earliest_strict
    assert year.latest_fuzzy == year.latest_strict
    feb = exact_bounds(1500, 2, None, J)
    assert ymd(feb.latest_strict) == (1500, 2, 29)  # a Julian leap year
    assert (
        exact_bounds(1500, 2, None, Calendar.GREGORIAN).latest_strict
        - exact_bounds(1500, 2, None, Calendar.GREGORIAN).earliest_strict
        == 27
    )
    day = exact_bounds(1500, 3, 2, J)
    assert day.earliest_strict == day.latest_strict == to_jdn(1500, 3, 2, J)


def test_padded_bounds_by_precision():
    year = padded_bounds(1500, None, None, J)
    assert ymd(year.earliest_fuzzy) == (1499, 1, 1)
    assert ymd(year.earliest_strict) == (1500, 1, 1)
    assert ymd(year.latest_strict) == (1500, 12, 31)
    assert ymd(year.latest_fuzzy) == (1501, 12, 31)

    month = padded_bounds(1500, 3, None, J)
    assert ymd(month.earliest_fuzzy) == (1500, 2, 1)
    assert ymd(month.latest_fuzzy) == (1500, 4, 30)

    january = padded_bounds(1500, 1, None, J)
    assert ymd(january.earliest_fuzzy) == (1499, 12, 1)
    december = padded_bounds(1500, 12, None, J)
    assert ymd(december.latest_fuzzy) == (1501, 1, 31)

    day = padded_bounds(1500, 3, 2, J)
    assert ymd(day.earliest_fuzzy) == (1500, 2, 24)  # a week before, in a leap year
    assert ymd(day.latest_fuzzy) == (1500, 3, 9)


def test_padding_is_a_setting():
    wide = padded_bounds(1500, None, None, J, Padding(year=5))
    assert ymd(wide.earliest_fuzzy) == (1495, 1, 1)
    assert ymd(wide.latest_fuzzy) == (1505, 12, 31)
    none = padded_bounds(1500, 3, 2, J, Padding(day=0))
    assert none == exact_bounds(1500, 3, 2, J)


def test_shift_month():
    assert shift_month(1500, 3, 1) == (1500, 4)
    assert shift_month(1500, 12, 1) == (1501, 1)
    assert shift_month(1500, 1, -1) == (1499, 12)
    assert shift_month(1500, 1, -13) == (1498, 12)
    assert shift_month(1500, 6, 0) == (1500, 6)


def test_precision():
    assert precision_of(None, None) == Precision.YEAR
    assert precision_of(3, None) == Precision.MONTH
    assert precision_of(3, 2) == Precision.DAY


def test_sort_day_defaults_to_the_midpoint_of_the_strict_range():
    year = exact_bounds(1500, None, None, J)
    assert year.sort_day() == (year.earliest_strict + year.latest_strict) // 2
    assert ymd(year.sort_day()) == (1500, 7, 1)
    day = exact_bounds(1500, 3, 2, J)
    assert day.sort_day() == to_jdn(1500, 3, 2, J)


def test_every_way_to_sort():
    b = Bounds(10, 20, 40, 100)
    assert b.sort_day(SortBy.MIDPOINT) == 30
    assert b.sort_day(SortBy.MIDPOINT_FUZZY) == 55
    assert b.sort_day(SortBy.EARLIEST_STRICT) == 20
    assert b.sort_day(SortBy.LATEST_STRICT) == 40
    assert b.sort_day(SortBy.EARLIEST_FUZZY) == 10
    assert b.sort_day(SortBy.LATEST_FUZZY) == 100
    assert {s.value for s in SortBy} == {
        "midpoint",
        "midpoint_fuzzy",
        "earliest_strict",
        "latest_strict",
        "earliest_fuzzy",
        "latest_fuzzy",
    }


def test_sort_day_is_always_inside_the_bounds():
    for sort_by in SortBy:
        for b in [
            Bounds(1, 1, 1, 1),
            Bounds(0, 5, 6, 20),
            exact_bounds(1500, 2, None, J),
        ]:
            assert b.earliest_fuzzy <= b.sort_day(sort_by) <= b.latest_fuzzy


def test_contains_strict_or_fuzzy():
    b = Bounds(10, 20, 40, 100)
    assert b.contains(15) and not b.contains(15, fuzzy=False)
    assert b.contains(30, fuzzy=False)
    assert not b.contains(101)


def test_a_range_of_two_dates_spans_from_the_earliest_to_the_latest():
    earliest = exact_bounds(1500, None, None, J)
    latest = exact_bounds(1502, 3, None, J)
    span = spanning_bounds(earliest, latest)
    assert ymd(span.earliest_strict) == (1500, 1, 1)
    assert ymd(span.latest_strict) == (1502, 3, 31)
    assert span.earliest_fuzzy == span.earliest_strict


def test_a_range_of_approximate_ends_is_fuzzy_at_the_outer_edges():
    span = spanning_bounds(
        padded_bounds(1500, None, None, J), padded_bounds(1502, None, None, J)
    )
    assert ymd(span.earliest_fuzzy) == (1499, 1, 1)
    assert ymd(span.earliest_strict) == (1500, 1, 1)
    assert ymd(span.latest_strict) == (1502, 12, 31)
    assert ymd(span.latest_fuzzy) == (1503, 12, 31)


def test_a_range_cannot_end_before_it_starts():
    with pytest.raises(InvalidDate):
        spanning_bounds(
            exact_bounds(1502, None, None, J), exact_bounds(1500, None, None, J)
        )
    # the same year is fine, and so is the same day
    spanning_bounds(exact_bounds(1500, 3, 2, J), exact_bounds(1500, 3, 2, J))
    # years that overlap through the months are not an error
    spanning_bounds(exact_bounds(1500, None, None, J), exact_bounds(1500, 3, None, J))


def test_a_period_with_no_end_stops_at_the_horizon():
    horizon = to_jdn(1600, 1, 1, J)
    end = ongoing_bounds(horizon)
    period = spanning_bounds(exact_bounds(1500, 3, 2, J), end)
    assert period.latest_strict == period.latest_fuzzy == horizon
    assert period.earliest_strict == to_jdn(1500, 3, 2, J)
