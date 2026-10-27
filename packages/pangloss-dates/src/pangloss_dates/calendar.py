"""Day arithmetic in the Julian and Gregorian calendars, on integer Julian Day Numbers.

A date is kept as a **day number**: the Julian Day Number (JDN) of the day, a whole number that counts days
and does not depend on either calendar's month lengths. It orders correctly, can be indexed, and is the same
whichever calendar a date was written in. Nothing here uses `datetime.date`, which is proleptic Gregorian and
stops at year 1.

Years are numbered astronomically: 1 BC is year 0, 2 BC is year -1. (The algorithms hold for years from -4799.)
A date is in **one** calendar, and says which: there is no cutover (the Julian 4 October 1582 and the Gregorian
15 October 1582 are consecutive days with consecutive numbers, but a date is never read as "whichever was in
use").

The weekday does not depend on the calendar: `weekday(jdn)` is 0 for Sunday.
"""

from enum import IntEnum, StrEnum
from typing import NamedTuple

MIN_YEAR = -4799
MAX_YEAR = 9999


class Calendar(StrEnum):
    JULIAN = "julian"
    GREGORIAN = "gregorian"


class Weekday(IntEnum):
    SUNDAY = 0
    MONDAY = 1
    TUESDAY = 2
    WEDNESDAY = 3
    THURSDAY = 4
    FRIDAY = 5
    SATURDAY = 6


class YMD(NamedTuple):
    year: int
    month: int
    day: int


class InvalidDate(ValueError):
    """The year, month or day does not exist in that calendar"""


def is_leap_year(year: int, calendar: Calendar) -> bool:
    if year % 4:
        return False
    if calendar == Calendar.JULIAN:
        return True
    return year % 100 != 0 or year % 400 == 0


_MONTH_LENGTHS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def month_length(year: int, month: int, calendar: Calendar) -> int:
    check_month(year, month)
    if month == 2 and is_leap_year(year, calendar):
        return 29
    return _MONTH_LENGTHS[month - 1]


def check_month(year: int, month: int) -> None:
    if not MIN_YEAR <= year <= MAX_YEAR:
        raise InvalidDate(f"year {year} is outside {MIN_YEAR} to {MAX_YEAR}")
    if not 1 <= month <= 12:
        raise InvalidDate(f"month {month} is not from 1 to 12")


def check_date(year: int, month: int, day: int, calendar: Calendar) -> None:
    length = month_length(year, month, calendar)
    if not 1 <= day <= length:
        raise InvalidDate(
            f"day {day} does not exist in {year}-{month:02d} of the {calendar} calendar"
            f" (which has {length} days)"
        )


def to_jdn(year: int, month: int, day: int, calendar: Calendar) -> int:
    """The Julian Day Number of a day (an error if the day does not exist in that calendar)"""
    check_date(year, month, day, calendar)
    a = (14 - month) // 12
    y = year + 4800 - a
    m = month + 12 * a - 3
    jdn = day + (153 * m + 2) // 5 + 365 * y + y // 4
    if calendar == Calendar.JULIAN:
        return jdn - 32083
    return jdn - y // 100 + y // 400 - 32045


def from_jdn(jdn: int, calendar: Calendar) -> YMD:
    """The year, month and day of a day number in a calendar"""
    f = jdn + 1401
    if calendar == Calendar.GREGORIAN:
        f += (4 * jdn + 274277) // 146097 * 3 // 4 - 38
    e = 4 * f + 3
    g = e % 1461 // 4
    h = 5 * g + 2
    day = h % 153 // 5 + 1
    month = (h // 153 + 2) % 12 + 1
    year = e // 1461 - 4716 + (14 - month) // 12
    return YMD(year, month, day)


def convert(
    year: int, month: int, day: int, from_calendar: Calendar, to_calendar: Calendar
) -> YMD:
    return from_jdn(to_jdn(year, month, day, from_calendar), to_calendar)


def weekday(jdn: int) -> Weekday:
    return Weekday((jdn + 1) % 7)


def nth_weekday(
    year: int, month: int, day_of_week: Weekday, n: int, calendar: Calendar
) -> int | None:
    """The day number of the `n`th `day_of_week` of a month (1 is the first; -1 is the last, -2 the one before),
    or None if the month has no such day (there is no fifth Sunday in most months)"""
    if n == 0:
        raise ValueError("n counts from 1 (the first) or from -1 (the last)")
    first = to_jdn(year, month, 1, calendar)
    length = month_length(year, month, calendar)
    last = first + length - 1
    if n > 0:
        found = first + (day_of_week - weekday(first)) % 7 + 7 * (n - 1)
        return found if found <= last else None
    found = last - (weekday(last) - day_of_week) % 7 + 7 * (n + 1)
    return found if found >= first else None


def first_and_last_day(
    year: int, month: int | None, day: int | None, calendar: Calendar
) -> tuple[int, int]:
    """The first and last day number covered by a year, a month, or a day (the more precise parts being None)"""
    if month is None:
        if day is not None:
            raise InvalidDate("a day needs a month")
        return to_jdn(year, 1, 1, calendar), to_jdn(year, 12, 31, calendar)
    if day is None:
        return (
            to_jdn(year, month, 1, calendar),
            to_jdn(year, month, month_length(year, month, calendar), calendar),
        )
    jdn = to_jdn(year, month, day, calendar)
    return jdn, jdn
