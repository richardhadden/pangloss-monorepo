"""The four bounds of a date, and the day it sorts by.

Each date is described by **evidence** (what the source said) and **bounds** worked out from it and stored as
day numbers (see `pangloss_dates.calendar`), so dates can be compared, indexed and ordered:

- *strict*: the range as stated. `1500-03` is strict from 1 to 31 March; "between 1 May and 3 May" is strict
  from the 1st to the 3rd.
- *fuzzy*: the strict range allowing for doubt. `1500-03~` ("about March 1500") is fuzzy from 1 February to 30 April.
  "Fuzzy" here means "allowing for doubt", not vague.

`earliest_fuzzy <= earliest_strict <= latest_strict <= latest_fuzzy` always. For a date that is exactly what it says
the strict and fuzzy bounds are equal.
"""

from dataclasses import dataclass
from enum import StrEnum

from pangloss_dates.calendar import Calendar, InvalidDate, first_and_last_day


class InvalidBounds(ValueError):
    """The bounds are not in order"""


class SortBy(StrEnum):
    """Which day a date is ordered by"""

    MIDPOINT = "midpoint"
    EARLIEST_STRICT = "earliest_strict"
    LATEST_STRICT = "latest_strict"
    EARLIEST_FUZZY = "earliest_fuzzy"
    LATEST_FUZZY = "latest_fuzzy"
    MIDPOINT_FUZZY = "midpoint_fuzzy"


class Precision(StrEnum):
    YEAR = "year"
    MONTH = "month"
    DAY = "day"
    RANGE = "range"
    ONGOING = "ongoing"


@dataclass(frozen=True)
class Bounds:
    earliest_fuzzy: int
    earliest_strict: int
    latest_strict: int
    latest_fuzzy: int

    def __post_init__(self):
        if not (
            self.earliest_fuzzy
            <= self.earliest_strict
            <= self.latest_strict
            <= self.latest_fuzzy
        ):
            raise InvalidBounds(
                "bounds must satisfy earliest_fuzzy <= earliest_strict <= latest_strict <= latest_fuzzy, got "
                f"{self.earliest_fuzzy}, {self.earliest_strict}, {self.latest_strict}, {self.latest_fuzzy}"
            )

    def sort_day(self, sort_by: SortBy = SortBy.MIDPOINT) -> int:
        match sort_by:
            case SortBy.MIDPOINT:
                return (self.earliest_strict + self.latest_strict) // 2
            case SortBy.MIDPOINT_FUZZY:
                return (self.earliest_fuzzy + self.latest_fuzzy) // 2
            case SortBy.EARLIEST_STRICT:
                return self.earliest_strict
            case SortBy.LATEST_STRICT:
                return self.latest_strict
            case SortBy.EARLIEST_FUZZY:
                return self.earliest_fuzzy
            case SortBy.LATEST_FUZZY:
                return self.latest_fuzzy

    def contains(self, day: int, *, fuzzy: bool = True) -> bool:
        """Whether the day could be inside (fuzzy bounds) or is inside the stated range (strict bounds)"""
        if fuzzy:
            return self.earliest_fuzzy <= day <= self.latest_fuzzy
        return self.earliest_strict <= day <= self.latest_strict


@dataclass(frozen=True)
class Padding:
    """How much doubt adds to each side of a strict range, in units of the range's own precision: an approximate
    year is a year either side, an approximate month a month, an approximate day a week. A convention, not a measure"""

    year: int = 1
    month: int = 1
    day: int = 7


def precision_of(month: int | None, day: int | None) -> Precision:
    if month is None:
        return Precision.YEAR
    if day is None:
        return Precision.MONTH
    return Precision.DAY


def exact_bounds(
    year: int, month: int | None, day: int | None, calendar: Calendar
) -> Bounds:
    """A year, a month or a day, taken as stated: strict and fuzzy are the same"""
    first, last = first_and_last_day(year, month, day, calendar)
    return Bounds(first, first, last, last)


def padded_bounds(
    year: int,
    month: int | None,
    day: int | None,
    calendar: Calendar,
    padding: Padding | None = None,
) -> Bounds:
    """An approximate or uncertain year, month or day: strict is the unit, fuzzy adds the padding either side"""
    padding = padding or Padding()
    strict_first, strict_last = first_and_last_day(year, month, day, calendar)
    if month is None:
        before = first_and_last_day(year - padding.year, None, None, calendar)[0]
        after = first_and_last_day(year + padding.year, None, None, calendar)[1]
    elif day is None:
        before_year, before_month = shift_month(year, month, -padding.month)
        after_year, after_month = shift_month(year, month, padding.month)
        before = first_and_last_day(before_year, before_month, None, calendar)[0]
        after = first_and_last_day(after_year, after_month, None, calendar)[1]
    else:
        before = strict_first - padding.day
        after = strict_last + padding.day
    return Bounds(before, strict_first, strict_last, after)


def shift_month(year: int, month: int, months: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + months
    return index // 12, index % 12 + 1


def spanning_bounds(earliest: Bounds, latest: Bounds) -> Bounds:
    """From one date to another: a range of two dates, or a period from a start to an end. The strict range runs from
    the earliest strict day of the first to the latest strict day of the second; the fuzzy range likewise"""
    if earliest.earliest_strict > latest.latest_strict:
        raise InvalidDate(
            "the earliest date is after the latest (the range would be empty)"
        )
    # (the fuzzy start can only be later than the fuzzy end if the strict one is)
    return Bounds(
        earliest.earliest_fuzzy,
        earliest.earliest_strict,
        latest.latest_strict,
        latest.latest_fuzzy,
    )


def ongoing_bounds(horizon: int) -> Bounds:
    """The end of a period that has not ended: no later than the horizon (a setting), whose day number
    stands for the strict and fuzzy bounds alike"""
    return Bounds(horizon, horizon, horizon, horizon)
