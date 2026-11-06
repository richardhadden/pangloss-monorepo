"""A day, a month, a year, Easter, and the characterisations: the pieces put together.

The dates are found with `graph.dated_between` (from the dates, by their indexed bounds), so what is deleted, or
unpublished for a reader who may not see it, is left out as it is in the lists. The characterisations (feasts and the
like: `pangloss_calendar.models.DateCharacterisation`) are those of the rule they have, worked out here, and those attached
by hand (`graph.attach`); the days themselves are worked out, and need not be in the graph (with `CALENDAR_AUTO_EXTEND`
they are made as they are asked for, within the reach of the calendar).
"""

from typing import Any, Literal
from uuid import UUID

from pangloss_dates import Calendar, Weekday, from_jdn, occurrences, occurs_on
from pangloss_dates.easter import easter
from pangloss_dates.recurrence import day_keys
from pydantic import BaseModel

from pangloss_calendar import graph, settings
from pangloss_calendar import characterisations as rules
from pangloss_calendar.characterisations import Characterisation, is_single
from pangloss_calendar.days import (
    DayView,
    format_day,
    month_grid,
    month_span,
    next_month,
    previous_month,
    view_of,
    year_span,
)
from pangloss_calendar.fields import DateField, calendar_fields
from pangloss_calendar.views import Dated, place

MONTH_LIMIT = 20_000
"""Dates looked at to fill a month or a day (more are left out, and the report says `truncated`)"""

COVERING_PAGE = 50
"""How many of the long periods that cover a view are read at once, if the request does not say (`covering`)"""
MAX_COVERING_PAGE = 500

Mark = Literal["stated", "possible"]
Origin = Literal["rule", "manual"]
Via = Literal["rule", "day", "month", "year", "span"]


class OutsideCalendar(ValueError):
    """What is asked for is beyond the span and its margin: it is not made"""


class DayOut(BaseModel):
    jdn: int
    julian: str
    gregorian: str
    weekday: int
    weekday_name: str

    @classmethod
    def of(cls, jdn: int) -> DayOut:
        view: DayView = view_of(jdn)
        return cls(
            jdn=jdn,
            julian=format_day(jdn, Calendar.JULIAN),
            gregorian=format_day(jdn, Calendar.GREGORIAN),
            weekday=int(view.weekday),
            weekday_name=Weekday(view.weekday).name.lower(),
        )


class CharacterisationOut(BaseModel):
    id: UUID
    label: str
    type: str
    easter_offset: int | None = None
    kind: str | None = None
    """The kind of its `when` (`Recurrence`, `JulianExactDate`, `Period`, ...); None for one with no rule"""
    repeated: bool = False
    """Whether it falls again and again (a `Recurrence`), rather than once"""

    @classmethod
    def of(cls, c: Characterisation) -> CharacterisationOut:
        return cls(
            id=c.id,
            label=c.label,
            type=c.type,
            easter_offset=c.rule.easter_offset if c.rule else None,
            kind=c.kind,
            repeated=c.repeated,
        )


class Characterised(BaseModel):
    """A characterisation on a day (or over a range), and how it comes to be there"""

    characterisation: CharacterisationOut
    origin: Origin
    via: Via
    first: DayOut | None = None
    last: DayOut | None = None
    """For one attached to a month, a year or a span: the range it covers"""


class Ref(BaseModel):
    id: UUID
    label: str
    type: str
    field: str


class Hit(BaseModel):
    ref: Ref
    mark: Mark
    single: bool = True
    """One day (an exact date, a range, an EDTF date, a day of a repeated event), as against a period over its days"""
    first: DayOut | None = None
    last: DayOut | None = None
    """The range the date states (for a single date: the days it could be on)"""


class DayReport(BaseModel):
    day: DayOut
    calendar: Calendar
    previous: DayOut
    next: DayOut
    """The day before and the day after (for stepping through the days)"""
    characterisations: list[Characterised]
    hits: list[Hit]
    covering: int = 0
    """How many long periods cover the day, beginning before it and ending after: not among the `hits` (`/covering`
    has them, a page at a time)"""
    truncated: bool = False
    """More dates were found than are shown (`MONTH_LIMIT`)"""


class MonthDayOut(BaseModel):
    day: DayOut
    characterisations: list[Characterised]
    hits: list[Hit]


class Spanning(BaseModel):
    ref: Ref
    first: DayOut
    last: DayOut


