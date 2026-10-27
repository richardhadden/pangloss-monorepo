"""The date types, as Embedded models.

A field is typed with the base of a family and takes any member of it (`when: Date`); each member is told apart by
`type`. The bounds, the sort day and the pattern keys are worked out by a validator that always overwrites them, so
they are `int | None = None` on the models a client writes (it can leave them out), and always set when stored.

    Date                      the base (never used on its own)
    ├── ExactDate             year, and optionally month and day
    ├── EDTFDate              an EDTF string (needs the `edtf` extra)
    ├── DateRange             earliest and latest, each an ExactDate
    ├── OngoingDate           the end of a period that has not ended
    ├── Period                start and end, each an ExactDate, DateRange or EDTFDate (the end may be ongoing)
    └── Recurrence            a rule (every Sunday, the third Sunday of March...) over a start and an end

`pangloss_dates.julian` and `pangloss_dates.gregorian` have the same families fixed to a calendar (`JulianDate`,
`JulianExactDate`, ...); here the calendar is that of the date, or `DATES_DEFAULT_CALENDAR`.
"""

from typing import Annotated, ClassVar

from pangloss_models.model_bases.embedded import Embedded
from pangloss_models.model_bases.helpers import DBField
from pydantic import model_validator

from pangloss_dates import config
from pangloss_dates.bounds import (
    Bounds,
    Precision,
    SortBy,
    exact_bounds,
    ongoing_bounds,
    precision_of,
    spanning_bounds,
)
from pangloss_dates.calendar import Calendar, Weekday
from pangloss_dates.recurrence import Frequency, RecurrenceRule, pattern_keys


def bounds_of(date) -> Bounds:
    """The bounds stored on a date that has been filled in"""
    return Bounds(
        date.earliest_fuzzy, date.earliest_strict, date.latest_strict, date.latest_fuzzy
    )


class Date(Embedded):
    _meta = Embedded.Meta(
        abstract=True,
        indexes=["sort_day", "end_sort_day", "earliest_fuzzy", "latest_fuzzy"],
    )

    default_calendar: ClassVar[Calendar | None] = None
    """The calendar a family is fixed to (None: the date says, or the project's setting)"""

    calendar: Calendar | None = None
    source_text: str | None = None
    """What the source said ("last week, probably Tuesday"), kept as written"""
    sort_by: SortBy | None = None
    """Which day to order by (the midpoint of the strict range if not said)"""

    # worked out, whatever a client sends
    precision: Precision | None = None
    earliest_fuzzy: int | None = None
    earliest_strict: int | None = None
    latest_strict: int | None = None
    latest_fuzzy: int | None = None
    sort_day: int | None = None
    end_sort_day: int | None = None
    """For a period or a recurrence the day its end sorts by; for any other date, the same as `sort_day`"""

    @model_validator(mode="after")
    def work_out_the_bounds(self):
        # (self is the model made for writing; `_owner` is the class declared)
        type(self)._owner.fill_in(self)  # ty: ignore[unresolved-attribute]
        return self

    @classmethod
    def fill_in(cls, date) -> None:
        fixed = cls.default_calendar
        if fixed is not None and date.calendar not in (None, fixed):
            raise ValueError(f"{cls.__name__} is in the {fixed} calendar")
        date.calendar = date.calendar or fixed or config.default_calendar()
        bounds, precision = cls.work_out(date)
        date.precision = precision
        (
            date.earliest_fuzzy,
            date.earliest_strict,
            date.latest_strict,
            date.latest_fuzzy,
        ) = (
            bounds.earliest_fuzzy,
            bounds.earliest_strict,
            bounds.latest_strict,
            bounds.latest_fuzzy,
        )
        date.sort_day = bounds.sort_day(date.sort_by or SortBy.MIDPOINT)
        date.end_sort_day = date.sort_day

    @classmethod
    def work_out(cls, date) -> tuple[Bounds, Precision]:
        raise NotImplementedError(f"{cls.__name__} is not a date to use on its own")


class ExactDate(Date):
    year: int
    month: int | None = None
    day: int | None = None

    @classmethod
    def work_out(cls, date) -> tuple[Bounds, Precision]:
        return (
            exact_bounds(date.year, date.month, date.day, date.calendar),
            precision_of(date.month, date.day),
        )


class EDTFDate(Date):
    edtf: str
    """EDTF text: `1500-03-02`, `1500~`, `150X`, `[1500,1502]`. Needs the `edtf` extra"""

    @classmethod
    def work_out(cls, date) -> tuple[Bounds, Precision]:
        from pangloss_dates.edtf import parse_edtf_date

        result = parse_edtf_date(date.edtf, date.calendar, config.padding())
        return result.bounds, result.precision


