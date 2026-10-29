"""`/api/calendar`: a day, a month, a year, Easter, and the characterisations (feasts and the like).

Reading is open, with the visibility of any search (nothing deleted; nothing unpublished for a reader who may not see
it). Attaching a characterisation to a day, a month, a year or a span, and taking it away, needs a user who is logged in.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pangloss_api.dependencies import get_current_user
from pangloss_dates.calendar import MAX_YEAR, MIN_YEAR, Calendar, InvalidDate
from pydantic import BaseModel

from pangloss_calendar import graph, service, settings
from pangloss_calendar.days import InvalidDayRef, parse_day

router = APIRouter(prefix="/api/calendar", tags=["calendar"])

Year = Annotated[int, Path(ge=MIN_YEAR, le=MAX_YEAR)]
MonthNumber = Annotated[int, Path(ge=1, le=12)]
Use = Annotated[str | None, Query(description="Only the characterisations of this use")]
logged_in = [Depends(get_current_user)]


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
    return await service.day(day_of(ref), calendar or settings.calendar_default(), use)


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


@router.get("/characterisations", response_model=list[service.CharacterisationOut])
async def list_characterisations(
    use: Use = None,
    q: Annotated[str | None, Query(description="Part of the label")] = None,
):
    return await service.find_characterisations(use, q)


@router.get(
    "/characterisations/{characterisation}/days",
    response_model=list[service.DayOfCharacterisation],
)
async def days_of_characterisation(
    characterisation: UUID,
    first: Annotated[str, Query(alias="from", description="A day: J1500-01-01")],
    to: Annotated[str, Query(description="A day: J1500-12-31")],
):
    """Where the characterisation is between two days: by its rule, and by hand"""
    found = await service.days_of_characterisation(
        characterisation, day_of(first), day_of(to)
    )
    if found is None:
        raise HTTPException(status_code=404, detail="There is no such characterisation")
    return found


class Attachment(BaseModel):
    """What a characterisation is attached to: give one of `day`; `calendar`, `year` and `month`; `calendar` and `year`;
    or `first` and `last` (a span of days). A day is `J1500-03-02`, `G1500-03-12` or a day number."""

    characterisation: UUID
    day: str | None = None
    calendar: Calendar | None = None
    year: int | None = None
    month: int | None = None
    first: str | None = None
    last: str | None = None

    def target(self) -> graph.Target:
        if self.day is not None:
            return graph.Target("day", first=day_of(self.day))
        if self.first is not None and self.last is not None:
            return graph.Target(
                "span", first=day_of(self.first), last=day_of(self.last)
            )
        if self.calendar is not None and self.year is not None:
            if self.month is not None:
                if not 1 <= self.month <= 12:
                    raise refused(ValueError(f"month {self.month} is not from 1 to 12"))
                return graph.Target(
                    "month", calendar=self.calendar, year=self.year, month=self.month
                )
            return graph.Target("year", calendar=self.calendar, year=self.year)
        raise refused(
            ValueError(
                "give a day; a calendar, year and month; a calendar and year; or first and last"
            )
        )


@router.post("/attach", status_code=201, dependencies=logged_in)
async def attach(body: Attachment) -> dict[str, bool]:
    """Attach a characterisation by hand. Days within the span of the calendar, and the margin beyond it, are made
    if they are not there; anything beyond that is refused (422)"""
    try:
        made = await service.attach(body.characterisation, body.target())
    except (service.OutsideCalendar, settings.NoSpan, InvalidDate, ValueError) as error:
        raise refused(error) from error
    if not made:
        raise HTTPException(status_code=404, detail="There is no such characterisation")
    return {"attached": True}


@router.post("/detach", dependencies=logged_in)
async def detach(body: Attachment) -> dict[str, int]:
    """Take away what was attached by hand (what a rule gives is not touched)"""
    try:
        return {"removed": await service.detach(body.characterisation, body.target())}
    except (InvalidDate, ValueError) as error:
        raise refused(error) from error


async def _worked(awaitable):
    try:
        return await awaitable
    except InvalidDate as error:
        raise refused(error) from error