class MonthReport(BaseModel):
    calendar: Calendar
    year: int
    month: int
    first: DayOut
    last: DayOut
    previous: tuple[int, int]
    next: tuple[int, int]
    weeks: list[list[int | None]]
    """Day numbers, seven to a row (None outside the month); the days are in `days`"""
    days: list[MonthDayOut]
    spanning: list[Spanning]
    """Periods wider than `CALENDAR_NARROW_DAYS`: drawn across their days"""
    between: list[Spanning]
    """Single dates known only within a range that lies in the month ("between these days")"""
    roughly: list[Spanning]
    """Single dates known only within a range that reaches beyond the month: listed, not drawn"""
    characterised_spans: list[Characterised]
    """Characterisations attached to the month, its year or a span, not to a day"""
    covering: int = 0
    """How many long periods cover the whole month, beginning before it and ending after: not among `spanning`
    (`/covering` has them, a page at a time)"""
    truncated: bool
    """More dates were found than are shown (`MONTH_LIMIT`)"""


class CoveringReport(BaseModel):
    """The long periods that cover all the days from `first` to `last`, a page of them"""

    first: DayOut
    last: DayOut
    count: int
    page: int
    page_size: int
    results: list[Spanning]


class MoveableOut(BaseModel):
    characterisation: CharacterisationOut
    day: DayOut


class EasterReport(BaseModel):
    calendar: Calendar
    year: int
    easter: DayOut
    moveable: list[MoveableOut]


class YearMonth(BaseModel):
    month: int
    first: DayOut
    last: DayOut
    count: int = 0
    """How many dates state a range that meets the month (a repeated event once for each month it falls in)"""


class YearReport(BaseModel):
    calendar: Calendar
    year: int
    months: list[YearMonth]
    truncated: bool = False
    """More dates were found than are counted (`MONTH_LIMIT`)"""
    easter: DayOut
    moveable: list[MoveableOut]


class SettingsOut(BaseModel):
    """What the interface needs to know of the project's calendar settings"""

    calendar: Calendar
    """`CALENDAR_DEFAULT`: the calendar a view opens in"""
    first_year: int | None
    last_year: int | None
    """`CALENDAR_FIRST_YEAR` and `CALENDAR_LAST_YEAR`: the span (None: not set)"""
    narrow_days: int
    extend_margin_years: int


def settings_report() -> SettingsOut:
    return SettingsOut(
        calendar=settings.calendar_default(),
        first_year=settings.first_year(),
        last_year=settings.last_year(),
        narrow_days=settings.narrow_days(),
        extend_margin_years=settings.extend_margin_years(),
    )


class YearCount(BaseModel):
    year: int
    count: int
    """How many dates state a range that meets the year (a repeated event once for each year it falls in)"""


class YearsReport(BaseModel):
    calendar: Calendar
    first_year: int
    last_year: int
    years: list[YearCount]
    truncated: bool = False
    """More dates were found than are counted (`MONTH_LIMIT`)"""


MAX_YEARS = 1000
"""How many years a `years_report` counts at most"""


def count_by_year(
    dated: list[Dated], calendar: Calendar, first_year: int, last_year: int
) -> list[int]:
    """How many distinct dates meet each year from `first_year` to `last_year` (by their stated range, in the
    calendar; a range is counted in every year it reaches)"""
    seen: list[set[Any]] = [set() for _ in range(first_year, last_year + 1)]
    first_day, last_day = (
        year_span(calendar, first_year)[0],
        year_span(calendar, last_year)[1],
    )
    for item in dated:
        if item.latest_strict < first_day or item.earliest_strict > last_day:
            continue
        low = from_jdn(max(item.earliest_strict, first_day), calendar).year
        high = from_jdn(min(item.latest_strict, last_day), calendar).year
        key = (item.ref.id, item.ref.field)
        for year in range(low, high + 1):
            seen[year - first_year].add(key)
    return [len(found) for found in seen]


async def _ensure(first: int, last: int) -> None:
    """Make the days, if the project asks for it and they are within the reach of the calendar"""
    if not settings.auto_extend():
        return
    try:
        low, high = settings.reach_days()
    except settings.NoSpan:
        return
    if low <= first and last <= high:
        await graph.ensure_range(first, last)


def _ref(row: dict[str, Any]) -> Ref:
    return Ref(id=row["id"], label=row["label"], type=row["type"], field=row["field"])


def _names(fields: list[DateField] | None) -> list[str]:
    """The fields to look in, as the query takes them (`Class.field`)"""
    return [f.name for f in (fields if fields is not None else calendar_fields())]


