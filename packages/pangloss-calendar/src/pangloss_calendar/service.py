"""A day, a month, a year, Easter, and the characterisations: the pieces put together.

The dates are found with `graph.dated_between` (from the dates, by their indexed bounds), so what is deleted, or
unpublished for a reader who may not see it, is left out as it is in the lists. The characterisations (feasts and the
like: `pangloss_calendar.models.DateCharacterisation`) are those of the rule they have, worked out here, and those attached
by hand (`graph.attach`); the days themselves are worked out, and need not be in the graph (with `CALENDAR_AUTO_EXTEND`
they are made as they are asked for, within the reach of the calendar).
"""

from typing import Any, Literal
from uuid import UUID

from pangloss_dates.calendar import Calendar, Weekday
from pangloss_dates.easter import easter
from pangloss_dates.recurrence import day_keys, occurrences, occurs_on
from pydantic import BaseModel

from pangloss_calendar import characterisations as rules
from pangloss_calendar import graph, settings
from pangloss_calendar.characterisations import Characterisation
from pangloss_calendar.days import (
    DayView,
    format_day,
    month_grid,
    month_span,
    next_month,
    previous_month,
    view_of,
)
from pangloss_calendar.fields import DateField, calendar_fields
from pangloss_calendar.views import Dated, place

MONTH_LIMIT = 20_000
"""Dates looked at, for each field, to fill a month or a day (more are left out, and the report says `truncated`)"""

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
    use: str | None
    rank: str | None
    easter_offset: int | None = None

    @classmethod
    def of(cls, c: Characterisation) -> CharacterisationOut:
        return cls(
            id=c.id,
            label=c.label,
            type=c.type,
            use=c.use,
            rank=c.rank,
            easter_offset=c.rule.easter_offset if c.rule else None,
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


class DayReport(BaseModel):
    day: DayOut
    calendar: Calendar
    characterisations: list[Characterised]
    hits: list[Hit]
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
    characterised_spans: list[Characterised]
    """Characterisations attached to the month, its year or a span, not to a day"""
    truncated: bool
    """More dates were found than are shown (`MONTH_LIMIT`)"""


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


class YearReport(BaseModel):
    calendar: Calendar
    year: int
    months: list[YearMonth]
    easter: DayOut
    moveable: list[MoveableOut]


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


def _ref(row: dict[str, Any], field: DateField) -> Ref:
    return Ref(
        id=row["id"],
        label=row["label"],
        type=row["type"] or field.model.__name__,
        field=field.field,
    )


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
            use=row["use"],
            rank=row["rank"],
        ),
        origin="manual",
        via=row["via"],
        first=DayOut.of(row["lo"]) if wide else None,
        last=DayOut.of(row["hi"]) if wide else None,
    )


async def day(
    jdn: int,
    calendar: Calendar,
    use: str | None = None,
    fields: list[DateField] | None = None,
) -> DayReport:
    """What is on a day: the characterisations (by their rule, and by hand), and every document with a date that holds it
    (`stated` if the date says so, `possible` if only its allowance for doubt holds it), or a repeated event that falls
    on it"""
    await _ensure(jdn, jdn)
    use = use if use is not None else settings.use()
    chars = await graph.read_characterisations(use)
    by_rule = rules.on_day(chars, jdn)
    extra = [c.feast_key for c in by_rule]
    keys = _both_calendars_keys(jdn, extra)
    hits: dict[tuple[UUID, str], Hit] = {}
    truncated = False
    for field in fields if fields is not None else calendar_fields():
        rows, cut = await graph.dated_between(
            field.model.__name__,
            field.field,
            jdn,
            jdn,
            strict=False,
            keys=keys,
            limit=MONTH_LIMIT,
        )
        truncated = truncated or cut
        for row in rows:
            if _is_repeated(row) and not occurs_on(
                _rule_of(row).rule,
                jdn,
                _calendar_of(row, calendar),
                _anchor(row),
                extra,
            ):
                continue
            stated = row["earliest_strict"] <= jdn <= row["latest_strict"]
            hits[(row["id"], field.name)] = Hit(
                ref=_ref(row, field), mark="stated" if stated else "possible"
            )
    ordered = sorted(
        hits.values(), key=lambda h: (h.ref.label.lower(), str(h.ref.id), h.ref.field)
    )
    return DayReport(
        day=DayOut.of(jdn),
        calendar=calendar,
        characterisations=_characterised(
            by_rule, await graph.manual_between(jdn, jdn, use)
        ),
        hits=ordered,
        truncated=truncated,
    )


