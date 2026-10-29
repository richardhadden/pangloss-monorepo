"""Naming days and laying out a month, in both calendars"""

import pytest
from pangloss_calendar.days import (
    InvalidDayRef,
    format_day,
    month_grid,
    month_span,
    next_month,
    parse_day,
    previous_month,
    view_of,
)
from pangloss_dates.calendar import Calendar, Weekday, from_jdn, to_jdn, weekday

J = Calendar.JULIAN
G = Calendar.GREGORIAN


def test_julian_1500_has_a_29_february_and_the_gregorian_year_does_not():
    leap = to_jdn(1500, 2, 29, J)
    view = view_of(leap)
    assert view.julian == (1500, 2, 29)
    assert view.gregorian == (1500, 3, 10)
    assert month_span(J, 1500, 2)[1] - month_span(J, 1500, 2)[0] == 28
    assert month_span(G, 1500, 2)[1] - month_span(G, 1500, 2)[0] == 27


def test_julian_2_march_1500_is_gregorian_12_march_a_monday():
    view = view_of(parse_day("J1500-03-02"))
    assert view.gregorian == (1500, 3, 12)
    assert view.weekday == Weekday.MONDAY
    assert parse_day("G1500-03-12") == parse_day("J1500-03-02")
    assert parse_day(str(parse_day("J1500-03-02"))) == parse_day("J1500-03-02")


def test_a_day_is_written_in_either_calendar_and_read_back():
    jdn = parse_day("J1500-03-02")
    assert format_day(jdn, J) == "J1500-03-02"
    assert format_day(jdn, G) == "G1500-03-12"
    assert parse_day(format_day(jdn, G)) == jdn
    assert parse_day("J-0044-03-15") == to_jdn(-44, 3, 15, J)


@pytest.mark.parametrize(
    "text",
    ["", "1500-03-02", "J1500-02-30", "G1500-02-29", "X1500-01-01", "J1500-13-01"],
)
def test_a_text_that_is_not_a_day_is_refused(text):
    with pytest.raises(InvalidDayRef):
        parse_day(text)


@pytest.mark.parametrize("calendar", [J, G])
def test_every_day_of_1400_to_1600_has_both_names_that_agree_with_the_arithmetic(
    calendar,
):
    for jdn in range(to_jdn(1400, 1, 1, calendar), to_jdn(1600, 12, 31, calendar) + 1):
        view = view_of(jdn)
        assert to_jdn(*view.julian, J) == jdn
        assert to_jdn(*view.gregorian, G) == jdn
        assert view.weekday == weekday(jdn)
        assert tuple(from_jdn(jdn, calendar)) == view.in_calendar(calendar)


def test_the_two_calendars_name_the_days_with_juliandate_too():
    juliandate = pytest.importorskip("juliandate")
    for jdn in range(to_jdn(1500, 1, 1, J), to_jdn(1500, 12, 31, J) + 1):
        view = view_of(jdn)
        assert juliandate.from_julian(*view.julian) == jdn - 0.5
        assert juliandate.from_gregorian(*view.gregorian) == jdn - 0.5


@pytest.mark.parametrize("calendar", [J, G])
@pytest.mark.parametrize("starts", [Weekday.MONDAY, Weekday.SUNDAY])
def test_a_month_grid_starts_on_the_right_weekday(calendar, starts):
    for year, month in [(1500, 2), (1500, 3), (1499, 12), (1582, 10)]:
        grid = month_grid(calendar, year, month, starts)
        first, last = month_span(calendar, year, month)
        assert all(len(week) == 7 for week in grid)
        days = [d for week in grid for d in week if d is not None]
        assert days == list(range(first, last + 1))
        for week in grid:
            for column, d in enumerate(week):
                if d is not None:
                    assert weekday(d) == (starts + column) % 7
        assert grid[0][(weekday(first) - starts) % 7] == first


def test_march_1500_begins_on_a_different_weekday_in_each_calendar():
    assert weekday(to_jdn(1500, 3, 1, J)) != weekday(to_jdn(1500, 3, 1, G))


def test_months_step_over_the_year():
    assert next_month(J, 1500, 12) == (1501, 1)
    assert previous_month(J, 1500, 1) == (1499, 12)
    assert next_month(G, 1500, 5) == (1500, 6)
