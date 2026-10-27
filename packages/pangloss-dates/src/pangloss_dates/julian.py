"""The date types fixed to the julian calendar: `JulianDate` takes any of them (`when: JulianDate`).

They add no fields. Each is its plain type with the calendar fixed (a julian one cannot be given another calendar),
and, inside a range, a period or a recurrence, ends in the same calendar. A search for `ExactDate` finds the
JulianExactDate too, and the day numbers are those of every calendar, so ordering and ranges work across them.
"""

from typing import ClassVar

from pangloss_dates.calendar import Calendar
from pangloss_dates.models import (
    Date,
    DateRange,
    EDTFDate,
    ExactDate,
    OngoingDate,
    Period,
    Recurrence,
    UnknownDate,
)


class JulianDate(Date):
    _meta = Date.Meta(abstract=True)
    default_calendar: ClassVar[Calendar | None] = Calendar.JULIAN


class JulianExactDate(JulianDate, ExactDate):
    pass


class JulianEDTFDate(JulianDate, EDTFDate):
    pass


class JulianDateRange(JulianDate, DateRange):
    earliest: JulianExactDate
    latest: JulianExactDate


class JulianOngoingDate(JulianDate, OngoingDate):
    pass


class JulianUnknownDate(JulianDate, UnknownDate):
    pass


class JulianPeriod(JulianDate, Period):
    start: JulianExactDate | JulianDateRange | JulianEDTFDate | JulianUnknownDate
    end: (
        JulianExactDate
        | JulianDateRange
        | JulianEDTFDate
        | JulianOngoingDate
        | JulianUnknownDate
    )


class JulianRecurrence(JulianDate, Recurrence):
    start: JulianExactDate | JulianDateRange | JulianEDTFDate | JulianUnknownDate
    end: (
        JulianExactDate
        | JulianDateRange
        | JulianEDTFDate
        | JulianOngoingDate
        | JulianUnknownDate
    )