async def _dated_in(
    field: DateField,
    first: int,
    last: int,
    calendar: Calendar,
    chars: list[Characterisation],
) -> tuple[list[Dated], bool]:
    """The dates of the field in the days, as ranges: a date by its stated range, a repeated event by each day it
    falls on (and whether more were found than `MONTH_LIMIT`)"""
    rows, truncated = await graph.dated_between(
        field.model.__name__,
        field.field,
        first,
        last,
        strict=True,
        keys=None,
        limit=MONTH_LIMIT,
    )
    found: list[Dated] = []
    for row in rows:
        ref = _ref(row, field)
        if _is_repeated(row):
            days = occurrences(
                _rule_of(row).rule,
                max(first, row["earliest_strict"]),
                min(last, row["latest_strict"]),
                _calendar_of(row, calendar),
                _anchor(row),
                lambda d: rules.feast_keys(chars, d),
            )
            found.extend(Dated(ref, d, d) for d in days)
        else:
            found.append(Dated(ref, row["earliest_strict"], row["latest_strict"]))
    return found, truncated


async def month(
    calendar: Calendar,
    year: int,
    month_number: int,
    use: str | None = None,
    fields: list[DateField] | None = None,
) -> MonthReport:
    """A month with, on each day, its characterisations and the dates on it; the dates that state a long range are apart"""
    first, last = month_span(calendar, year, month_number)
    await _ensure(first, last)
    use = use if use is not None else settings.use()
    chars = await graph.read_characterisations(use)
    dated: list[Dated] = []
    truncated = False
    for field in fields if fields is not None else calendar_fields():
        part, cut = await _dated_in(field, first, last, calendar, chars)
        dated.extend(part)
        truncated = truncated or cut
    view = place(dated, first, last, settings.narrow_days())
    by_day = rules.days_of(chars, first, last)
    manual = await graph.manual_between(first, last, use)
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
        spanning=[
            Spanning(
                ref=d.ref,
                first=DayOut.of(d.earliest_strict),
                last=DayOut.of(d.latest_strict),
            )
            for d in view.spanning
        ],
        characterised_spans=wide,
        truncated=truncated,
    )


def _moveable(
    chars: list[Characterisation], year: int, calendar: Calendar
) -> list[MoveableOut]:
    return [
        MoveableOut(characterisation=CharacterisationOut.of(c), day=DayOut.of(jdn))
        for c, jdn in rules.moveable(chars, year, calendar)
    ]


async def easter_report(
    calendar: Calendar, year: int, use: str | None = None
) -> EasterReport:
    use = use if use is not None else settings.use()
    return EasterReport(
        calendar=calendar,
        year=year,
        easter=DayOut.of(easter(year, calendar)),
        moveable=_moveable(await graph.read_characterisations(use), year, calendar),
    )


async def year_report(
    calendar: Calendar, year: int, use: str | None = None
) -> YearReport:
    use = use if use is not None else settings.use()
    months = []
    for number in range(1, 13):
        first, last = month_span(calendar, year, number)
        months.append(
            YearMonth(month=number, first=DayOut.of(first), last=DayOut.of(last))
        )
    return YearReport(
        calendar=calendar,
        year=year,
        months=months,
        easter=DayOut.of(easter(year, calendar)),
        moveable=_moveable(await graph.read_characterisations(use), year, calendar),
    )


async def find_characterisations(
    use: str | None = None, q: str | None = None
) -> list[CharacterisationOut]:
    found = await graph.read_characterisations(use)
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
