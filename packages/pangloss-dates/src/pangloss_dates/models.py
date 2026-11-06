"""The date types, as Embedded models.

A field is typed with the base of a family and takes any member of it (`when: Date`); each member is told apart by
`type`. The precision, the bounds, the sort days and the pattern keys are worked out by a validator, and are database
fields (`DBField`): the models a client writes and reads do not have them, and those written to the database always have
them set. (They are `X | None = None` so that a `CreateDB` can be made without them, before the validator fills them in.)

    Date                      the base (never used on its own)
    ├── ExactDate             year, and optionally month and day
    ├── EDTFDate              an EDTF string (needs the `edtf` extra)
    ├── DateRange             not_before and not_after, each an ExactDate (or unknown: not both)
    ├── OngoingDate           the end of a period that has not ended
    ├── UnknownDate           a start or an end that nobody knows (not both ends of a period)
    ├── Period                start and end, each an ExactDate, DateRange or EDTFDate (or unknown; the end may be ongoing)
    └── Recurrence            a rule (every Sunday, the third Sunday of March...) over a start and an end

`pangloss_dates.julian` and `pangloss_dates.gregorian` have the same families fixed to a calendar (`JulianDate`,
`JulianExactDate`, ...); here the calendar is that of the date, or `DATES_DEFAULT_CALENDAR`.
"""

from typing import Annotated, ClassVar

from pangloss_models import DBField, Embedded
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


def worked_out(date) -> tuple[Bounds, Precision]:
    """The bounds and the precision of a date, worked out from what it says (on any model of it: they are not stored on
    the models a client has)"""
    return type(date)._owner.work_out(date)


def _stored(date) -> bool:
    """Whether the date is a model written to the database, which keeps what is worked out (`DBField`s)"""
    return "sort_day" in type(date).model_fields


def interface_meta() -> dict:
    """The card and the editor of the interface module of this package (`pangloss_dates/interface/`), if the interface is
    installed: a date is said as a person would, not listed field by field, and a form asks only what a person says of it
    (not the bounds and sort days, which are worked out). They are used when `pangloss_dates` is in `INSTALLED_APPS`"""
    try:
        from pangloss_interface import InterfaceMeta
    except ImportError:
        return {}
    return {
        "_interface_meta": InterfaceMeta(
            view_card="pangloss_dates:DateCard", edit_card="pangloss_dates:DateEditor"
        )
    }


class Date(Embedded):
    locals().update(interface_meta())
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

    # worked out, and only in the database
    precision: Annotated[Precision | None, DBField] = None
    earliest_fuzzy: Annotated[int | None, DBField] = None
    earliest_strict: Annotated[int | None, DBField] = None
    latest_strict: Annotated[int | None, DBField] = None
    latest_fuzzy: Annotated[int | None, DBField] = None
    sort_day: Annotated[int | None, DBField] = None
    end_sort_day: Annotated[int | None, DBField] = None
    """For a period or a recurrence the day its end sorts by; for any other date, the same as `sort_day`"""

    @model_validator(mode="after")
    def work_out_the_bounds(self):
        # (self is a model made for writing; `_owner` is the class declared)
        type(self)._owner.fill_in(self)  # ty: ignore[unresolved-attribute]
        return self

    @classmethod
    def fill_in(cls, date) -> None:
        """Works out the date, which refuses one that cannot be on every model a client writes, and keeps what is
        worked out on those written to the database"""
        fixed = cls.default_calendar
        if fixed is not None and date.calendar not in (None, fixed):
            raise ValueError(f"{cls.__name__} is in the {fixed} calendar")
        date.calendar = date.calendar or fixed or config.default_calendar()
        bounds, precision = cls.work_out(date)
        sort_day, end_sort_day = cls.sort_days(date, bounds)
        if not _stored(date):
            return
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
        date.sort_day, date.end_sort_day = sort_day, end_sort_day

    @classmethod
    def sort_days(cls, date, bounds: Bounds) -> tuple[int, int]:
        """The day the date sorts by, and the day its end sorts by"""
        sort_day = bounds.sort_day(date.sort_by or SortBy.MIDPOINT)
        return sort_day, sort_day

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


def _spanning(
    first: Bounds, first_precision: Precision, last: Bounds, last_precision: Precision
) -> Bounds:
    """From one date to another (`spanning_bounds`). When they are the wrong way round only because an end that is
    open (not known, or not yet come) is taken to be by a year of the settings, the error says which setting: "the
    range would be empty" of a period from 1605 that is still going on said nothing of `DATES_OPEN_END_YEAR`"""
    if first.earliest_strict > last.latest_strict:
        if last_precision in (Precision.ONGOING, Precision.UNKNOWN):
            raise ValueError(
                f"it starts after {config.open_end_year()}, and an end that is not known or has not come is taken to "
                f"be by the end of that year (the setting DATES_OPEN_END_YEAR): set DATES_OPEN_END_YEAR to a later year"
            )
        if first_precision == Precision.UNKNOWN:
            raise ValueError(
                f"it ends before {config.earliest_year()}, and a start that is not known is taken to be no earlier "
                f"than that year (the setting DATES_EARLIEST_YEAR): set DATES_EARLIEST_YEAR to an earlier year"
            )
    return spanning_bounds(first, last)


