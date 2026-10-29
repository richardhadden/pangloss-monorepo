"""Naming days, and laying out a month.

A day is a Julian Day Number with no calendar of its own (see `pangloss_dates.calendar`); a reader names it in the
Julian or the Gregorian calendar. A day is written for a URL or a person as `J1500-03-02` (Julian), `G1500-03-12`
(Gregorian), or a bare number (the JDN): the same day in three ways.
"""

import re
from dataclasses import dataclass

from pangloss_dates.calendar import (
    Calendar,
    InvalidDate,
    Weekday,
    describe,
    from_jdn,
    month_length,
    to_jdn,
    weekday,
)

_REF = re.compile(r"^([JG])(-?\d{1,4})-(\d{1,2})-(\d{1,2})$")
_PREFIX = {"J": Calendar.JULIAN, "G": Calendar.GREGORIAN}


class InvalidDayRef(ValueError):
    """The text is not a day"""


def parse_day(ref: str) -> int:
    """`J1500-03-02`, `G1500-03-12` or `2268933` as a day number"""
    ref = ref.strip()
    if ref.isdigit():
        return int(ref)
    found = _REF.match(ref)
    if found is None:
        raise InvalidDayRef(
            f"{ref!r} is not a day: write J1500-03-02, G1500-03-12 or a day number"
        )
    letter, year, month, day = found.groups()
    try:
        return to_jdn(int(year), int(month), int(day), _PREFIX[letter])
    except InvalidDate as error:
        raise InvalidDayRef(str(error)) from error


def format_day(jdn: int, calendar: Calendar) -> str:
    year, month, day = from_jdn(jdn, calendar)
    letter = "J" if calendar == Calendar.JULIAN else "G"
    return f"{letter}{year}-{month:02d}-{day:02d}"


@dataclass(frozen=True)
class DayView:
    jdn: int
    julian: tuple[int, int, int]
    gregorian: tuple[int, int, int]
    weekday: Weekday

    def in_calendar(self, calendar: Calendar) -> tuple[int, int, int]:
        return self.julian if calendar == Calendar.JULIAN else self.gregorian


def view_of(jdn: int) -> DayView:
    names = describe(jdn)
    return DayView(jdn, tuple(names.julian), tuple(names.gregorian), names.weekday)


def month_span(calendar: Calendar, year: int, month: int) -> tuple[int, int]:
    """The first and last day number of a month"""
    first = to_jdn(year, month, 1, calendar)
    return first, first + month_length(year, month, calendar) - 1


def next_month(calendar: Calendar, year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def previous_month(calendar: Calendar, year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def month_grid(
    calendar: Calendar,
    year: int,
    month: int,
    week_starts: Weekday = Weekday.MONDAY,
) -> list[list[int | None]]:
    """The weeks of a month as rows of seven: the day number of each day, or None before the 1st and after the
    last. The first row starts on `week_starts`. Julian and Gregorian months of the same name differ in which
    weekday they begin on, so the grid is made for the calendar asked"""
    first, last = month_span(calendar, year, month)
    lead = (weekday(first) - week_starts) % 7
    cells: list[int | None] = [None] * lead + list(range(first, last + 1))
    cells += [None] * (-len(cells) % 7)
    return [cells[i : i + 7] for i in range(0, len(cells), 7)]
