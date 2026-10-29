"""`/api/calendar`: a day, a month, a year, Easter, and the feasts (read only; the visibility of any search applies)."""

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query
from pangloss_dates.calendar import MAX_YEAR, MIN_YEAR, Calendar, InvalidDate

from pangloss_calendar import service
from pangloss_calendar.days import InvalidDayRef, parse_day

router = APIRouter(prefix="/api/calendar", tags=["calendar"])

Year = Annotated[int, Path(ge=MIN_YEAR, le=MAX_YEAR)]
MonthNumber = Annotated[int, Path(ge=1, le=12)]
Use = Annotated[str | None, Query(description="Only the feasts of this liturgical use")]


def refused(error: Exception) -> HTTPException:
    return HTTPException(status_code=422, detail=str(error))


def day_of(text: str) -> int:
    try:
        return parse_day(text)
    except InvalidDayRef as error:
        raise refused(error) from error


@router.get("/day/{ref}", response_model=service.DayReport)
async def get_day(
    ref: str,
    calendar: Annotated[
        Calendar | None, Query(description="The calendar the answer is read in")
    ] = None,
    use: Use = None,
):
    """`ref` is `J1500-03-02`, `G1500-03-12` or a day number: the same day under its names"""
    from pangloss_calendar.settings import calendar_default

    return await service.day(day_of(ref), calendar or calendar_default(), use)


@router.get("/month/{calendar}/{year}/{month}", response_model=service.MonthReport)
async def get_month(
    calendar: Calendar, year: Year, month: MonthNumber, use: Use = None
):
    return await service.month(calendar, year, month, use)


@router.get("/year/{calendar}/{year}", response_model=service.YearReport)
async def get_year(calendar: Calendar, year: Year, use: Use = None):
    return await _worked(service.year_report(calendar, year, use))


@router.get("/easter/{calendar}/{year}", response_model=service.EasterReport)
async def get_easter(calendar: Calendar, year: Year, use: Use = None):
    return await _worked(service.easter_report(calendar, year, use))


@router.get("/observances", response_model=list[service.ObservanceOut])
async def list_observances(
    use: Use = None,
    q: Annotated[str | None, Query(description="Part of the key or a name")] = None,
):
    return await service.find_observances(use, q)


@router.get("/observances/{key:path}/days")
async def days_of_observance(
    key: str,
    first: Annotated[str, Query(alias="from", description="A day: J1500-01-01")],
    to: Annotated[str, Query(description="A day: J1500-12-31")],
) -> list[dict[str, Any]]:
    """Where the observance falls between two days (as linked in the graph)"""
    return await service.days_of_observance(key, day_of(first), day_of(to))


async def _worked(awaitable):
    try:
        return await awaitable
    except InvalidDate as error:
        raise refused(error) from error