def _check_ends_in_calendar(date, *ends) -> None:
    for end in ends:
        if end.calendar != date.calendar:
            raise ValueError(
                f"the {end.calendar} date {end} is in a {date.calendar} {type(date).__name__}"
            )


class DateRange(Date):
    """One date whose day is not known: somewhere from `earliest` to `latest`"""

    earliest: ExactDate
    latest: ExactDate

    @classmethod
    def work_out(cls, date) -> tuple[Bounds, Precision]:
        _check_ends_in_calendar(date, date.earliest, date.latest)
        return (
            spanning_bounds(bounds_of(date.earliest), bounds_of(date.latest)),
            Precision.RANGE,
        )


class OngoingDate(Date):
    """The end of a period that has not ended (it is taken to stop by the end of `DATES_OPEN_END_YEAR`)"""

    @classmethod
    def work_out(cls, date) -> tuple[Bounds, Precision]:
        return (
            ongoing_bounds(config.open_end_horizon(date.calendar)),
            Precision.ONGOING,
        )


class Period(Date):
    """From `start` to `end`: an occupation, a role, a residence. Sorts by when it started"""

    start: ExactDate | DateRange | EDTFDate
    end: ExactDate | DateRange | EDTFDate | OngoingDate

    @classmethod
    def work_out(cls, date) -> tuple[Bounds, Precision]:
        _check_ends_in_calendar(date, date.start, date.end)
        return (
            spanning_bounds(bounds_of(date.start), bounds_of(date.end)),
            Precision.RANGE,
        )

    @classmethod
    def fill_in(cls, date) -> None:
        super().fill_in(date)
        # a period is ordered by its start, not by the middle of its length
        date.sort_day = bounds_of(date.start).sort_day(date.sort_by or SortBy.MIDPOINT)
        date.end_sort_day = bounds_of(date.end).sort_day()


class Recurrence(Date):
    """Something that happens again and again, within a lifetime (`start` to `end`): "every Sunday", "the third
    Sunday of March", "on the 21st of each month". The days are never stored; `pattern_keys` find the rules that
    could fall on a day (see `pangloss_dates.recurrence`)"""

    frequency: Frequency
    weekdays: list[int]
    """0 is Sunday, 6 is Saturday"""
    nth: int | None = None
    """With one weekday, the first, second... (or -1, the last) of the month"""
    month: int | None = None
    month_day: int | None = None
    interval: int | None = None
    """Every 2nd, 3rd... week, month or year, counting from the start (1 if not said)"""
    excluded_days: list[int]
    """Day numbers the rule does not fall on"""

    start: ExactDate | DateRange | EDTFDate
    end: ExactDate | DateRange | EDTFDate | OngoingDate

    # worked out
    pattern_keys: Annotated[list[str], DBField]

    @classmethod
    def rule_of(cls, date) -> RecurrenceRule:
        return RecurrenceRule(
            frequency=date.frequency,
            weekdays=tuple(Weekday(w) for w in date.weekdays),
            nth=date.nth,
            month=date.month,
            month_day=date.month_day,
            interval=date.interval or 1,
            excluded_days=frozenset(date.excluded_days),
        )

    @classmethod
    def work_out(cls, date) -> tuple[Bounds, Precision]:
        _check_ends_in_calendar(date, date.start, date.end)
        date.interval = date.interval or 1
        rule = cls.rule_of(date)  # (refuses a rule that says no day)
        if (
            "pattern_keys" in type(date).model_fields
        ):  # (not on the models a client writes)
            date.pattern_keys = pattern_keys(rule)
        return (
            spanning_bounds(bounds_of(date.start), bounds_of(date.end)),
            Precision.RANGE,
        )

    @classmethod
    def fill_in(cls, date) -> None:
        super().fill_in(date)
        date.sort_day = bounds_of(date.start).sort_day(date.sort_by or SortBy.MIDPOINT)
        date.end_sort_day = bounds_of(date.end).sort_day()


class SortDefault:
    """The day a field's dates sort by when the date does not say (`sort_by`), instead of the midpoint:

        born: Annotated[ExactDate, SortDefault(SortBy.EARLIEST_FUZZY)]

    "for a birth date, a person sorts by the earliest it could be". The date's own `sort_by` wins."""

    def __init__(self, sort_by: SortBy):
        self.sort_by = sort_by

    def apply_to_embedded(self, date) -> None:
        if getattr(date, "sort_by", None) is None and hasattr(date, "sort_day"):
            date.sort_by = self.sort_by
            type(date)._owner.fill_in(date)
            date.sort_by = None  # (what was said is kept as it was)

    def __repr__(self) -> str:
        return f"SortDefault({self.sort_by.value!r})"