def _is_repeated(row: dict[str, Any]) -> bool:
    return row["kind"].endswith("Recurrence")


def _rule_of(row: dict[str, Any]):
    return rules.from_row(
        {**row, "id": row["id"], "label": row["label"], "type": row["type"] or ""},
        Calendar.GREGORIAN,
    )


def _calendar_of(row: dict[str, Any], default: Calendar) -> Calendar:
    return Calendar(row["calendar"]) if row.get("calendar") else default


def _anchor(row: dict[str, Any]) -> int:
    return row["anchor"] if row["anchor"] is not None else row["earliest_strict"]


def _both_calendars_keys(jdn: int, extra: list[str]) -> list[str]:
    """The keys a rule in either calendar could have and fall on this day (the rule is checked in its own calendar)"""
    keys = day_keys(jdn, Calendar.JULIAN, extra)
    return keys + [k for k in day_keys(jdn, Calendar.GREGORIAN) if k not in keys]


def _characterised(
    by_rule: list[Characterisation], manual: list[dict[str, Any]]
) -> list[Characterised]:
    found = [
        Characterised(
            characterisation=CharacterisationOut.of(c), origin="rule", via="rule"
        )
        for c in by_rule
    ]
    seen = {c.id for c in by_rule}
    for row in manual:
        if row["id"] in seen and row["via"] == "day":
            continue
        found.append(_manual(row))
    return found


def _manual(row: dict[str, Any]) -> Characterised:
    wide = row["via"] != "day"
    return Characterised(
        characterisation=CharacterisationOut(
            id=row["id"],
            label=row["label"],
            type=row["type"],
            kind=row.get("kind"),
            repeated=bool(row.get("kind") and str(row["kind"]).endswith("Recurrence")),
        ),
        origin="manual",
        via=row["via"],
        first=DayOut.of(row["lo"]) if wide else None,
        last=DayOut.of(row["hi"]) if wide else None,
    )


async def day(
    jdn: int,
    calendar: Calendar,
    fields: list[DateField] | None = None,
) -> DayReport:
    """What is on a day: the characterisations (by their rule, and by hand), and every document with a date that holds it
    (`stated` if the date says so, `possible` if only its allowance for doubt holds it), or a repeated event that falls
    on it"""
    await _ensure(jdn, jdn)
    chars = await graph.read_characterisations()
    by_rule = rules.on_day(chars, jdn)
    extra = [c.feast_key for c in by_rule]
    keys = _both_calendars_keys(jdn, extra)
    hits: dict[tuple[UUID, str], Hit] = {}
    names = _names(fields)
    rows, truncated = await graph.dated_between(
        names,
        jdn,
        jdn,
        strict=False,
        keys=keys,
        limit=MONTH_LIMIT,
        long_days=settings.long_days(),
    )
    for row in rows:
        if _is_repeated(row) and not occurs_on(
            _rule_of(row).rule,
            jdn,
            _calendar_of(row, calendar),
            _anchor(row),
            extra,
        ):
            continue
        repeated = _is_repeated(row)
        single = repeated or is_single(row["kind"])
        # (a single date is stated on the day only if it says that day; a period, on each of its days)
        stated = repeated or (
            row["earliest_strict"] == row["latest_strict"] == jdn
            if single
            else row["earliest_strict"] <= jdn <= row["latest_strict"]
        )
        hits[(row["id"], row["field"])] = Hit(
            ref=_ref(row),
            mark="stated" if stated else "possible",
            single=single,
            first=DayOut.of(jdn if repeated else row["earliest_strict"]),
            last=DayOut.of(jdn if repeated else row["latest_strict"]),
        )
    covering, _ = await graph.covering_between(
        names, jdn, jdn, long_days=settings.long_days(), skip=0, size=0
    )
    ordered = sorted(
        hits.values(), key=lambda h: (h.ref.label.lower(), str(h.ref.id), h.ref.field)
    )
    return DayReport(
        day=DayOut.of(jdn),
        calendar=calendar,
        previous=DayOut.of(jdn - 1),
        next=DayOut.of(jdn + 1),
        characterisations=_characterised(by_rule, await graph.manual_between(jdn, jdn)),
        hits=ordered,
        covering=covering,
        truncated=truncated,
    )


