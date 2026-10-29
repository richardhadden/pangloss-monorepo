"""The settings of the calendar, read from the project's settings if it has them (as `pangloss_dates.config`)"""

from typing import Any

from pangloss_dates.calendar import Calendar
from pangloss_dates.config import default_calendar, setting

from pangloss_calendar.views import DEFAULT_NARROW_DAYS


def calendar_default(settings: Any = None) -> Calendar:
    """`CALENDAR_DEFAULT`, else `DATES_DEFAULT_CALENDAR`"""
    chosen = setting("CALENDAR_DEFAULT", None, settings)
    return Calendar(chosen) if chosen else default_calendar(settings)


def first_year(settings: Any = None) -> int | None:
    """`CALENDAR_FIRST_YEAR`: no default; `seed` refuses to run without it"""
    return setting("CALENDAR_FIRST_YEAR", None, settings)


def last_year(settings: Any = None) -> int | None:
    """`CALENDAR_LAST_YEAR`: no default"""
    return setting("CALENDAR_LAST_YEAR", None, settings)


def auto_extend(settings: Any = None) -> bool:
    """`CALENDAR_AUTO_EXTEND`: make days outside the span when one is asked for (off unless set)"""
    return bool(setting("CALENDAR_AUTO_EXTEND", False, settings))


def narrow_days(settings: Any = None) -> int:
    """`CALENDAR_NARROW_DAYS`: see `pangloss_calendar.views`"""
    return setting("CALENDAR_NARROW_DAYS", DEFAULT_NARROW_DAYS, settings)


def use(settings: Any = None) -> str | None:
    """`CALENDAR_USE`: the liturgical use a view shows (all if not set)"""
    return setting("CALENDAR_USE", None, settings)
