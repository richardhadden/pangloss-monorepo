"""The date types fixed to the gregorian calendar: `GregorianDate` takes any of them (`when: GregorianDate`).

They add no fields. Each is its plain type with the calendar fixed (a gregorian one cannot be given another calendar),
and, inside a range, a period or a recurrence, ends in the same calendar. A search for `ExactDate` finds the
GregorianExactDate too, and the day numbers are those of every calendar, so ordering and ranges work across them.
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


class GregorianDate(Date):
    _meta = Date.Meta(abstract=True)
    default_calendar: ClassVar[Calendar | None] = Calendar.GREGORIAN


class GregorianExactDate(GregorianDate, ExactDate):
    pass


class GregorianEDTFDate(GregorianDate, EDTFDate):
    pass


class GregorianDateRange(GregorianDate, DateRange):
    earliest: GregorianExactDate
    latest: GregorianExactDate


class GregorianOngoingDate(GregorianDate, OngoingDate):
    pass


class GregorianUnknownDate(GregorianDate, UnknownDate):
    pass


class GregorianPeriod(GregorianDate, Period):
    start: (
        GregorianExactDate
        | GregorianDateRange
        | GregorianEDTFDate
        | GregorianUnknownDate
    )
    end: (
        GregorianExactDate
        | GregorianDateRange
        | GregorianEDTFDate
        | GregorianOngoingDate
    )


class GregorianRecurrence(GregorianDate, Recurrence):
    start: (
        GregorianExactDate
        | GregorianDateRange
        | GregorianEDTFDate
        | GregorianUnknownDate
    )
    end: (
        GregorianExactDate
        | GregorianDateRange
        | GregorianEDTFDate
        | GregorianOngoingDate
    )