async def _dated_in(
    fields: list[DateField] | None,
    first: int,
    last: int,
    calendar: Calendar,
    chars: list[Characterisation],
) -> tuple[list[Dated], bool]:
    """The dates of the fields in the days, as ranges: a date by its stated range, a repeated event by each day it
    falls on (and whether more were found than `MONTH_LIMIT`). Not the long periods that cover all the days
    (`covering`)"""
    rows, truncated = await graph.dated_between(
        _names(fields),
        first,
        last,
        strict=True,
        keys=None,
        limit=MONTH_LIMIT,
        long_days=settings.long_days(),
    )
    found: list[Dated] = []
    for row in rows:
        ref = _ref(row)
        if _is_repeated(row):
            days = occurrences(
                _rule_of(row).rule,
                max(first, row["earliest_strict"]),
                min(last, row["latest_strict"]),
                _calendar_of(row, calendar),
                _anchor(row),
                lambda d: rules.feast_keys(chars, d),
            )
            found.extend(Dated(ref, d, d, single=True) for d in days)
        else:
            found.append(
                Dated(
                    ref,
                    row["earliest_strict"],
                    row["latest_strict"],
                    single=is_single(row["kind"]),
                )
            )
    return found, truncated


async def covering(
    first: int,
    last: int,
    page: int = 1,
    page_size: int = COVERING_PAGE,
    fields: list[DateField] | None = None,
) -> CoveringReport:
    """The long periods (`CALENDAR_LONG_DAYS` or more) that cover all the days from `first` to `last`, beginning
    before them and ending after: the earliest to begin first, a page at a time. A day and a month say how many there
    are, and leave them out of what they list"""
    if first > last:
        raise ValueError("the days go from the first to the last")
    count, rows = await graph.covering_between(
        _names(fields),
        first,
        last,
        long_days=settings.long_days(),
        skip=(page - 1) * page_size,
        size=page_size,
    )
    return CoveringReport(
        first=DayOut.of(first),
        last=DayOut.of(last),
        count=count,
        page=page,
        page_size=page_size,
        results=[
            Spanning(
                ref=_ref(row),
                first=DayOut.of(row["earliest_strict"]),
                last=DayOut.of(row["latest_strict"]),
            )
            for row in rows
        ],
    )


async def month(
    calendar: Calendar,
    year: int,
    month_number: int,
    fields: list[DateField] | None = None,
) -> MonthReport:
    """A month with, on each day, its characterisations and the dates on it; the dates that state a long range are apart"""
    first, last = month_span(calendar, year, month_number)
    await _ensure(first, last)
    chars = await graph.read_characterisations()
    dated, truncated = await _dated_in(fields, first, last, calendar, chars)
    covering_count, _ = await graph.covering_between(
        _names(fields), first, last, long_days=settings.long_days(), skip=0, size=0
    )
    view = place(dated, first, last, settings.narrow_days())
    by_day = rules.days_of(chars, first, last)
    manual = await graph.manual_between(first, last)
    manual_on: dict[int, list[dict[str, Any]]] = {}
    wide: list[Characterised] = []
    for row in manual:
        if row["via"] == "day":
            manual_on.setdefault(row["lo"], []).append(row)
        else:
            wide.append(_manual(row))
    days = [
        MonthDayOut(
            day=DayOut.of(jdn),
            characterisations=_characterised(
                by_day.get(jdn, []), manual_on.get(jdn, [])
            ),
            hits=[Hit(ref=p.ref, mark=p.mark) for p in view.days[jdn]],
        )
        for jdn in range(first, last + 1)
    ]
    return MonthReport(
        calendar=calendar,
        year=year,
        month=month_number,
        first=DayOut.of(first),
        last=DayOut.of(last),
        previous=previous_month(calendar, year, month_number),
        next=next_month(calendar, year, month_number),
        weeks=month_grid(calendar, year, month_number),
        days=days,
        spanning=_spanning(view.spanning),
        between=_spanning(view.between),
        roughly=_spanning(view.roughly),
        characterised_spans=wide,
        covering=covering_count,
        truncated=truncated,
    )


def _spanning(items: list[Dated]) -> list[Spanning]:
    return [
        Spanning(
            ref=d.ref,
            first=DayOut.of(d.earliest_strict),
            last=DayOut.of(d.latest_strict),
        )
        for d in items
    ]


def _moveable(
    chars: list[Characterisation], year: int, calendar: Calendar
) -> list[MoveableOut]:
    return [
        MoveableOut(characterisation=CharacterisationOut.of(c), day=DayOut.of(jdn))
        for c, jdn in rules.moveable(chars, year, calendar)
    ]


