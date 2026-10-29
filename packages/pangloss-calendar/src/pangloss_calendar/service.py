"""A day, a month, a year, Easter, and the feasts: the pieces put together.

The dates are found with `pangloss_dates.query` and `Model.search`, so the visibility of the lists (nothing deleted;
nothing unpublished for a reader who may not see it) is that of any search. The feasts are those loaded in the graph
(`pangloss calendar load-observances`); the days themselves are worked out, and need not be in the graph (with
`CALENDAR_AUTO_EXTEND` they are made as they are asked for).
"""

import asyncio
from typing import Any, Literal
from uuid import UUID

from pangloss_dates.calendar import Calendar, Weekday
from pangloss_dates.easter import easter
from pangloss_dates.query import SINGLE_KINDS, on_day, pages
from pangloss_dates.recurrence import occurrences
from pydantic import BaseModel

from pangloss_calendar import graph, settings
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
from pangloss_calendar.observances import (
    Observance,
    falls_on,
    feast_keys,
    observances_on,
)
from pangloss_calendar.views import Dated, place

MONTH_LIMIT = 2000
"""Dates looked at, for each field, to fill a month (more are left out, and the month says `truncated`)"""

Mark = Literal["stated", "possible"]


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


class ObservanceOut(BaseModel):
    key: str
    use: str
    name: dict[str, str]
    rank: str | None
    fixed: tuple[int, int] | None
    easter_offset: int | None

    @classmethod
    def of(cls, o: Observance) -> ObservanceOut:
        return cls(
            key=o.key,
            use=o.use,
            name=o.name,
            rank=o.rank,
            fixed=o.fixed,
            easter_offset=o.easter_offset,
        )


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
    observances: list[ObservanceOut]
    hits: list[Hit]


class MonthDayOut(BaseModel):
    day: DayOut
    observances: list[ObservanceOut]
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
    truncated: bool
    """More dates were found than are shown (`MONTH_LIMIT`)"""


class EasterReport(BaseModel):
    calendar: Calendar
    year: int
    easter: DayOut
    moveable: list[MoveableOut]


class MoveableOut(BaseModel):
    observance: ObservanceOut
    day: DayOut


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


async def observances(use: str | None = None) -> list[Observance]:
    found = await graph.read_observances()
    return [o for o in found if use is None or o.use == use]


async def _ensure(first: int, last: int) -> None:
    if settings.auto_extend():
        await graph.ensure_range(first, last)


def _ref(item: Any, field: DateField) -> Ref:
    return Ref(
        id=item.id,
        label=item.label,
        type=getattr(item, "type", field.model.__name__),
        field=field.field,
    )


async def day(
    jdn: int,
    calendar: Calendar,
    use: str | None = None,
    fields: list[DateField] | None = None,
) -> DayReport:
    """What is on a day: the feasts, and every document with a date that holds it (`stated` if the date says so,
    `possible` if only its allowance for doubt holds it), or a repeated event that falls on it"""
    await _ensure(jdn, jdn)
    use = use if use is not None else settings.use()
    loaded = await observances(use)
    on_it = observances_on(loaded, jdn, calendar)
    keys = feast_keys(loaded, jdn, calendar)
    hits: dict[tuple[UUID, str], Hit] = {}
    for field in fields if fields is not None else calendar_fields():
        stated = await on_day(
            field.model,
            field.field,
            jdn,
            calendar,
            field.family,
            fuzzy=False,
            extra_keys=keys,
        )
        possible = await on_day(
            field.model,
            field.field,
            jdn,
            calendar,
            field.family,
            fuzzy=True,
            extra_keys=keys,
        )
        for item in stated:
            hits[(item.id, field.name)] = Hit(ref=_ref(item, field), mark="stated")
        for item in possible:
            hits.setdefault(
                (item.id, field.name), Hit(ref=_ref(item, field), mark="possible")
            )
    ordered = sorted(
        hits.values(), key=lambda h: (h.ref.label.lower(), str(h.ref.id), h.ref.field)
    )
    return DayReport(
        day=DayOut.of(jdn),
        calendar=calendar,
        observances=[ObservanceOut.of(o) for o in on_it],
        hits=ordered,
    )


