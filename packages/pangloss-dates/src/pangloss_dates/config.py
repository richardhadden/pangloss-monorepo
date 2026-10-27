"""The settings of dates, read from the project's settings if it has them (as `pangloss_history` does)"""

from typing import Any

from pangloss_core import settings as core_settings

from pangloss_dates.bounds import Padding
from pangloss_dates.calendar import Calendar, to_jdn


def setting(name: str, default: Any, settings: Any = None) -> Any:
    settings = settings or core_settings.__dict__.get("SETTINGS")
    return getattr(settings, name, default)


def default_calendar(settings: Any = None) -> Calendar:
    """`DATES_DEFAULT_CALENDAR`: the calendar of a date that does not say (Gregorian unless the project sets it)"""
    return Calendar(setting("DATES_DEFAULT_CALENDAR", Calendar.GREGORIAN, settings))


def padding(settings: Any = None) -> Padding:
    """`DATES_PADDING_YEARS`, `DATES_PADDING_MONTHS`, `DATES_PADDING_DAYS`: what doubt adds either side"""
    return Padding(
        year=setting("DATES_PADDING_YEARS", 1, settings),
        month=setting("DATES_PADDING_MONTHS", 1, settings),
        day=setting("DATES_PADDING_DAYS", 7, settings),
    )


def open_end_horizon(calendar: Calendar, settings: Any = None) -> int:
    """`DATES_OPEN_END_YEAR`: a period or an order with no end is taken to stop by the end of this year"""
    return to_jdn(setting("DATES_OPEN_END_YEAR", 1600, settings), 12, 31, calendar)


def earliest_day(calendar: Calendar, settings: Any = None) -> int:
    """`DATES_EARLIEST_YEAR`: a start that is not known is taken to be no earlier than the start of this year"""
    return to_jdn(setting("DATES_EARLIEST_YEAR", 1, settings), 1, 1, calendar)
