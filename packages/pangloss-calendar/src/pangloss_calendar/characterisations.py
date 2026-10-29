"""A characterisation as the calendar sees it, and the days its rule falls on (pure: no database, no models).

A characterisation (`pangloss_calendar.models.DateCharacterisation`) has an optional yearly or weekly rule over a
lifetime, in a calendar. `Characterisation` is that, read from the database (`pangloss_calendar.graph`) or built by
hand in a test.
"""

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from pangloss_dates.calendar import (
    Calendar,
    InvalidDate,
    from_jdn,
    is_leap_year,
    nth_weekday,
    to_jdn,
)
from pangloss_dates.easter import easter
from pangloss_dates.models import Recurrence
from pangloss_dates.recurrence import (
    Frequency,
    RecurrenceRule,
    occurrences,
    occurs_on,
)


@dataclass(frozen=True)
class Characterisation:
    id: UUID
    label: str
    type: str
    use: str | None = None
    rank: str | None = None
    rule: RecurrenceRule | None = None
    calendar: Calendar = Calendar.GREGORIAN
    first: int | None = None
    """The first day of its lifetime (strict), or None without a rule"""
    last: int | None = None
    anchor: int | None = None

    @property
    def key(self) -> str:
        """What a rule's `feast` says to fall on this characterisation's days"""
        return str(self.id)

    @property
    def feast_key(self) -> str:
        return f"feast:{self.id}"

    @property
    def moves_with_easter(self) -> bool:
        return self.rule is not None and self.rule.easter_offset is not None

    @property
    def has_days(self) -> bool:
        """A rule that can be worked out here (one on another characterisation's feast cannot)"""
        return self.rule is not None and self.rule.feast is None


def from_row(row: dict[str, Any], default: Calendar) -> Characterisation:
    """From a row of `graph.characterisations`"""
    rule = None
    if row.get("frequency"):
        rule = Recurrence.rule_of(
            SimpleNamespace(
                frequency=Frequency(row["frequency"]),
                weekdays=row["weekdays"] or [],
                nth=row["nth"],
                month=row["month"],
                month_day=row["month_day"],
                interval=row["interval"] or 1,
                excluded_days=row["excluded_days"] or [],
                easter_offset=row["easter_offset"],
                feast=row["feast"],
                leap_shift=bool(row.get("leap_shift")),
            )
        )
    return Characterisation(
        id=UUID(str(row["id"])),
        label=row["label"],
        type=row["type"],
        use=row.get("use"),
        rank=row.get("rank"),
        rule=rule,
        calendar=Calendar(row["calendar"]) if row.get("calendar") else default,
        first=row.get("earliest_strict") if rule else None,
        last=row.get("latest_strict") if rule else None,
        anchor=row["anchor"]
        if row.get("anchor") is not None
        else row.get("earliest_strict"),
    )


def falls_on_day(c: Characterisation, day: int) -> bool:
    """Whether the rule falls on the day, in the rule's own calendar and within its lifetime"""
    if not c.has_days or c.rule is None:
        return False
    if (c.first is not None and day < c.first) or (c.last is not None and day > c.last):
        return False
    return occurs_on(c.rule, day, c.calendar, c.anchor)


def days_between(c: Characterisation, first: int, last: int) -> list[int]:
    """The days from `first` to `last` (inclusive) that the rule falls on, in order. A yearly rule is worked out for each year
    (not tried on every day)"""
    if not c.has_days or c.rule is None:
        return []
    lo = max(first, c.first) if c.first is not None else first
    hi = min(last, c.last) if c.last is not None else last
    if lo > hi:
        return []
    rule = c.rule
    if rule.frequency != Frequency.YEARLY:
        return occurrences(rule, lo, hi, c.calendar, c.anchor)
    found = []
    for year in range(from_jdn(lo, c.calendar).year, from_jdn(hi, c.calendar).year + 1):
        day = _yearly_day(rule, year, c.calendar)
        if (
            day is not None
            and lo <= day <= hi
            and occurs_on(rule, day, c.calendar, c.anchor)
        ):
            found.append(day)
    return found


def _yearly_day(rule: RecurrenceRule, year: int, calendar: Calendar) -> int | None:
    if rule.easter_offset is not None:
        return easter(year, calendar) + rule.easter_offset
    assert rule.month is not None
    if rule.month_day is not None:
        try:
            shift = 1 if rule.leap_shift and is_leap_year(year, calendar) else 0
            return to_jdn(year, rule.month, rule.month_day, calendar) + shift
        except InvalidDate:  # (29 February, or the 31st of a short month)
            return None
    return nth_weekday(year, rule.month, rule.weekdays[0], rule.nth or 1, calendar)


def unique(chars: list[Characterisation]) -> list[Characterisation]:
    """Once for each characterisation (kept for a row for each rule)"""
    return list({c.id: c for c in chars}.values())


def on_day(chars: list[Characterisation], day: int) -> list[Characterisation]:
    return unique([c for c in chars if falls_on_day(c, day)])


def feast_keys(chars: list[Characterisation], day: int) -> list[str]:
    """The `extra_keys` for `pangloss_dates`: the characterisations whose rule falls on the day"""
    return [c.feast_key for c in on_day(chars, day)]


def days_of(
    chars: list[Characterisation], first: int, last: int
) -> dict[int, list[Characterisation]]:
    """For each day from `first` to `last` that any rule falls on, the characterisations"""
    by_day: dict[int, list[Characterisation]] = {}
    for c in chars:
        for day in days_between(c, first, last):
            by_day.setdefault(day, []).append(c)
    return {day: unique(found) for day, found in by_day.items()}


def moveable(
    chars: list[Characterisation], year: int, calendar: Calendar
) -> list[tuple[Characterisation, int]]:
    """The characterisations that move with Easter, and their day in the year of the calendar, in order"""
    found = []
    for c in chars:
        if not c.moves_with_easter or c.rule is None:
            continue
        day = easter(year, c.calendar) + (c.rule.easter_offset or 0)
        if from_jdn(day, calendar).year == year and falls_on_day(c, day):
            found.append((c, day))
    return sorted(found, key=lambda pair: (pair[1], pair[0].label, str(pair[0].id)))