def _check_ends_in_calendar(date, *ends) -> None:
    for end in ends:
        if end.calendar != date.calendar:
            raise ValueError(
                f"the {end.calendar} date {end} is in a {date.calendar} {type(date).__name__}"
            )


class DateRange(Date):
    """One date whose day is not known: somewhere from `not_before` to `not_after` (the names of the Text Encoding
    Initiative). Either may be unknown (`UnknownDate`: "not before March 1500", and nothing said of when it was by),
    not both; such a range runs to the horizon (or from the floor) and sorts by its known end"""

    not_before: ExactDate | UnknownDate
    not_after: ExactDate | UnknownDate

    @classmethod
    def work_out(cls, date) -> tuple[Bounds, Precision]:
        _check_ends_in_calendar(date, date.not_before, date.not_after)
        (first, first_precision), (last, last_precision) = (
            worked_out(date.not_before),
            worked_out(date.not_after),
        )
        if first_precision == last_precision == Precision.UNKNOWN:
            raise ValueError(
                "the ends of a range cannot both be unknown: say what is known of one of them (or use UnknownDate)"
            )
        return _spanning(first, first_precision, last, last_precision), Precision.RANGE

    @classmethod
    def sort_days(cls, date, bounds: Bounds) -> tuple[int, int]:
        """A range with one end unknown sorts by the other, unless it says how (the middle of 1500 to the horizon
        would mean nothing)"""
        if date.sort_by is None:
            (first, first_precision), (last, last_precision) = (
                worked_out(date.not_before),
                worked_out(date.not_after),
            )
            if Precision.UNKNOWN in (first_precision, last_precision):
                known = last if first_precision == Precision.UNKNOWN else first
                return known.sort_day(), known.sort_day()
        return super().sort_days(date, bounds)


def _span_of_lifetime(date) -> Bounds:
    """The bounds of something from `start` to `end`, one of which may be unknown (not both)"""
    _check_ends_in_calendar(date, date.start, date.end)
    (start, start_precision), (end, end_precision) = (
        worked_out(date.start),
        worked_out(date.end),
    )
    if start_precision == end_precision == Precision.UNKNOWN:
        raise ValueError(
            "the start and the end cannot both be unknown: say what is known of one of them"
        )
    return _spanning(start, start_precision, end, end_precision)


def _sort_a_lifetime(cls, date, bounds: Bounds) -> tuple[int, int]:
    """A period or a recurrence is ordered by its start (by its end if the start is not known), and has the day
    its end sorts by (its start if the end is not known)"""
    sort_by = date.sort_by or SortBy.MIDPOINT
    (start, start_precision), (end, end_precision) = (
        worked_out(date.start),
        worked_out(date.end),
    )
    start_unknown = start_precision == Precision.UNKNOWN
    sort_day = end.sort_day(sort_by) if start_unknown else start.sort_day(sort_by)
    end_unknown = end_precision == Precision.UNKNOWN
    return sort_day, start.sort_day() if end_unknown else end.sort_day()


class Period(Date):
    """From `start` to `end`: an occupation, a role, a residence. Sorts by when it started"""

    start: ExactDate | DateRange | EDTFDate | UnknownDate
    end: ExactDate | DateRange | EDTFDate | OngoingDate | UnknownDate

    sort_days = classmethod(_sort_a_lifetime)

    @classmethod
    def work_out(cls, date) -> tuple[Bounds, Precision]:
        return _span_of_lifetime(date), Precision.RANGE


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

    sort_days = classmethod(_sort_a_lifetime)

    @classmethod
    def work_out(cls, date) -> tuple[Bounds, Precision]:
        if date.feast is not None:
            _check_feast(date.feast)
        cls.rule_of(date)  # (refuses a rule that says no day)
        return _span_of_lifetime(date), Precision.RANGE

    @classmethod
    def fill_in(cls, date) -> None:
        date.interval = date.interval or 1
        super().fill_in(date)
        if _stored(date):
            date.pattern_keys = pattern_keys(cls.rule_of(date))


class SortDefault:
    """The day a field's dates sort by when the date does not say (`sort_by`), instead of the midpoint:

        born: Annotated[ExactDate, SortDefault(SortBy.EARLIEST_FUZZY)]

    "for a birth date, a person sorts by the earliest it could be". The date's own `sort_by` wins."""

    def __init__(self, sort_by: SortBy):
        self.sort_by = sort_by

    def apply_to_embedded(self, date) -> None:
        if getattr(date, "sort_by", None) is None and _stored(date):
            date.sort_by = self.sort_by
            type(date)._owner.fill_in(date)
            date.sort_by = None  # (what was said is kept as it was)

    def export(self) -> dict:
        """For the interface: the sort it shows as chosen when a date of the field does not say"""
        return {"sortBy": self.sort_by.value}

    def __repr__(self) -> str:
        return f"SortDefault({self.sort_by.value!r})"
