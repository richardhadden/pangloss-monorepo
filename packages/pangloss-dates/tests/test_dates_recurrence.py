"""Repeated events: the rule, its occurrences, and the keys that find them"""

import itertools
import re

import pytest
from pangloss_dates import (
    Calendar,
    Frequency,
    InvalidRule,
    RecurrenceRule,
    Weekday,
    from_jdn,
    occurrences,
    occurs_on,
    to_jdn,
    weekday,
)
from pangloss_dates.recurrence import day_keys, pattern_keys

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


def test_every_third_month_counts_on_from_the_anchors_month_into_the_next_year():
    """(An interval of 2 cannot tell counting forward from counting backward, nor a year of 12 months from 13)"""
    rule = RecurrenceRule(Frequency.MONTHLY, month_day=1, interval=3)
    anchor = day(1500, 2, 1)
    days = occurrences(rule, anchor, day(1501, 12, 31), J, anchor)
    assert [ymd(d)[:2] for d in days] == [
        (1500, 2),
        (1500, 5),
        (1500, 8),
        (1500, 11),
        (1501, 2),
        (1501, 5),
        (1501, 8),
        (1501, 11),
    ]


def test_the_anchors_month_is_read_in_the_rules_calendar():
    """1 February 1501 (Gregorian) is 22 January in the Julian calendar; an interval of 5 and an anchor in 1501
    also tell (year - anchor year) from (year + anchor year)"""
    rule = RecurrenceRule(Frequency.MONTHLY, month_day=1, interval=5)
    anchor = day(1501, 2, 1, G)
    days = occurrences(rule, anchor, day(1502, 12, 31, G), G, anchor)
    assert [ymd(d, G)[:2] for d in days] == [
        (1501, 2),
        (1501, 7),
        (1501, 12),
        (1502, 5),
        (1502, 10),
    ]


def test_the_weeks_from_the_end_of_a_month_count_in_its_own_calendar():
    """February 1500 has 29 days in the Julian calendar (and 28 in the Gregorian one)"""
    for d, from_end in [(29, -1), (22, -2)]:
        jdn = day(1500, 2, d)
        assert f"nth:{from_end}:{weekday(jdn).value}" in day_keys(jdn, J)


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


EITHER = "give either month_day, or nth with one weekday (not both, not neither)"
NTH_AND_ONE = "the nth weekday of a month needs nth and one weekday"


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"frequency": Frequency.WEEKLY}, "a weekly rule needs at least one weekday"),
        (
            {"frequency": Frequency.WEEKLY, "weekdays": (SUN,), "month_day": 3},
            "a weekly rule takes only weekdays and an interval",
        ),
        (
            {"frequency": Frequency.WEEKLY, "weekdays": (SUN,), "nth": 1},
            "a weekly rule takes only weekdays and an interval",
        ),
        (
            {"frequency": Frequency.WEEKLY, "weekdays": (SUN,), "month": 3},
            "a weekly rule takes only weekdays and an interval",
        ),
        (
            {"frequency": Frequency.WEEKLY, "weekdays": (SUN, SUN)},
            "a weekday is given twice",
        ),
        (
            {"frequency": Frequency.WEEKLY, "weekdays": (SUN,), "interval": 0},
            "interval must be 1 or more",
        ),
        ({"frequency": Frequency.MONTHLY}, EITHER),
        (
            {
                "frequency": Frequency.MONTHLY,
                "month_day": 3,
                "nth": 1,
                "weekdays": (SUN,),
            },
            EITHER,
        ),
        ({"frequency": Frequency.MONTHLY, "nth": 1}, NTH_AND_ONE),
        ({"frequency": Frequency.MONTHLY, "weekdays": (SUN,)}, NTH_AND_ONE),
        (
            {
                "frequency": Frequency.MONTHLY,
                "nth": 1,
                "weekdays": (SUN, Weekday.MONDAY),
            },
            NTH_AND_ONE,
        ),
        (
            {"frequency": Frequency.MONTHLY, "month_day": 3, "month": 3},
            "a monthly rule does not take a month",
        ),
        (
            {"frequency": Frequency.MONTHLY, "nth": 0, "weekdays": (SUN,)},
            "nth is 1 to 5, or -1 to -5 from the end of the month",
        ),
        (
            {"frequency": Frequency.MONTHLY, "nth": 6, "weekdays": (SUN,)},
            "nth is 1 to 5, or -1 to -5 from the end of the month",
        ),
        (
            {"frequency": Frequency.MONTHLY, "nth": -6, "weekdays": (SUN,)},
            "nth is 1 to 5, or -1 to -5 from the end of the month",
        ),
        (
            {"frequency": Frequency.YEARLY, "month_day": 3},
            "a yearly rule needs a month",
        ),
        (
            {"frequency": Frequency.YEARLY, "month": 13, "month_day": 3},
            "month 13 is not from 1 to 12",
        ),
        (
            {"frequency": Frequency.YEARLY, "month": 3, "month_day": 32},
            "month_day 32 is not from 1 to 31",
        ),
    ],
)
def test_rules_that_do_not_say_a_day_are_refused(kwargs, message):
    """(The message is matched, so that a check that refuses first does not hide a missing one)"""
    with pytest.raises(InvalidRule, match=f"^{re.escape(message)}$"):
        RecurrenceRule(**kwargs)


def test_the_ends_of_the_ranges_are_taken():
    """(Built here rather than only in RULES below, which is built before any test runs)"""
    RecurrenceRule(Frequency.YEARLY, month=12, month_day=31)
    RecurrenceRule(Frequency.YEARLY, month=1, month_day=1)
    for nth in (5, -5):
        RecurrenceRule(Frequency.MONTHLY, weekdays=(SUN,), nth=nth)


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
