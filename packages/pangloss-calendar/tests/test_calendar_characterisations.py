"""The days a characterisation's rule falls on, worked out (pure)"""

from uuid import uuid4

from pangloss_calendar.characterisations import (
    Characterisation,
    days_between,
    falls_on_day,
    feast_keys,
    moveable,
    on_day,
)
from pangloss_dates.calendar import Calendar, Weekday, from_jdn, to_jdn, weekday
from pangloss_dates.easter import easter
from pangloss_dates.recurrence import Frequency, RecurrenceRule, occurrences

J = Calendar.JULIAN
G = Calendar.GREGORIAN


def make(rule, calendar=J, first=None, last=None, label="x", anchor=None):
    return Characterisation(
        id=uuid4(),
        label=label,
        type="FeastDay",
        rule=rule,
        calendar=calendar,
        first=first,
        last=last,
        anchor=anchor if anchor is not None else first,
    )


def yearly(month, day):
    return RecurrenceRule(Frequency.YEARLY, month=month, month_day=day)


def test_a_fixed_day_is_on_that_date_in_the_calendar_of_its_rule():
    benedict = make(yearly(3, 21))
    days = days_between(benedict, to_jdn(1500, 1, 1, J), to_jdn(1502, 12, 31, J))
    assert [tuple(from_jdn(d, J)) for d in days] == [
        (1500, 3, 21),
        (1501, 3, 21),
        (1502, 3, 21),
    ]
    in_gregorian = make(yearly(3, 21), calendar=G)
    other = days_between(in_gregorian, to_jdn(1500, 1, 1, J), to_jdn(1502, 12, 31, J))
    assert tuple(from_jdn(other[0], G)) == (1500, 3, 21)
    assert other[0] != days[0]


def test_days_between_agrees_with_trying_every_day():
    rules = [
        yearly(3, 21),
        yearly(2, 29),
        yearly(1, 31),
        RecurrenceRule(Frequency.YEARLY, month=3, nth=3, weekdays=(Weekday.SUNDAY,)),
        RecurrenceRule(Frequency.YEARLY, month=3, nth=-1, weekdays=(Weekday.FRIDAY,)),
        RecurrenceRule(Frequency.YEARLY, easter_offset=49),
        RecurrenceRule(Frequency.YEARLY, easter_offset=-47, interval=2),
        RecurrenceRule(Frequency.WEEKLY, weekdays=(Weekday.SUNDAY,)),
    ]
    first, last = to_jdn(1498, 1, 1, J), to_jdn(1505, 12, 31, J)
    for rule in rules:
        for calendar in (J, G):
            c = make(rule, calendar=calendar, anchor=first)
            assert days_between(c, first, last) == occurrences(
                rule, first, last, calendar, first
            )


def test_the_lifetime_limits_the_days():
    c = make(yearly(3, 21), first=to_jdn(1500, 1, 1, J), last=to_jdn(1502, 12, 31, J))
    days = days_between(c, to_jdn(1490, 1, 1, J), to_jdn(1520, 12, 31, J))
    assert [from_jdn(d, J).year for d in days] == [1500, 1501, 1502]
    assert falls_on_day(c, to_jdn(1501, 3, 21, J))
    assert not falls_on_day(c, to_jdn(1503, 3, 21, J))
    assert not falls_on_day(c, to_jdn(1499, 3, 21, J))


def test_a_characterisation_without_a_rule_or_on_a_feast_has_no_days_of_its_own():
    assert days_between(make(None), 0, 3_000_000) == []
    on_feast = make(RecurrenceRule(Frequency.YEARLY, feast="abc"))
    assert days_between(on_feast, to_jdn(1500, 1, 1, J), to_jdn(1501, 1, 1, J)) == []
    assert not falls_on_day(on_feast, to_jdn(1500, 3, 21, J))


def test_what_is_on_a_day_and_the_keys_a_repeated_event_can_fall_on():
    benedict = make(yearly(3, 21), label="Benedict")
    pentecost = make(
        RecurrenceRule(Frequency.YEARLY, easter_offset=49), label="Pentecost"
    )
    day = to_jdn(1500, 3, 21, J)
    assert [c.label for c in on_day([benedict, pentecost], day)] == ["Benedict"]
    assert feast_keys([benedict, pentecost], day) == [benedict.feast_key]
    assert benedict.feast_key == f"feast:{benedict.id}"
    assert feast_keys([benedict], day + 1) == []


def test_the_days_that_move_with_easter_are_in_order_and_only_those():
    pentecost = make(
        RecurrenceRule(Frequency.YEARLY, easter_offset=49), label="Pentecost"
    )
    shrove = make(RecurrenceRule(Frequency.YEARLY, easter_offset=-47), label="Shrove")
    fixed = make(yearly(3, 21))
    found = moveable([pentecost, fixed, shrove], 1500, J)
    assert [(c.label, d) for c, d in found] == [
        ("Shrove", easter(1500, J) - 47),
        ("Pentecost", easter(1500, J) + 49),
    ]
    assert weekday(found[1][1]) == Weekday.SUNDAY


def test_days_between_applies_the_leap_shift():
    from pangloss_dates.calendar import is_leap_year

    matthias = make(
        RecurrenceRule(Frequency.YEARLY, month=2, month_day=24, leap_shift=True)
    )
    first, last = to_jdn(1496, 1, 1, J), to_jdn(1504, 12, 31, J)
    days = days_between(matthias, first, last)
    assert days == occurrences(matthias.rule, first, last, J, first)
    assert [from_jdn(d, J).day for d in days] == [
        25 if is_leap_year(y, J) else 24 for y in range(1496, 1505)
    ]
