"""Repeated events: a rule over day numbers, never a list of days.

"Every Sunday", "the third Sunday of March", "on the 21st of each month", "21 March every second year". The rule
is applied in a calendar (the third Sunday of March 1500 is a different day in the Julian and the Gregorian
calendar). When a rule repeats every second week (or month, or year) it counts from an **anchor** day, usually the
start of the lifetime of the order (weeks are the seven days from the anchor; months and years are the calendar's
own); the anchor is not needed for an interval of 1.

This module knows nothing of when the order was in force: that is the bounds of the `Recurrence` (see
`pangloss_dates.bounds`). It gives three things:

- `occurs_on(rule, day, ...)` and `occurrences(rule, first, last, ...)`, the exact rule;
- `pattern_keys(rule)`, a short list of keys that every day the rule falls on has among its `day_keys(day, ...)`.
  The keys are stored on the rule so "everything that happens on this day" can ask the database for the rules with a
  matching key, and then check each with `occurs_on`. A key match is necessary, not sufficient (it ignores the
  interval and the excluded days).
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import StrEnum

from pangloss_dates.calendar import (
    Calendar,
    Weekday,
    from_jdn,
    is_leap_year,
    month_length,
    nth_weekday,
    weekday,
)
from pangloss_dates.easter import easter

EASTER_OFFSETS = range(-80, 251)
"""Far enough to keep the day in the year of its Easter (Easter is from 22 March to 25 April)"""


class Frequency(StrEnum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class InvalidRule(ValueError):
    """The rule does not say a day"""


@dataclass(frozen=True)
class RecurrenceRule:
    """- weekly: `weekdays` (every Sunday and Wednesday)
    - monthly: `month_day` (the 21st), or `nth` with one weekday (the third Sunday; -1 is the last)
    - yearly: `month`, and `month_day` or `nth` with one weekday (21 March; the third Sunday of March)
    - yearly, `leap_shift`: a fixed day from 24 to 28 February that falls a day later in a leap year (in the old Roman reckoning
      the leap day was made by repeating 24 February, so St Matthias is 24 February, and 25 in a leap year)
    - yearly, moving with Easter: `easter_offset` alone, in days (-47 is Shrove Tuesday, 49 is Pentecost)
    - yearly, on a feast: `feast` alone, a key that the owner of the feasts (`pangloss_calendar`) works out the days of;
      `occurs_on` is told the feasts of the day in `extra_keys`

    `interval` is every 2nd, 3rd... week, month or year. `excluded_days` are day numbers that are left out."""

    frequency: Frequency
    weekdays: tuple[Weekday, ...] = ()
    nth: int | None = None
    month: int | None = None
    month_day: int | None = None
    interval: int = 1
    excluded_days: frozenset[int] = field(default_factory=frozenset)
    easter_offset: int | None = None
    feast: str | None = None
    leap_shift: bool = False

    def __post_init__(self):
        if self.interval < 1:
            raise InvalidRule("interval must be 1 or more")
        if self.month is not None and not 1 <= self.month <= 12:
            raise InvalidRule(f"month {self.month} is not from 1 to 12")
        if self.month_day is not None and not 1 <= self.month_day <= 31:
            raise InvalidRule(f"month_day {self.month_day} is not from 1 to 31")
        if self.nth is not None and (self.nth == 0 or not -5 <= self.nth <= 5):
            raise InvalidRule("nth is 1 to 5, or -1 to -5 from the end of the month")
        if len(set(self.weekdays)) != len(self.weekdays):
            raise InvalidRule("a weekday is given twice")
        if self.leap_shift and not (
            self.frequency == Frequency.YEARLY
            and self.month == 2
            and self.month_day is not None
            and 24 <= self.month_day <= 28
            and self.easter_offset is None
            and self.feast is None
        ):
            raise InvalidRule(
                "leap_shift is for a yearly rule on a day from 24 to 28 February"
            )
        if self.easter_offset is not None or self.feast is not None:
            self._check_moving()
            return
        if self.frequency == Frequency.WEEKLY:
            if not self.weekdays:
                raise InvalidRule("a weekly rule needs at least one weekday")
            if (
                self.nth is not None
                or self.month is not None
                or self.month_day is not None
            ):
                raise InvalidRule("a weekly rule takes only weekdays and an interval")
            return
        if self.frequency == Frequency.MONTHLY and self.month is not None:
            raise InvalidRule("a monthly rule does not take a month")
        if self.frequency == Frequency.YEARLY and self.month is None:
            raise InvalidRule("a yearly rule needs a month")
        by_day = self.month_day is not None
        by_weekday = self.nth is not None or bool(self.weekdays)
        if by_day == by_weekday:
            raise InvalidRule(
                "give either month_day, or nth with one weekday (not both, not neither)"
            )
        if by_weekday and (self.nth is None or len(self.weekdays) != 1):
            raise InvalidRule("the nth weekday of a month needs nth and one weekday")

    def _check_moving(self):
        if self.easter_offset is not None and self.feast is not None:
            raise InvalidRule("give easter_offset or feast, not both")
        if self.frequency != Frequency.YEARLY:
            raise InvalidRule("a rule on Easter or a feast is yearly")
        if (
            self.weekdays
            or self.nth is not None
            or self.month is not None
            or self.month_day is not None
        ):
            raise InvalidRule(
                "a rule on Easter or a feast takes no weekday, nth, month or month_day"
            )
        if self.easter_offset is not None and self.easter_offset not in EASTER_OFFSETS:
            raise InvalidRule(
                f"easter_offset {self.easter_offset} is not from {EASTER_OFFSETS.start} to {EASTER_OFFSETS.stop - 1}"
            )
        if self.feast is not None and not self.feast.strip():
            raise InvalidRule("a feast needs a key")


def _needs_anchor(rule: RecurrenceRule, anchor: int | None) -> int:
    if anchor is None:
        raise InvalidRule("a rule with an interval over 1 needs an anchor day")
    return anchor


def occurs_on(
    rule: RecurrenceRule,
    day: int,
    calendar: Calendar,
    anchor: int | None = None,
    extra_keys: Iterable[str] = (),
) -> bool:
    """Whether the rule falls on the day (the lifetime of the order is not considered). `extra_keys` are the keys
    the caller knows the day to have that cannot be worked out here (`feast:...`)"""
    if day in rule.excluded_days:
        return False
    year, month, day_of_month = from_jdn(day, calendar)
    if rule.easter_offset is not None or rule.feast is not None:
        if rule.feast is not None:
            on_it = f"feast:{rule.feast}" in set(extra_keys)
        else:
            on_it = day == easter(year, calendar) + (rule.easter_offset or 0)
        return on_it and _in_interval(rule, year, calendar, anchor)
    if rule.frequency == Frequency.WEEKLY:
        if weekday(day) not in rule.weekdays:
            return False
        if rule.interval > 1:
            # weeks of seven days counted from the anchor, so "every second week from this day" starts with this week
            return ((day - _needs_anchor(rule, anchor)) // 7) % rule.interval == 0
        return True
    if rule.frequency == Frequency.YEARLY and month != rule.month:
        return False
    if rule.month_day is not None:
        shifted = rule.leap_shift and is_leap_year(year, calendar)
        if day_of_month != rule.month_day + (1 if shifted else 0):
            return False
    elif nth_weekday(year, month, rule.weekdays[0], rule.nth or 1, calendar) != day:
        return False
    if rule.interval > 1:
        a_year, a_month, _ = from_jdn(_needs_anchor(rule, anchor), calendar)
        if rule.frequency == Frequency.YEARLY:
            return (year - a_year) % rule.interval == 0
        return ((year - a_year) * 12 + month - a_month) % rule.interval == 0
    return True


def _in_interval(
    rule: RecurrenceRule, year: int, calendar: Calendar, anchor: int | None
) -> bool:
    if rule.interval == 1:
        return True
    a_year = from_jdn(_needs_anchor(rule, anchor), calendar).year
    return (year - a_year) % rule.interval == 0


def occurrences(
    rule: RecurrenceRule,
    first: int,
    last: int,
    calendar: Calendar,
    anchor: int | None = None,
    extra_keys_of: Callable[[int], Iterable[str]] | None = None,
) -> list[int]:
    """The days from `first` to `last` (inclusive) on which the rule falls. Goes through every day of the range, so
    ask for a stretch of years, not centuries. `extra_keys_of(day)`
    gives the keys of a day that cannot be worked out here (feasts)"""
    return [
        d
        for d in range(first, last + 1)
        if occurs_on(
            rule, d, calendar, anchor, extra_keys_of(d) if extra_keys_of else ()
        )
    ]


def pattern_keys(rule: RecurrenceRule) -> list[str]:
    """Keys that a day the rule falls on always has among its `day_keys` (and, for a feast, its `extra_keys`)"""
    if rule.easter_offset is not None:
        return [f"easter:{rule.easter_offset:+d}"]
    if rule.feast is not None:
        return [f"feast:{rule.feast}"]
    if rule.frequency == Frequency.WEEKLY:
        return [f"weekday:{w.value}" for w in rule.weekdays]
    if rule.frequency == Frequency.MONTHLY:
        if rule.month_day is not None:
            return [f"monthday:{rule.month_day}"]
        return [f"nth:{rule.nth}:{rule.weekdays[0].value}"]
    if rule.month_day is not None:
        keys = [f"yearday:{rule.month}-{rule.month_day}"]
        if rule.leap_shift:
            keys.append(f"yearday:{rule.month}-{rule.month_day + 1}")
        return keys
    return [f"yearnth:{rule.month}:{rule.nth}:{rule.weekdays[0].value}"]


def day_keys(day: int, calendar: Calendar, extra_keys: Iterable[str] = ()) -> list[str]:
    """Every key a rule could have and fall on this day. `extra_keys` are added as they are: the `feast:` keys
    of the day, which only the owner of the feasts can say"""
    year, month, day_of_month = from_jdn(day, calendar)
    dow = weekday(day).value
    from_start = (day_of_month - 1) // 7 + 1
    from_end = -((month_length(year, month, calendar) - day_of_month) // 7 + 1)
    return [
        f"weekday:{dow}",
        f"monthday:{day_of_month}",
        f"nth:{from_start}:{dow}",
        f"nth:{from_end}:{dow}",
        f"yearday:{month}-{day_of_month}",
        f"yearnth:{month}:{from_start}:{dow}",
        f"yearnth:{month}:{from_end}:{dow}",
        f"easter:{day - easter(year, calendar):+d}",
        *extra_keys,
    ]