async def easter_report(calendar: Calendar, year: int) -> EasterReport:
    return EasterReport(
        calendar=calendar,
        year=year,
        easter=DayOut.of(easter(year, calendar)),
        moveable=_moveable(await graph.read_characterisations(), year, calendar),
    )


async def year_report(
    calendar: Calendar,
    year: int,
    fields: list[DateField] | None = None,
) -> YearReport:
    """The months of a year with how many dates meet each, Easter, and the characterisations that move with it"""
    chars = await graph.read_characterisations()
    spans = [month_span(calendar, year, number) for number in range(1, 13)]
    seen: list[set[tuple[UUID, str]]] = [set() for _ in spans]
    dated, truncated = await _dated_in(
        fields, spans[0][0], spans[-1][1], calendar, chars
    )
    for item in dated:
        for index, (first, last) in enumerate(spans):
            if item.earliest_strict <= last and item.latest_strict >= first:
                seen[index].add((item.ref.id, item.ref.field))
    months = [
        YearMonth(
            month=number,
            first=DayOut.of(first),
            last=DayOut.of(last),
            count=len(seen[number - 1]),
        )
        for number, (first, last) in enumerate(spans, start=1)
    ]
    return YearReport(
        calendar=calendar,
        year=year,
        months=months,
        truncated=truncated,
        easter=DayOut.of(easter(year, calendar)),
        moveable=_moveable(chars, year, calendar),
    )


async def years_report(
    calendar: Calendar,
    first_year: int,
    last_year: int,
    fields: list[DateField] | None = None,
) -> YearsReport:
    """The years from `first_year` to `last_year` with how many dates meet each (for the list of years)"""
    if first_year > last_year:
        raise ValueError("the years go from the first to the last")
    if last_year - first_year + 1 > MAX_YEARS:
        raise ValueError(f"at most {MAX_YEARS} years can be counted at once")
    chars = await graph.read_characterisations()
    first = year_span(calendar, first_year)[0]
    last = year_span(calendar, last_year)[1]
    dated, truncated = await _dated_in(fields, first, last, calendar, chars)
    counts = count_by_year(dated, calendar, first_year, last_year)
    return YearsReport(
        calendar=calendar,
        first_year=first_year,
        last_year=last_year,
        years=[
            YearCount(year=year, count=count)
            for year, count in zip(
                range(first_year, last_year + 1), counts, strict=True
            )
        ],
        truncated=truncated,
    )


async def find_characterisations(q: str | None = None) -> list[CharacterisationOut]:
    found = await graph.read_characterisations()
    if q:
        found = [c for c in found if q.lower() in c.label.lower()]
    return [CharacterisationOut.of(c) for c in rules.unique(found)]


class DayOfCharacterisation(BaseModel):
    day: DayOut
    origin: Origin


async def days_of_characterisation(
    characterisation: UUID, first: int, last: int
) -> list[DayOfCharacterisation] | None:
    """The days from `first` to `last` that a characterisation is on: by its rule and by hand (None: there is none)"""
    own = [c for c in await graph.read_characterisations() if c.id == characterisation]
    if not own:
        return None
    days: dict[int, Origin] = {
        d: "rule" for c in own for d in rules.days_between(c, first, last)
    }
    for row in await graph.manual_between(first, last):
        if row["id"] == characterisation and row["via"] == "day":
            days.setdefault(row["lo"], "manual")
    return [
        DayOfCharacterisation(day=DayOut.of(d), origin=o)
        for d, o in sorted(days.items())
    ]


def check_reach(first: int, last: int) -> None:
    """Raise `OutsideCalendar` unless the days are within the span of the calendar and its margin"""
    low, high = settings.reach_days()
    if first < low or last > high:
        margin = settings.extend_margin_years()
        raise OutsideCalendar(
            f"Those days are outside the calendar: CALENDAR_FIRST_YEAR to CALENDAR_LAST_YEAR with {margin} years "
            "on each side (CALENDAR_EXTEND_MARGIN_YEARS) is what days are made for"
        )


async def attach(characterisation: UUID, target: graph.Target) -> bool:
    first, last = target.days()
    if first > last:
        raise ValueError("a span goes from its first day to its last")
    check_reach(first, last)
    return await graph.attach(characterisation, target)


async def detach(characterisation: UUID, target: graph.Target) -> int:
    return await graph.detach(characterisation, target)