def _overlap(field: DateField, first: int, last: int) -> list[dict[str, Any]]:
    """Patterns for the dates of the field whose stated range meets the days `first` to `last`"""
    meets = {"earliest_strict": {"lte": last}, "latest_strict": {"gte": first}}
    single = {
        "$any_of": [
            {field.field: {"type": f"{field.family}{kind}", "where": meets}}
            for kind in SINGLE_KINDS
        ]
    }
    repeated = {
        field.field: {"type": f"{field.family}Recurrence", "where": meets},
    }
    return [single, repeated]


async def _dated_in(
    field: DateField,
    first: int,
    last: int,
    calendar: Calendar,
    loaded: list[Observance],
    use: str | None,
) -> tuple[list[Dated], bool]:
    """The dates of the field in the days, as ranges: a date by its stated range, a repeated event by each day it
    falls on (and whether more were found than `MONTH_LIMIT`)"""
    found: list[Dated] = []
    truncated = False
    semaphore = asyncio.Semaphore(8)

    async def read(item: Any) -> list[Dated]:
        async with semaphore:
            document = await field.model.get(item.id)
        date = getattr(document, field.field, None)
        if date is None or not hasattr(date, "earliest_strict"):
            return []
        ref = _ref(item, field)
        if hasattr(date, "pattern_keys") or hasattr(type(date), "rule_of"):
            rule = type(date)._owner.rule_of(date)
            anchor = date.start.earliest_strict
            lo, hi = max(first, date.earliest_strict), min(last, date.latest_strict)
            days = occurrences(
                rule,
                lo,
                hi,
                calendar,
                anchor,
                lambda d: feast_keys(loaded, d, calendar, use),
            )
            return [Dated(ref, d, d) for d in days]
        return [Dated(ref, date.earliest_strict, date.latest_strict)]

    for where in _overlap(field, first, last):
        items = []
        async for item in pages(field.model, where, MONTH_LIMIT):
            items.append(item)
        truncated = truncated or len(items) >= MONTH_LIMIT
        for part in await asyncio.gather(*(read(item) for item in items)):
            found.extend(part)
    return found, truncated


async def month(
    calendar: Calendar,
    year: int,
    month_number: int,
    use: str | None = None,
    fields: list[DateField] | None = None,
) -> MonthReport:
    """A month with, on each day, its feasts and the dates on it; the dates that state a long range are apart"""
    first, last = month_span(calendar, year, month_number)
    await _ensure(first, last)
    use = use if use is not None else settings.use()
    loaded = await observances(use)
    dated: list[Dated] = []
    truncated = False
    for field in fields if fields is not None else calendar_fields():
        part, cut = await _dated_in(field, first, last, calendar, loaded, use)
        dated.extend(part)
        truncated = truncated or cut
    view = place(dated, first, last, settings.narrow_days())
    days = [
        MonthDayOut(
            day=DayOut.of(jdn),
            observances=[
                ObservanceOut.of(o) for o in observances_on(loaded, jdn, calendar)
            ],
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
        truncated=truncated,
    )


def _moveable(
    loaded: list[Observance], year: int, calendar: Calendar
) -> list[MoveableOut]:
    found = []
    for o in loaded:
        if o.easter_offset is not None:
            jdn = falls_on(o, year, calendar)
            if jdn is not None:
                found.append(
                    MoveableOut(observance=ObservanceOut.of(o), day=DayOut.of(jdn))
                )
    return sorted(found, key=lambda m: (m.day.jdn, m.observance.key))


async def easter_report(
    calendar: Calendar, year: int, use: str | None = None
) -> EasterReport:
    use = use if use is not None else settings.use()
    return EasterReport(
        calendar=calendar,
        year=year,
        easter=DayOut.of(easter(year, calendar)),
        moveable=_moveable(await observances(use), year, calendar),
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
        moveable=_moveable(await observances(use), year, calendar),
    )


async def find_observances(
    use: str | None = None, q: str | None = None
) -> list[ObservanceOut]:
    found = await observances(use)
    if q:
        needle = q.lower()
        found = [
            o
            for o in found
            if needle in o.key.lower()
            or any(needle in n.lower() for n in o.name.values())
        ]
    return [ObservanceOut.of(o) for o in found]


async def days_of_observance(key: str, first: int, last: int) -> list[dict[str, Any]]:
    rows = await graph.observance_days(key, first, last)
    return [
        {"calendar": r["calendar"], "year": r["year"], "day": DayOut.of(r["jdn"])}
        for r in rows
    ]
