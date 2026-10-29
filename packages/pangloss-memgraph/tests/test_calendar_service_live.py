# ruff: noqa: F811, RUF059
"""The calendar's day, month, year and Easter against documents with dates (the exit test of phase 3)"""

import importlib
from typing import no_type_check

import httpx2 as httpx
import pytest
from fastapi import FastAPI
from pangloss_calendar import graph, service
from pangloss_calendar.api import router
from pangloss_calendar.days import parse_day
from pangloss_calendar.observances import parse
from pangloss_dates.calendar import Calendar, weekday
from pangloss_dates.easter import easter
from pangloss_memgraph.databases.memgraph.initialise_database import (
    initialise_database,
)
from pangloss_models import initialise
from pangloss_models.model_bases.document import Document
from pangloss_users import see_unpublished

from .test_calendar_live import clear_calendar, structure  # noqa: F401

pytestmark = pytest.mark.asyncio(loop_scope="session")

J = Calendar.JULIAN
G = Calendar.GREGORIAN


def exact(year, month=None, day=None):
    return {"type": "JulianExactDate", "year": year, "month": month, "day": day}


def models():
    from pangloss_dates import julian, models

    for module in (models, julian):
        importlib.reload(module)

    class Factoid(Document):
        when: julian.JulianDate

    class Mass(Document):
        when: julian.JulianDate

    initialise()
    return Factoid, Mass


FEASTS = """
[[observance]]
key = "sarum:second-of-march"
use = "sarum"
fixed = { month = 3, day = 2 }

[[observance]]
key = "sarum:pentecost"
use = "sarum"
easter_offset = 49
"""


async def make_documents(Factoid):
    created = {}
    for label, when in {
        "exact": exact(1500, 3, 2),
        "range": {
            "type": "JulianDateRange",
            "earliest": exact(1500, 3, 1),
            "latest": exact(1500, 3, 3),
        },
        "about": {"type": "JulianEDTFDate", "edtf": "1500-03-06~"},
        "period": {
            "type": "JulianPeriod",
            "start": exact(1500, 1, 1),
            "end": exact(1500, 12, 31),
        },
        "other day": exact(1500, 3, 20),
        "other year": exact(1490),
    }.items():
        created[label] = await Factoid.Create(label=label, when=when).save()
    return created


def labels(hits, mark=None):
    return sorted(h.ref.label for h in hits if mark is None or h.mark == mark)


@no_type_check
async def test_a_day_finds_every_kind_of_date_and_the_feast(
    clear_database, clear_calendar
):
    Factoid, Mass = models()
    await initialise_database()
    await structure()
    await make_documents(Factoid)
    await Factoid.Create(
        label="weekly",
        when={
            "type": "JulianRecurrence",
            "frequency": "weekly",
            "weekdays": [int(weekday(parse_day("J1500-03-02")))],
            "excluded_days": [],
            "start": exact(1500, 1, 1),
            "end": exact(1500, 12, 31),
        },
    ).save()
    await graph.load_observances(parse(FEASTS), [J])
    report = await service.day(parse_day("J1500-03-02"), J)
    assert report.day.julian == "J1500-03-02" and report.day.gregorian == "G1500-03-12"
    assert [o.key for o in report.observances] == ["sarum:second-of-march"]
    assert labels(report.hits, "stated") == ["exact", "period", "range", "weekly"]
    assert labels(report.hits, "possible") == [
        "about"
    ]  # (a week either side of the 6th allows the 2nd)
    assert "other day" not in labels(report.hits) and "other year" not in labels(
        report.hits
    )
    # the same day by its other name is the same answer
    gregorian = await service.day(parse_day("G1500-03-12"), G)
    assert labels(gregorian.hits) == labels(report.hits)
    # and a day in the lifetime of the period only has the period (and, as possible, the allowance for doubt)
    assert labels((await service.day(parse_day("J1500-03-10"), J)).hits, "stated") == [
        "period"
    ]


@no_type_check
async def test_what_a_reader_may_not_see_is_not_found(clear_database, clear_calendar):
    Factoid, Mass = models()
    await initialise_database()
    made = await make_documents(Factoid)
    run_id = made["exact"].id
    from .conftest import MEMGRAPH_DATABASE  # noqa: F401

    token = see_unpublished.set(False)
    try:
        assert "exact" in labels((await service.day(parse_day("J1500-03-02"), J)).hits)
        # unpublished
        from pangloss_memgraph.databases.memgraph.database import Database

        async with Database.default.driver.session() as session:
            await session.run(
                "MATCH (n:HeadNode {id: $id}) SET n.published = false", id=str(run_id)
            )
        assert "exact" not in labels(
            (await service.day(parse_day("J1500-03-02"), J)).hits
        )
        see_unpublished.set(True)
        assert "exact" in labels((await service.day(parse_day("J1500-03-02"), J)).hits)
        see_unpublished.set(False)
        # deleted
        await Factoid.delete(made["range"].id)
        assert "range" not in labels(
            (await service.day(parse_day("J1500-03-02"), J)).hits
        )
    finally:
        see_unpublished.reset(token)


