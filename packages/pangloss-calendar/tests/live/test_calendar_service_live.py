"""The calendar's day, month, year and Easter against documents with dates (the exit test of phase 3)"""

import importlib
from typing import no_type_check

import httpx2 as httpx
import pytest
from calendar_live_support import structure
from fastapi import FastAPI
from pangloss_calendar import graph, service
from pangloss_calendar.api import router
from pangloss_calendar.days import parse_day
from pangloss_dates.calendar import Calendar, weekday
from pangloss_dates.easter import easter
from pangloss_models import initialise
from pangloss_models.model_bases.document import Document
from pangloss_testing.live import initialise_database
from pangloss_users import see_unpublished

pytestmark = pytest.mark.asyncio(loop_scope="session")

J = Calendar.JULIAN
G = Calendar.GREGORIAN


def exact(year, month=None, day=None):
    return {"type": "JulianExactDate", "year": year, "month": month, "day": day}


def models():
    from pangloss_calendar import models as calendar_models
    from pangloss_dates import julian
    from pangloss_dates import models as date_models

    for module in (date_models, julian, calendar_models):
        importlib.reload(module)

    class FeastDay(calendar_models.DateCharacterisation):
        # (a project says what else it wants of one: the base has only `when`)
        use: str | None = None
        rank: str | None = None

    class Factoid(Document):
        when: julian.JulianDate

    class Mass(Document):
        when: julian.JulianDate

    initialise()
    return Factoid, Mass, FeastDay


def yearly(first_year, last_year, **rule):
    return {
        "type": "Recurrence",
        "calendar": "julian",
        "frequency": "yearly",
        "weekdays": [],
        "excluded_days": [],
        "start": {"type": "ExactDate", "calendar": "julian", "year": first_year},
        "end": {
            "type": "ExactDate",
            "calendar": "julian",
            "year": last_year,
            "month": 12,
            "day": 31,
        },
        **rule,
    }


async def make_feasts(FeastDay):
    return {
        "march": await FeastDay.Create(
            label="Second of March",
            use="sarum",
            when=yearly(1450, 1530, month=3, month_day=2),
        ).save(),
        "pentecost": await FeastDay.Create(
            label="Pentecost", use="sarum", when=yearly(1450, 1530, easter_offset=49)
        ).save(),
        "by hand": await FeastDay.Create(
            label="Term day", when={"type": "NoRule"}
        ).save(),
        "once": await FeastDay.Create(
            label="Council",
            when={
                "type": "JulianDateRange",
                "not_before": exact(1500, 3, 4),
                "not_after": exact(1500, 3, 5),
            },
        ).save(),
        "lent": await FeastDay.Create(
            label="Lent 1500",
            when={
                "type": "JulianPeriod",
                "start": exact(1500, 2, 5),
                "end": exact(1500, 3, 21),
            },
        ).save(),
    }


