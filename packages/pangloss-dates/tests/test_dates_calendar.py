"""Julian and Gregorian day arithmetic, against known days and against `juliandate`"""

import pytest
from pangloss_dates.calendar import (
    Calendar,
    InvalidDate,
    Weekday,
    convert,
    first_and_last_day,
    from_jdn,
    is_leap_year,
    month_length,
    nth_weekday,
    to_jdn,
    weekday,
)

J, G = Calendar.JULIAN, Calendar.GREGORIAN


@pytest.mark.parametrize(
    "ymd, calendar, jdn",
    [
        ((2000, 1, 1), G, 2451545),
        ((-4712, 1, 1), J, 0),
        ((1582, 10, 4), J, 2299160),
        ((1582, 10, 15), G, 2299161),
        ((1500, 3, 2), J, 2268994),
        ((1500, 3, 12), G, 2268994),
        ((1500, 2, 29), J, 2268994 - 2),
        ((1, 1, 1), J, 1721424),
        ((1, 1, 1), G, 1721426),
    ],
)
def test_known_days(ymd, calendar, jdn):
    assert to_jdn(*ymd, calendar) == jdn
    assert tuple(from_jdn(jdn, calendar)) == ymd


def test_the_gap_between_the_calendars_grows_with_the_century():
    assert convert(1500, 2, 28, J, G) == (1500, 3, 9)
    assert convert(1500, 3, 1, J, G) == (1500, 3, 11)
    assert convert(1400, 3, 1, J, G) == (1400, 3, 10)
    assert convert(1600, 3, 1, J, G) == (1600, 3, 11)
    assert convert(1700, 3, 1, J, G) == (1700, 3, 12)


def test_1500_is_a_leap_year_in_the_julian_calendar_only():
    assert is_leap_year(1500, J) and not is_leap_year(1500, G)
    assert month_length(1500, 2, J) == 29 and month_length(1500, 2, G) == 28
    assert is_leap_year(1600, J) and is_leap_year(1600, G)
    assert is_leap_year(1900, J) and not is_leap_year(1900, G)
    assert not is_leap_year(1501, J)
    assert is_leap_year(0, J) and is_leap_year(0, G)
    assert is_leap_year(-4, J)


@pytest.mark.parametrize("calendar", [J, G])
def test_every_day_from_1400_to_1600_round_trips_and_counts_on_by_one(calendar):
    start = to_jdn(1400, 1, 1, calendar)
    end = to_jdn(1600, 12, 31, calendar)
    previous = None
    for jdn in range(start, end + 1):
        ymd = from_jdn(jdn, calendar)
        assert to_jdn(*ymd, calendar) == jdn
        if previous is not None:
            nxt_month = ymd.day == 1
            assert nxt_month or (ymd.year, ymd.month) == (previous.year, previous.month)
            assert nxt_month or ymd.day == previous.day + 1
        previous = ymd


@pytest.mark.parametrize("calendar", [J, G])
def test_whole_range_of_years_round_trips(calendar):
    for jdn in range(0, 5_000_000, 997):
        assert to_jdn(*from_jdn(jdn, calendar), calendar) == jdn


@pytest.mark.parametrize("calendar", [J, G])
def test_agrees_with_juliandate_over_every_day_from_1400_to_1600(calendar):
    juliandate = pytest.importorskip("juliandate")
    start = to_jdn(1400, 1, 1, calendar)
    end = to_jdn(1600, 12, 31, calendar)
    for jdn in range(start, end + 1):
        y, m, d = from_jdn(jdn, calendar)
        # juliandate counts from midnight, so the day starting at JD n - 0.5 is day number n
        if calendar == J:
            assert juliandate.from_julian(y, m, d) == jdn - 0.5
        else:
            assert juliandate.from_gregorian(y, m, d) == jdn - 0.5


def test_weekdays():
    assert weekday(to_jdn(2000, 1, 1, G)) == Weekday.SATURDAY
    assert weekday(to_jdn(1582, 10, 15, G)) == Weekday.FRIDAY
    assert weekday(to_jdn(1582, 10, 4, J)) == Weekday.THURSDAY
    assert weekday(to_jdn(1500, 3, 2, J)) == weekday(to_jdn(1500, 3, 12, G))
    # a week is seven days in either calendar
    assert weekday(to_jdn(1500, 3, 1, J) + 7) == weekday(to_jdn(1500, 3, 1, J))
    assert weekday(0) == Weekday.MONDAY


def test_the_nth_weekday_of_a_month():
    third_sunday = nth_weekday(1500, 3, Weekday.SUNDAY, 3, J)
    assert third_sunday is not None
    assert weekday(third_sunday) == Weekday.SUNDAY
    y, m, d = from_jdn(third_sunday, J)
    assert (y, m) == (1500, 3) and 15 <= d <= 21
    assert nth_weekday(1500, 3, Weekday.SUNDAY, 1, J) == third_sunday - 14
    last = nth_weekday(1500, 3, Weekday.SUNDAY, -1, J)
    assert last is not None and from_jdn(last, J).day >= 25
    assert nth_weekday(1500, 3, Weekday.SUNDAY, -3, J) == third_sunday


def test_nth_weekday_brute_force_over_two_hundred_years():
    for calendar in (J, G):
        for year in range(1400, 1600):
            for month in range(1, 13):
                first = to_jdn(year, month, 1, calendar)
                days = [first + i for i in range(month_length(year, month, calendar))]
                for dow in Weekday:
                    wanted = [d for d in days if weekday(d) == dow]
                    for n in range(1, 6):
                        assert nth_weekday(year, month, dow, n, calendar) == (
                            wanted[n - 1] if n <= len(wanted) else None
                        )
                    for n in range(-5, 0):
                        assert nth_weekday(year, month, dow, n, calendar) == (
                            wanted[n] if -n <= len(wanted) else None
                        )


def test_no_zeroth_weekday():
    with pytest.raises(ValueError):
        nth_weekday(1500, 3, Weekday.SUNDAY, 0, J)


@pytest.mark.parametrize(
    "ymd, calendar",
    [
        ((1500, 2, 30), J),
        ((1500, 2, 29), G),
        ((1501, 2, 29), J),
        ((1500, 4, 31), J),
        ((1500, 13, 1), J),
        ((1500, 0, 1), J),
        ((1500, 1, 0), J),
        ((10000, 1, 1), J),
        ((-5000, 1, 1), G),
    ],
)
def test_days_that_do_not_exist_are_an_error(ymd, calendar):
    with pytest.raises(InvalidDate):
        to_jdn(*ymd, calendar)


def test_first_and_last_day_of_a_year_a_month_a_day():
    assert first_and_last_day(1500, None, None, J) == (
        to_jdn(1500, 1, 1, J),
        to_jdn(1500, 12, 31, J),
    )
    assert first_and_last_day(1500, 2, None, J)[1] - to_jdn(1500, 2, 1, J) == 28
    assert first_and_last_day(1500, 2, None, G)[1] - to_jdn(1500, 2, 1, G) == 27
    assert first_and_last_day(1500, 3, 2, J) == (to_jdn(1500, 3, 2, J),) * 2
    with pytest.raises(InvalidDate):
        first_and_last_day(1500, None, 2, J)
