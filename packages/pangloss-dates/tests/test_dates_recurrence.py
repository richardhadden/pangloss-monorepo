"""Repeated events: the rule, its occurrences, and the keys that find them"""

import itertools

import pytest
from pangloss_dates.calendar import Calendar, Weekday, from_jdn, to_jdn, weekday
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
SUN = Weekday.SUNDAY


def day(y, m, d, calendar=J):
    return to_jdn(y, m, d, calendar)


def ymd(jdn, calendar=J):
    return tuple(from_jdn(jdn, calendar))


def test_every_sunday():
    rule = RecurrenceRule(Frequency.WEEKLY, weekdays=(SUN,))
    days = occurrences(rule, day(1500, 3, 1), day(1500, 3, 31), J)
    assert all(weekday(d) == SUN for d in days)
    assert len(days) in (4, 5)
    assert days == sorted(days) and days[1] - days[0] == 7
    assert not occurs_on(rule, days[0] + 1, J)


def test_two_weekdays():
    rule = RecurrenceRule(Frequency.WEEKLY, weekdays=(SUN, Weekday.WEDNESDAY))
    days = occurrences(rule, day(1500, 3, 1), day(1500, 3, 14), J)
    assert {weekday(d) for d in days} == {SUN, Weekday.WEDNESDAY}
    assert len(days) == 4


def test_every_second_week_counts_from_the_anchor():
    rule = RecurrenceRule(Frequency.WEEKLY, weekdays=(SUN,), interval=2)
    anchor = day(1500, 3, 2)
    first_sunday = anchor + (SUN - weekday(anchor)) % 7
    days = occurrences(rule, anchor, anchor + 70, J, anchor)
    assert days[0] == first_sunday and all(
        b - a == 14 for a, b in itertools.pairwise(days)
    )
    with pytest.raises(InvalidRule):
        occurs_on(rule, first_sunday, J)  # no anchor


def test_the_third_sunday_of_march():
    rule = RecurrenceRule(Frequency.YEARLY, weekdays=(SUN,), nth=3, month=3)
    days = occurrences(rule, day(1500, 1, 1), day(1510, 12, 31), J)
    assert len(days) == 11
    for d in days:
        _y, m, dom = ymd(d)
        assert m == 3 and weekday(d) == SUN and 15 <= dom <= 21
    # the same rule in the Gregorian calendar is another set of days
    assert days != occurrences(rule, day(1500, 1, 1), day(1510, 12, 31), G)[: len(days)]


def test_the_last_friday_of_every_month():
    rule = RecurrenceRule(Frequency.MONTHLY, weekdays=(Weekday.FRIDAY,), nth=-1)
    days = occurrences(rule, day(1500, 1, 1), day(1500, 12, 31), J)
    assert len(days) == 12
    for d in days:
        _y, m, _ = ymd(d)
        assert weekday(d) == Weekday.FRIDAY and ymd(d + 7)[1] != m


def test_monthly_on_a_day_of_the_month_skips_short_months():
    rule = RecurrenceRule(Frequency.MONTHLY, month_day=31)
    days = occurrences(rule, day(1500, 1, 1), day(1500, 12, 31), J)
    assert [ymd(d)[1] for d in days] == [1, 3, 5, 7, 8, 10, 12]


def test_yearly_on_the_21st_of_march_and_the_leap_day():
    rule = RecurrenceRule(Frequency.YEARLY, month=3, month_day=21)
    assert [
        ymd(d) for d in occurrences(rule, day(1500, 1, 1), day(1502, 12, 31), J)
    ] == [
        (1500, 3, 21),
        (1501, 3, 21),
        (1502, 3, 21),
    ]
    leap = RecurrenceRule(Frequency.YEARLY, month=2, month_day=29)
    julian = occurrences(leap, day(1496, 1, 1), day(1504, 12, 31), J)
    assert [ymd(d)[0] for d in julian] == [1496, 1500, 1504]
    gregorian = occurrences(leap, day(1496, 1, 1), day(1504, 12, 31), G)
    assert [ymd(d, G)[0] for d in gregorian] == [1496, 1504]


