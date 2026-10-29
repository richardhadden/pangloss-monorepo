"""The settings of the calendar, read from the project's settings if it has them (as `pangloss_dates.config`)"""

from typing import Any

from pangloss_dates.calendar import Calendar, to_jdn
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


DEFAULT_EXTEND_MARGIN_YEARS = 10


def extend_margin_years(settings: Any = None) -> int:
    """`CALENDAR_EXTEND_MARGIN_YEARS`: how far beyond the span (`CALENDAR_FIRST_YEAR` to `CALENDAR_LAST_YEAR`) the
    calendar makes days when something is attached or linked there (default 10; 0 for none)"""
    return setting(
        "CALENDAR_EXTEND_MARGIN_YEARS", DEFAULT_EXTEND_MARGIN_YEARS, settings
    )


class NoSpan(ValueError):
    """`CALENDAR_FIRST_YEAR` and `CALENDAR_LAST_YEAR` are not set"""


def span_days(settings: Any = None) -> tuple[int, int]:
    """The first and last day number of the span the project has set (in `CALENDAR_DEFAULT`)"""
    first, last = first_year(settings), last_year(settings)
    if first is None or last is None:
        raise NoSpan(
            "Set CALENDAR_FIRST_YEAR and CALENDAR_LAST_YEAR (there is no default span)"
        )
    calendar = calendar_default(settings)
    return to_jdn(first, 1, 1, calendar), to_jdn(last, 12, 31, calendar)


def reach_days(settings: Any = None) -> tuple[int, int]:
    """The span with the margin on each side: days inside it are made when needed, days outside it never are"""
    first, last = span_days(settings)
    margin = extend_margin_years(settings)
    return first - round(margin * 365.2425), last + round(margin * 365.2425)
