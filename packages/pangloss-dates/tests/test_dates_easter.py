"""Easter in both calendars, and the rules that move with it"""

import pytest
from pangloss_dates.calendar import (
    Calendar,
    Weekday,
    convert,
    describe,
    from_jdn,
    to_jdn,
    weekday,
)
from pangloss_dates.easter import easter
from pangloss_dates.recurrence import (
    Frequency,
    InvalidRule,
    RecurrenceRule,
    day_keys,
    occurrences,
    occurs_on,
    pattern_keys,
)

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


@pytest.mark.parametrize(
    "kwargs",
    [
        {"frequency": Frequency.YEARLY, "easter_offset": 1, "feast": "a"},
        {"frequency": Frequency.MONTHLY, "easter_offset": 1},
        {"frequency": Frequency.YEARLY, "easter_offset": 1, "month": 3},
        {"frequency": Frequency.YEARLY, "feast": "a", "month_day": 3},
        {"frequency": Frequency.YEARLY, "easter_offset": 251},
        {"frequency": Frequency.YEARLY, "easter_offset": -81},
        {"frequency": Frequency.YEARLY, "feast": " "},
        {"frequency": Frequency.WEEKLY, "weekdays": (Weekday.SUNDAY,), "feast": "a"},
    ],
)
def test_a_rule_that_says_two_things_or_none_is_refused(kwargs):
    with pytest.raises(InvalidRule):
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