def test_every_second_month_and_every_second_year():
    monthly = RecurrenceRule(Frequency.MONTHLY, month_day=1, interval=2)
    anchor = day(1500, 1, 1)
    days = occurrences(monthly, anchor, day(1500, 12, 31), J, anchor)
    assert [ymd(d)[1] for d in days] == [1, 3, 5, 7, 9, 11]
    yearly = RecurrenceRule(Frequency.YEARLY, month=3, month_day=21, interval=2)
    days = occurrences(yearly, day(1500, 1, 1), day(1506, 12, 31), J, day(1501, 1, 1))
    assert [ymd(d)[0] for d in days] == [1501, 1503, 1505]


def test_excluded_days_are_left_out():
    sunday = day(1500, 3, 1)
    sunday += (SUN - weekday(sunday)) % 7
    assert weekday(sunday) == SUN
    rule = RecurrenceRule(
        Frequency.WEEKLY, weekdays=(SUN,), excluded_days=frozenset({sunday})
    )
    assert not occurs_on(rule, sunday, J)
    assert occurs_on(rule, sunday + 7, J)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"frequency": Frequency.WEEKLY},
        {"frequency": Frequency.WEEKLY, "weekdays": (SUN,), "month_day": 3},
        {"frequency": Frequency.WEEKLY, "weekdays": (SUN, SUN)},
        {"frequency": Frequency.WEEKLY, "weekdays": (SUN,), "interval": 0},
        {"frequency": Frequency.MONTHLY},
        {"frequency": Frequency.MONTHLY, "month_day": 3, "nth": 1, "weekdays": (SUN,)},
        {"frequency": Frequency.MONTHLY, "nth": 1},
        {"frequency": Frequency.MONTHLY, "nth": 1, "weekdays": (SUN, Weekday.MONDAY)},
        {"frequency": Frequency.MONTHLY, "month_day": 3, "month": 3},
        {"frequency": Frequency.MONTHLY, "nth": 0, "weekdays": (SUN,)},
        {"frequency": Frequency.YEARLY, "month_day": 3},
        {"frequency": Frequency.YEARLY, "month": 13, "month_day": 3},
        {"frequency": Frequency.YEARLY, "month": 3, "month_day": 32},
    ],
)
def test_rules_that_do_not_say_a_day_are_refused(kwargs):
    with pytest.raises(InvalidRule):
        RecurrenceRule(**kwargs)


RULES = [
    RecurrenceRule(Frequency.WEEKLY, weekdays=(SUN, Weekday.THURSDAY)),
    RecurrenceRule(Frequency.MONTHLY, month_day=29),
    RecurrenceRule(Frequency.MONTHLY, weekdays=(Weekday.MONDAY,), nth=2),
    RecurrenceRule(Frequency.MONTHLY, weekdays=(Weekday.MONDAY,), nth=-1),
    RecurrenceRule(Frequency.MONTHLY, weekdays=(Weekday.SATURDAY,), nth=5),
    RecurrenceRule(Frequency.YEARLY, month=2, month_day=29),
    RecurrenceRule(Frequency.YEARLY, month=3, weekdays=(SUN,), nth=3),
    RecurrenceRule(Frequency.YEARLY, month=10, weekdays=(Weekday.FRIDAY,), nth=-1),
]


@pytest.mark.parametrize("calendar", [J, G])
@pytest.mark.parametrize("rule", RULES)
def test_a_day_the_rule_falls_on_always_has_one_of_the_rules_keys(rule, calendar):
    """The keys never miss: the database is asked for the rules whose keys match a day, and each is then checked"""
    keys = set(pattern_keys(rule))
    for d in range(day(1496, 1, 1, calendar), day(1504, 12, 31, calendar) + 1):
        if occurs_on(rule, d, calendar):
            assert keys & set(day_keys(d, calendar)), (rule, ymd(d, calendar))


@pytest.mark.parametrize("rule", RULES)
def test_the_keys_cut_the_candidates_down_a_lot(rule):
    start, end = day(1500, 1, 1), day(1500, 12, 31)
    matching = [
        d
        for d in range(start, end + 1)
        if set(pattern_keys(rule)) & set(day_keys(d, J))
    ]
    assert len(matching) < (end - start + 1) * 0.6


def test_the_keys_of_a_day():
    keys = day_keys(day(1500, 3, 21), J)
    assert f"weekday:{weekday(day(1500, 3, 21)).value}" in keys
    assert "monthday:21" in keys and "yearday:3-21" in keys
    assert any(k.startswith("nth:3:") for k in keys)
