"""Easter in both calendars, and the rules that move with it"""

import re

import pytest
from pangloss_dates import (
    Calendar,
    Frequency,
    InvalidRule,
    RecurrenceRule,
    Weekday,
    convert,
    describe,
    from_jdn,
    occurrences,
    occurs_on,
    to_jdn,
    weekday,
)
from pangloss_dates.calendar import MAX_YEAR, MIN_YEAR
from pangloss_dates.easter import easter
from pangloss_dates.recurrence import day_keys, pattern_keys

J = Calendar.JULIAN
G = Calendar.GREGORIAN

# printed tables (Western: Gregorian; Orthodox: Julian reckoning, given here in the Gregorian calendar)
WESTERN = {
    1818: (3, 22),
    1943: (4, 25),
    1961: (4, 2),
    2000: (4, 23),
    2024: (3, 31),
    2025: (4, 20),
    2038: (4, 25),
}
ORTHODOX_IN_GREGORIAN = {
    2000: (4, 30),
    2021: (5, 2),
    2022: (4, 24),
    2023: (4, 16),
    2024: (5, 5),
    2025: (4, 20),
}


@pytest.mark.parametrize("year,md", WESTERN.items())
def test_western_easter_agrees_with_the_printed_table(year, md):
    assert tuple(from_jdn(easter(year, G), G))[1:] == md


@pytest.mark.parametrize("year,md", ORTHODOX_IN_GREGORIAN.items())
def test_julian_easter_is_the_orthodox_one(year, md):
    assert tuple(from_jdn(easter(year, J), G))[1:] == md


def test_julian_easter_of_2000_is_17_april_julian():
    assert tuple(from_jdn(easter(2000, J), J)) == (2000, 4, 17)


@pytest.mark.parametrize("calendar", [J, G])
def test_easter_is_a_sunday_between_22_march_and_25_april_in_its_calendar(calendar):
    for year in range(1400, 1801):
        jdn = easter(year, calendar)
        assert weekday(jdn) == Weekday.SUNDAY
        assert to_jdn(year, 3, 22, calendar) <= jdn <= to_jdn(year, 4, 25, calendar)


def _knuth_easter(year):
    """The Gregorian Easter by Knuth's method (The Art of Computer Programming, 1.3.2, exercise 14): an
    independent reckoning, from the golden number and the epact"""
    golden = year % 19 + 1
    century = year // 100 + 1
    skipped_leap_days = 3 * century // 4 - 12
    moon_correction = (8 * century + 5) // 25 - 5
    sunday = 5 * year // 4 - skipped_leap_days - 10
    epact = (11 * golden + 20 + moon_correction - skipped_leap_days) % 30
    if (epact == 25 and golden > 11) or epact == 24:
        epact += 1
    full_moon = 44 - epact
    if full_moon < 21:
        full_moon += 30
    n = full_moon + 7 - (sunday + full_moon) % 7
    return (year, 4, n - 31) if n > 31 else (year, 3, n)


def test_western_easter_agrees_with_knuths_method_in_every_year():
    """Printed tables and dateutil cover a few centuries; a slip in Meeus's arithmetic can show in only a
    handful of years of the whole range"""
    for year in range(MIN_YEAR, MAX_YEAR + 1):
        assert from_jdn(easter(year, G), G) == _knuth_easter(year), year


def test_describe_names_a_day_in_both_calendars():
    names = describe(to_jdn(1500, 2, 29, J))
    assert tuple(names.julian) == (1500, 2, 29)
    assert tuple(names.gregorian) == (1500, 3, 10)
    assert names.weekday == weekday(to_jdn(1500, 2, 29, J))
    assert convert(1500, 2, 29, J, G) == names.gregorian


def test_a_rule_on_easter():
    pentecost = RecurrenceRule(Frequency.YEARLY, easter_offset=49)
    for calendar in (J, G):
        days = occurrences(
            pentecost,
            to_jdn(1500, 1, 1, calendar),
            to_jdn(1502, 12, 31, calendar),
            calendar,
        )
        assert days == [easter(y, calendar) + 49 for y in (1500, 1501, 1502)]
        assert all(weekday(d) == Weekday.SUNDAY for d in days)


def test_a_rule_before_easter_and_every_second_year():
    shrove = RecurrenceRule(Frequency.YEARLY, easter_offset=-47, interval=2)
    anchor = to_jdn(1500, 1, 1, J)
    days = occurrences(shrove, anchor, to_jdn(1503, 12, 31, J), J, anchor)
    assert days == [easter(y, J) - 47 for y in (1500, 1502)]


def test_the_years_of_a_rule_on_easter_count_from_the_anchor_in_the_rules_calendar():
    """1 January 1501 (Gregorian) is still 1500 in the Julian calendar, so the anchor's year must be read in
    the calendar asked for; and an interval of 3 tells counting forward from counting backward"""
    rule = RecurrenceRule(Frequency.YEARLY, easter_offset=0, interval=3)
    anchor = to_jdn(1501, 1, 1, G)
    days = occurrences(rule, to_jdn(1500, 1, 1, G), to_jdn(1507, 12, 31, G), G, anchor)
    assert days == [easter(y, G) for y in (1501, 1504, 1507)]


def test_the_keys_of_a_rule_on_easter_are_among_the_keys_of_its_days():
    for offset in (-80, -47, 0, 1, 49, 250):
        rule = RecurrenceRule(Frequency.YEARLY, easter_offset=offset)
        assert pattern_keys(rule) == [f"easter:{offset:+d}"]
        for calendar in (J, G):
            for year in range(1500, 1516):
                day = easter(year, calendar) + offset
                assert pattern_keys(rule)[0] in day_keys(day, calendar)
                assert occurs_on(rule, day, calendar)
                assert not occurs_on(rule, day + 1, calendar)


