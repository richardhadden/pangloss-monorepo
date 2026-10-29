"""The date types, as Embedded models.

A field is typed with the base of a family and takes any member of it (`when: Date`); each member is told apart by
`type`. The bounds, the sort day and the pattern keys are worked out by a validator that always overwrites them, so
they are `int | None = None` on the models a client writes (it can leave them out), and always set when stored.

    Date                      the base (never used on its own)
    ├── ExactDate             year, and optionally month and day
    ├── EDTFDate              an EDTF string (needs the `edtf` extra)
    ├── DateRange             earliest and latest, each an ExactDate
    ├── OngoingDate           the end of a period that has not ended
    ├── UnknownDate           a start or an end that nobody knows (not both ends of a period)
    ├── Period                start and end, each an ExactDate, DateRange or EDTFDate (or unknown; the end may be ongoing)
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
    unknown_bounds,
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


class UnknownDate(Date):
    """The start or the end of a period that nobody knows. It is open from `DATES_EARLIEST_YEAR` to
    `DATES_OPEN_END_YEAR`, so the period is still found by a date it could include. Say what is known if
    anything can be: a range with a reasonable guess (`DateRange`, or EDTF `1500~`) says more, and an
    unknown date only that nothing is. Both ends of a period cannot be unknown."""

    @classmethod
    def work_out(cls, date) -> tuple[Bounds, Precision]:
        return (
            unknown_bounds(
                config.earliest_day(date.calendar),
                config.open_end_horizon(date.calendar),
            ),
            Precision.UNKNOWN,
        )


def _is_unknown(date) -> bool:
    return date.precision == Precision.UNKNOWN


def _span_of_lifetime(date) -> Bounds:
    """The bounds of something from `start` to `end`, one of which may be unknown (not both)"""
    _check_ends_in_calendar(date, date.start, date.end)
    if _is_unknown(date.start) and _is_unknown(date.end):
        raise ValueError(
            "the start and the end cannot both be unknown: say what is known of one of them"
        )
    return spanning_bounds(bounds_of(date.start), bounds_of(date.end))


def _sort_a_lifetime(date) -> None:
    """A period or a recurrence is ordered by its start (by its end if the start is not known), and has the day
    its end sorts by (its start if the end is not known)"""
    sort_by = date.sort_by or SortBy.MIDPOINT
    start, end = bounds_of(date.start), bounds_of(date.end)
    if _is_unknown(date.start):
        date.sort_day = end.sort_day(sort_by)
    else:
        date.sort_day = start.sort_day(sort_by)
    date.end_sort_day = start.sort_day() if _is_unknown(date.end) else end.sort_day()


class Period(Date):
    """From `start` to `end`: an occupation, a role, a residence. Sorts by when it started"""

    start: ExactDate | DateRange | EDTFDate | UnknownDate
    end: ExactDate | DateRange | EDTFDate | OngoingDate | UnknownDate

    @classmethod
    def work_out(cls, date) -> tuple[Bounds, Precision]:
        return _span_of_lifetime(date), Precision.RANGE

    @classmethod
    def fill_in(cls, date) -> None:
        super().fill_in(date)
        _sort_a_lifetime(date)


def _check_feast(feast: str) -> None:
    """A rule on a feast is answered by `pangloss_calendar` (the feast is the id of a characterisation): without it, it
    could never be, so it is refused"""
    from importlib.util import find_spec
    from uuid import UUID

    if find_spec("pangloss_calendar") is None:
        raise ValueError(
            "a rule on a feast needs pangloss-calendar (which works out the days of a feast); it is not installed"
        )
    try:
        UUID(feast)
    except ValueError as error:
        raise ValueError(
            f"feast is the id of a characterisation of pangloss-calendar, not {feast!r}"
        ) from error


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
    leap_shift: bool | None = None
    """(False if not said) A yearly rule on 24 to 28 February: a day later in a leap year (the old Roman leap day repeated the 24th)"""
    easter_offset: int | None = None
    """Instead of a month: days from Easter in the year (-47 is Shrove Tuesday); a yearly rule"""
    feast: str | None = None
    """Instead of a month: the key of a feast (the calendar works out its days); a yearly rule"""

    start: ExactDate | DateRange | EDTFDate | UnknownDate
    end: ExactDate | DateRange | EDTFDate | OngoingDate | UnknownDate

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
            easter_offset=date.easter_offset,
            leap_shift=bool(date.leap_shift),
            feast=date.feast,
        )

    @classmethod
    def work_out(cls, date) -> tuple[Bounds, Precision]:
        date.interval = date.interval or 1
        if date.feast is not None:
            _check_feast(date.feast)
        rule = cls.rule_of(date)  # (refuses a rule that says no day)
        if (
            "pattern_keys" in type(date).model_fields
        ):  # (not on the models a client writes)
            date.pattern_keys = pattern_keys(rule)
        return _span_of_lifetime(date), Precision.RANGE

    @classmethod
    def fill_in(cls, date) -> None:
        super().fill_in(date)
        _sort_a_lifetime(date)


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