async def make_documents(Factoid):
    created = {}
    for label, when in {
        "exact": exact(1500, 3, 2),
        "range": {
            "type": "JulianDateRange",
            "not_before": exact(1500, 3, 1),
            "not_after": exact(1500, 3, 3),
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
    Factoid, Mass, FeastDay = models()
    await initialise_database()
    await structure()
    await make_documents(Factoid)
    await Factoid.Create(
        label="yearly",
        when={
            "type": "JulianRecurrence",
            "frequency": "yearly",
            "weekdays": [],
            "excluded_days": [],
            "month": 3,
            "month_day": 2,
            "start": exact(1450),
            "end": exact(1530, 12, 31),
        },
    ).save()
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
    await make_feasts(FeastDay)
    report = await service.day(parse_day("J1500-03-02"), J)
    assert report.day.julian == "J1500-03-02" and report.day.gregorian == "G1500-03-12"
    assert [(c.characterisation.label, c.origin) for c in report.characterisations] == [
        ("Lent 1500", "rule"),
        ("Second of March", "rule"),
    ]
    by_char = {
        c.characterisation.label: c.characterisation for c in report.characterisations
    }
    assert by_char["Second of March"].repeated and by_char[
        "Second of March"
    ].kind.endswith("Recurrence")
    assert not by_char["Lent 1500"].repeated and by_char["Lent 1500"].kind.endswith(
        "Period"
    )
    # (the council, one day on the 4th or the 5th, is on both days once and not on the 2nd)
    fourth = await service.day(parse_day("J1500-03-04"), J)
    assert [c.characterisation.label for c in fourth.characterisations] == [
        "Council",
        "Lent 1500",
    ]
    assert labels(report.hits, "stated") == [
        "exact",
        "period",
        "weekly",
        "yearly",
    ]
    # (the range says one day from the 1st to the 3rd; a week either side of the 6th allows the 2nd)
    assert labels(report.hits, "possible") == ["about", "range"]
    by_label = {h.ref.label: h for h in report.hits}
    assert by_label["range"].single and by_label["range"].first.julian == "J1500-03-01"
    assert by_label["range"].last.julian == "J1500-03-03"
    assert (
        not by_label["period"].single
        and by_label["period"].last.julian == "J1500-12-31"
    )
    assert (
        by_label["weekly"].single and by_label["weekly"].first.julian == "J1500-03-02"
    )
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
    Factoid, Mass, FeastDay = models()
    await initialise_database()
    made = await make_documents(Factoid)
    run_id = made["exact"].id

    token = see_unpublished.set(False)
    try:
        assert "exact" in labels((await service.day(parse_day("J1500-03-02"), J)).hits)
        # unpublished
        from pangloss_core import backend

        async with backend.current().database().driver.session() as session:
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
    Factoid, Mass, FeastDay = models()
    await initialise_database()
    await make_documents(Factoid)
    await Factoid.Create(
        label="sometime in 1500", when={"type": "JulianExactDate", "year": 1500}
    ).save()
    await Factoid.Create(
        label="fortnight",
        when={
            "type": "JulianPeriod",
            "start": exact(1500, 3, 10),
            "end": exact(1500, 3, 23),
        },
    ).save()
    report = await service.month(J, 1500, 3)
    by_day = {d.day.julian: labels(d.hits) for d in report.days if d.hits}
    # (a single date known within a range is not on the days: it is between them)
    assert "J1500-03-01" not in by_day
    assert by_day["J1500-03-02"] == ["exact"]
    assert by_day["J1500-03-20"] == ["other day"]
    assert [s.ref.label for s in report.between] == ["range"]
    assert report.between[0].first.julian == "J1500-03-01"
    # (the year-long period is a bar; the single date known only to the year is listed)
    assert [s.ref.label for s in report.spanning] == ["period", "fortnight"]
    assert [s.ref.label for s in report.roughly] == ["sometime in 1500"]
    assert report.weeks[0][0] is None or report.weeks[0][0] == report.first.jdn
    assert report.previous == (1500, 2) and report.next == (1500, 4)
    assert not report.truncated


@no_type_check
async def test_easter_and_the_year(clear_database, clear_calendar):
    Factoid, Mass, FeastDay = models()
    await initialise_database()
    await make_feasts(FeastDay)
    report = await service.easter_report(J, 1500)
    assert report.easter.jdn == easter(1500, J)
    assert [m.characterisation.label for m in report.moveable] == ["Pentecost"]
    assert report.moveable[0].day.jdn == easter(1500, J) + 49
    await make_documents(Factoid)
    year = await service.year_report(J, 1500)
    assert [m.month for m in year.months] == list(range(1, 13))
    # the exact day, the range and the 20th are in March; the period covers the year; the year 1490 is not in it
    counts = [m.count for m in year.months]
    assert counts[2] == 5 and counts[0] == counts[11] == 1 and not year.truncated
    assert (
        year.months[1].last.jdn - year.months[1].first.jdn == 28
    )  # (Julian 1500 is a leap year)
    assert year.easter.jdn == easter(1500, J)


@no_type_check
async def test_the_routes(clear_database, clear_calendar, monkeypatch):
    from types import SimpleNamespace

    from pangloss_api.dependencies import get_current_user
    from pangloss_calendar import settings as calendar_settings
    from pangloss_dates.calendar import to_jdn

    Factoid, Mass, FeastDay = models()
    await initialise_database()
    await structure()
    await make_documents(Factoid)
    made = await make_feasts(FeastDay)
    await graph.seed(1500, 1500, J)
    await graph.link_rules(
        to_jdn(1495, 1, 1, J),
        to_jdn(1505, 12, 31, J),
        (to_jdn(1500, 1, 1, J), to_jdn(1500, 12, 31, J)),
    )
    monkeypatch.setattr(
        calendar_settings,
        "reach_days",
        lambda settings=None: (to_jdn(1495, 1, 1, J), to_jdn(1505, 12, 31, J)),
    )
    app = FastAPI()
    app.include_router(router)
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )
    got = await client.get("/api/calendar/day/J1500-03-02?calendar=julian")
    assert got.status_code == 200
    body = got.json()
    assert body["day"]["gregorian"] == "G1500-03-12"
    assert body["previous"]["julian"] == "J1500-03-01"
    assert body["next"]["gregorian"] == "G1500-03-13"
    assert {h["ref"]["label"] for h in body["hits"]} >= {"exact", "range"}
    assert [c["characterisation"]["label"] for c in body["characterisations"]] == [
        "Lent 1500",
        "Second of March",
    ]
    assert [c["characterisation"]["repeated"] for c in body["characterisations"]] == [
        False,
        True,
    ]
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
    # the settings the interface reads, and the years of the span with their counts
    monkeypatch.setattr(calendar_settings, "first_year", lambda settings=None: 1499)
    monkeypatch.setattr(calendar_settings, "last_year", lambda settings=None: 1501)
    read = (await client.get("/api/calendar/settings")).json()
    assert read["first_year"] == 1499 and read["last_year"] == 1501
    assert read["calendar"] in ("julian", "gregorian") and read["narrow_days"] == 7
    years = (await client.get("/api/calendar/years/julian")).json()
    assert [y["year"] for y in years["years"]] == [1499, 1500, 1501]
    assert years["years"][1]["count"] >= 5 and not years["truncated"]
    asked = (await client.get("/api/calendar/years/julian?from=1500&to=1500")).json()
    assert [y["year"] for y in asked["years"]] == [1500]
    assert (
        await client.get("/api/calendar/years/julian?from=1501&to=1500")
    ).status_code == 422
    assert (
        await client.get("/api/calendar/years/julian?from=1&to=1500")
    ).status_code == 422
    monkeypatch.setattr(calendar_settings, "first_year", lambda settings=None: None)
    assert (await client.get("/api/calendar/years/julian")).status_code == 422
    assert (await client.get("/api/calendar/settings")).json()["first_year"] is None
    found = (await client.get("/api/calendar/characterisations?q=pente")).json()
    assert [c["label"] for c in found] == ["Pentecost"]
    days = (
        await client.get(
            f"/api/calendar/characterisations/{made['march'].id}/days?from=J1500-01-01&to=J1500-12-31"
        )
    ).json()
    assert [(d["day"]["julian"], d["origin"]) for d in days] == [
        ("J1500-03-02", "rule")
    ]
    assert (
        await client.get(
            f"/api/calendar/characterisations/{made['march'].id}/days?from=J1500-01-01"
        )
    ).status_code == 422

    # attaching needs a user
    attach = {"characterisation": str(made["by hand"].id), "day": "J1500-03-05"}
    assert (await client.post("/api/calendar/attach", json=attach)).status_code in (
        401,
        403,
    )
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        username="someone"
    )
    assert (await client.post("/api/calendar/attach", json=attach)).status_code == 201
    on_day = (await client.get("/api/calendar/day/J1500-03-05")).json()
    assert [
        (c["characterisation"]["label"], c["origin"], c["via"])
        for c in on_day["characterisations"]
    ] == [
        ("Council", "rule", "rule"),
        ("Lent 1500", "rule", "rule"),
        ("Term day", "manual", "day"),
    ]
    month = {
        "characterisation": str(made["by hand"].id),
        "calendar": "julian",
        "year": 1500,
        "month": 3,
    }
    assert (await client.post("/api/calendar/attach", json=month)).status_code == 201
    in_month = (await client.get("/api/calendar/month/julian/1500/3")).json()
    assert [
        c["characterisation"]["label"] for c in in_month["characterised_spans"]
    ] == ["Term day"]
    assert in_month["characterised_spans"][0]["via"] == "month"
    assert (await client.post("/api/calendar/detach", json=attach)).json() == {
        "removed": 1
    }
    assert (await client.post("/api/calendar/detach", json=month)).json() == {
        "removed": 1
    }
    # beyond the calendar, no such thing, no target
    far = {"characterisation": str(made["by hand"].id), "day": "J-0383-03-01"}
    refused = await client.post("/api/calendar/attach", json=far)
    assert (
        refused.status_code == 422
        and "outside the calendar" in refused.json()["detail"]
    )
    missing = {
        "characterisation": "01a18688-4cf0-73dd-9d9c-a1c659bef751",
        "day": "J1500-03-05",
    }
    assert (await client.post("/api/calendar/attach", json=missing)).status_code == 404
    assert (
        await client.post(
            "/api/calendar/attach",
            json={"characterisation": attach["characterisation"]},
        )
    ).status_code == 422


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
    Factoid, Mass, FeastDay = models()
    await initialise_database()
    for i in range(5):
        await Factoid.Create(label=f"f{i}", when=exact(1500, 3, 2)).save()
    monkeypatch.setattr(service, "MONTH_LIMIT", 3)
    day = await service.day(parse_day("J1500-03-02"), J)
    assert day.truncated and len(day.hits) == 3
    assert (await service.month(J, 1500, 3)).truncated
    monkeypatch.setattr(service, "MONTH_LIMIT", 5)
    assert not (await service.day(parse_day("J1500-03-02"), J)).truncated