def test_a_rule_on_a_feast_is_answered_with_the_keys_of_the_day():
    rule = RecurrenceRule(Frequency.YEARLY, feast="sarum:st-benedict")
    day = to_jdn(1500, 3, 21, J)
    assert pattern_keys(rule) == ["feast:sarum:st-benedict"]
    assert not occurs_on(rule, day, J)
    assert occurs_on(rule, day, J, extra_keys=["feast:sarum:st-benedict"])
    assert "feast:sarum:st-benedict" in day_keys(day, J, ["feast:sarum:st-benedict"])
    assert "feast:sarum:st-benedict" not in day_keys(day, J)
    assert occurrences(
        rule,
        day - 3,
        day + 3,
        J,
        extra_keys_of=lambda d: ["feast:sarum:st-benedict"] if d == day else [],
    ) == [day]


IS_YEARLY = "a rule on Easter or a feast is yearly"
TAKES_NO = "a rule on Easter or a feast takes no weekday, nth, month or month_day"
SUNDAY = (Weekday.SUNDAY,)


@pytest.mark.parametrize(
    "kwargs, message",
    [
        (
            {"frequency": Frequency.YEARLY, "easter_offset": 1, "feast": "a"},
            "give easter_offset or feast, not both",
        ),
        ({"frequency": Frequency.MONTHLY, "easter_offset": 1}, IS_YEARLY),
        ({"frequency": Frequency.YEARLY, "easter_offset": 1, "month": 3}, TAKES_NO),
        ({"frequency": Frequency.YEARLY, "feast": "a", "month_day": 3}, TAKES_NO),
        (
            {"frequency": Frequency.YEARLY, "easter_offset": 1, "weekdays": SUNDAY},
            TAKES_NO,
        ),
        ({"frequency": Frequency.YEARLY, "feast": "a", "nth": 1}, TAKES_NO),
        (
            {"frequency": Frequency.YEARLY, "easter_offset": 251},
            "easter_offset 251 is not from -80 to 250",
        ),
        (
            {"frequency": Frequency.YEARLY, "easter_offset": -81},
            "easter_offset -81 is not from -80 to 250",
        ),
        ({"frequency": Frequency.YEARLY, "feast": " "}, "a feast needs a key"),
        ({"frequency": Frequency.WEEKLY, "weekdays": SUNDAY, "feast": "a"}, IS_YEARLY),
    ],
)
def test_a_rule_that_says_two_things_or_none_is_refused(kwargs, message):
    """(The message is matched, so that a check that refuses first does not hide a missing one)"""
    with pytest.raises(InvalidRule, match=f"^{re.escape(message)}$"):
        RecurrenceRule(**kwargs)


def test_easter_agrees_with_dateutil_over_1400_to_1800():
    dateutil_easter = pytest.importorskip("dateutil.easter")
    for year in range(1400, 1801):
        julian = dateutil_easter.easter(
            year, dateutil_easter.EASTER_JULIAN
        )  # (Julian date, as a plain date)
        assert tuple(from_jdn(easter(year, J), J)) == (year, julian.month, julian.day)
        western = dateutil_easter.easter(year, dateutil_easter.EASTER_WESTERN)
        assert tuple(from_jdn(easter(year, G), G)) == (year, western.month, western.day)


def test_a_feast_on_24_february_is_a_day_later_in_a_leap_year_only_with_leap_shift():
    from pangloss_dates import is_leap_year

    matthias = RecurrenceRule(Frequency.YEARLY, month=2, month_day=24, leap_shift=True)
    plain = RecurrenceRule(Frequency.YEARLY, month=2, month_day=24)
    for calendar in (J, G):
        for year in range(1496, 1505):
            leap = is_leap_year(year, calendar)
            moved = to_jdn(year, 2, 25 if leap else 24, calendar)
            assert occurs_on(matthias, moved, calendar)
            assert not occurs_on(matthias, moved + (-1 if leap else 1), calendar)
            assert occurs_on(plain, to_jdn(year, 2, 24, calendar), calendar)
            # the keys never miss
            assert any(
                key in day_keys(moved, calendar) for key in pattern_keys(matthias)
            )
    assert pattern_keys(matthias) == ["yearday:2-24", "yearday:2-25"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {
            "frequency": Frequency.YEARLY,
            "month": 3,
            "month_day": 24,
            "leap_shift": True,
        },
        {
            "frequency": Frequency.YEARLY,
            "month": 2,
            "month_day": 23,
            "leap_shift": True,
        },
        {
            "frequency": Frequency.YEARLY,
            "month": 2,
            "month_day": 29,
            "leap_shift": True,
        },
        {"frequency": Frequency.YEARLY, "easter_offset": 3, "leap_shift": True},
        {"frequency": Frequency.MONTHLY, "month_day": 24, "leap_shift": True},
    ],
)
def test_leap_shift_is_only_for_a_yearly_day_from_24_to_28_february(kwargs):
    with pytest.raises(
        InvalidRule,
        match="^leap_shift is for a yearly rule on a day from 24 to 28 February$",
    ):
        RecurrenceRule(**kwargs)


@pytest.mark.parametrize("month_day", [24, 28])
def test_leap_shift_takes_both_ends_of_its_days(month_day):
    RecurrenceRule(Frequency.YEARLY, month=2, month_day=month_day, leap_shift=True)