@no_type_check
async def test_a_month_puts_narrow_dates_on_days_and_wide_ones_apart(
    clear_database, clear_calendar
):
    Factoid, Mass = models()
    await initialise_database()
    await make_documents(Factoid)
    report = await service.month(J, 1500, 3)
    by_day = {d.day.julian: labels(d.hits) for d in report.days if d.hits}
    assert by_day["J1500-03-01"] == ["range"]
    assert by_day["J1500-03-02"] == ["exact", "range"]
    assert by_day["J1500-03-20"] == ["other day"]
    assert [s.ref.label for s in report.spanning] == ["period"]
    assert report.weeks[0][0] is None or report.weeks[0][0] == report.first.jdn
    assert report.previous == (1500, 2) and report.next == (1500, 4)
    marks = {
        h.ref.label: h.mark
        for d in report.days
        for h in d.hits
        if d.day.julian == "J1500-03-02"
    }
    assert marks["exact"] == "stated" and marks["range"] == "possible"
    assert not report.truncated


@no_type_check
async def test_easter_and_the_year(clear_database, clear_calendar):
    Factoid, Mass = models()
    await initialise_database()
    await graph.load_observances(parse(FEASTS), [J])
    report = await service.easter_report(J, 1500)
    assert report.easter.jdn == easter(1500, J)
    assert [m.observance.key for m in report.moveable] == ["sarum:pentecost"]
    assert report.moveable[0].day.jdn == easter(1500, J) + 49
    year = await service.year_report(J, 1500)
    assert [m.month for m in year.months] == list(range(1, 13))
    assert (
        year.months[1].last.jdn - year.months[1].first.jdn == 28
    )  # (Julian 1500 is a leap year)
    assert year.easter.jdn == easter(1500, J)


@no_type_check
async def test_the_routes(clear_database, clear_calendar):
    Factoid, Mass = models()
    await initialise_database()
    await structure()
    await make_documents(Factoid)
    await graph.seed(1500, 1500, J)
    await graph.load_observances(parse(FEASTS), [J])
    app = FastAPI()
    app.include_router(router)
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )
    got = await client.get("/api/calendar/day/J1500-03-02?calendar=julian")
    assert got.status_code == 200
    body = got.json()
    assert body["day"]["gregorian"] == "G1500-03-12"
    assert {h["ref"]["label"] for h in body["hits"]} >= {"exact", "range"}
    assert (await client.get("/api/calendar/day/nonsense")).status_code == 422
    assert (await client.get("/api/calendar/day/J1500-02-30")).status_code == 422
    assert (await client.get("/api/calendar/month/julian/1500/13")).status_code == 422
    assert (await client.get("/api/calendar/month/julian/1500/3")).status_code == 200
    assert (
        (await client.get("/api/calendar/year/julian/1500"))
        .json()["easter"]["julian"]
        .startswith("J1500-04")
    )
    assert (await client.get("/api/calendar/easter/gregorian/2000")).json()["easter"][
        "gregorian"
    ] == "G2000-04-23"
    found = (await client.get("/api/calendar/observances?use=sarum&q=pente")).json()
    assert [o["key"] for o in found] == ["sarum:pentecost"]
    days = (
        await client.get(
            "/api/calendar/observances/sarum:second-of-march/days?from=J1500-01-01&to=J1500-12-31"
        )
    ).json()
    assert [d["day"]["julian"] for d in days] == ["J1500-03-02"]


@no_type_check
async def test_the_date_fields_are_found_from_the_models_and_can_be_narrowed():
    from types import SimpleNamespace

    from pangloss_calendar.fields import calendar_fields

    models()
    found = calendar_fields()
    assert [(f.name, f.family) for f in found] == [
        ("Factoid.when", "Julian"),
        ("Mass.when", "Julian"),
    ]
    narrowed = calendar_fields(SimpleNamespace(CALENDAR_FIELDS=["Mass.when"]))
    assert [f.name for f in narrowed] == ["Mass.when"]
    assert calendar_fields(SimpleNamespace(CALENDAR_FIELDS=["Mass.sent"])) == []


@no_type_check
async def test_a_day_or_month_with_more_dates_than_the_limit_says_so(
    clear_database, clear_calendar, monkeypatch
):
    Factoid, Mass = models()
    await initialise_database()
    for i in range(5):
        await Factoid.Create(label=f"f{i}", when=exact(1500, 3, 2)).save()
    monkeypatch.setattr(service, "MONTH_LIMIT", 3)
    day = await service.day(parse_day("J1500-03-02"), J)
    assert day.truncated and len(day.hits) == 3
    assert (await service.month(J, 1500, 3)).truncated
    monkeypatch.setattr(service, "MONTH_LIMIT", 5)
    assert not (await service.day(parse_day("J1500-03-02"), J)).truncated
