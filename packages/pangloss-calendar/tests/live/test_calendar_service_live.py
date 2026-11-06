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
from pangloss_dates import Calendar, weekday
from pangloss_dates.easter import easter
from pangloss_models import Document, initialise
from pangloss_testing.live import initialise_database
from pangloss_users import see_unpublished

pytestmark = pytest.mark.asyncio(loop_scope="session")

J = Calendar.JULIAN
G = Calendar.GREGORIAN


def exact(year, month=None, day=None):
    return {"type": "JulianExactDate", "year": year, "month": month, "day": day}


def models():
    import pangloss_dates
    from pangloss_calendar import models as calendar_models
    from pangloss_dates import julian
    from pangloss_dates import models as date_models

    # (and the root of `pangloss_dates`, which the calendar's models import from: it keeps the classes it gave out)
    for module in (date_models, julian, pangloss_dates, calendar_models):
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

    from pangloss_api import get_current_user
    from pangloss_calendar import settings as calendar_settings
    from pangloss_dates import to_jdn

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


def period(start, end):
    return {"type": "JulianPeriod", "start": start, "end": end}


@no_type_check
async def test_a_date_that_is_only_unknown_is_in_no_view(
    clear_database, clear_calendar
):
    """`UnknownDate` says nothing of when: its bounds are the whole span of years, and it was on every day"""
    Factoid, Mass, FeastDay = models()
    await initialise_database()
    await Factoid.Create(label="exact", when=exact(1500, 3, 2)).save()
    await Factoid.Create(label="unknown", when={"type": "JulianUnknownDate"}).save()
    # (a period with one end unknown still says when it began: it stays)
    await Factoid.Create(
        label="from the first",
        when=period(exact(1500, 3, 1), {"type": "JulianUnknownDate"}),
    ).save()

    day = await service.day(parse_day("J1500-03-01"), J)
    assert labels(day.hits) == ["from the first"] and day.covering == 0
    month = await service.month(J, 1500, 3)
    assert [s.ref.label for s in month.spanning] == ["from the first"]
    assert month.roughly == [] and month.between == [] and month.covering == 0
    assert {d.day.julian: labels(d.hits) for d in month.days if d.hits} == {
        "J1500-03-02": ["exact"]
    }
    year = await service.year_report(J, 1500)
    # (January and February have nothing; March the exact day and the period; the rest the period)
    assert [m.count for m in year.months] == [0, 0, 2] + [1] * 9
    # a day later in the period is a day that it covers (it began before, and has no known end)
    later = await service.day(parse_day("J1500-03-02"), J)
    assert labels(later.hits) == ["exact"] and later.covering == 1
    found = await service.covering(parse_day("J1500-03-02"), parse_day("J1500-03-02"))
    assert [s.ref.label for s in found.results] == ["from the first"]


@no_type_check
async def test_long_periods_that_cover_the_view_are_counted_and_read_apart(
    clear_database, clear_calendar, monkeypatch
):
    from pangloss_calendar import settings as calendar_settings

    Factoid, Mass, FeastDay = models()
    await initialise_database()
    # (an exact day, a range, a period of the year 1500 and others: `make_documents`)
    await make_documents(Factoid)
    for label, when in {
        "life": period(exact(1480, 1, 1), exact(1520, 12, 31)),
        "office": period(exact(1490, 6, 1), exact(1510, 6, 1)),
        "term": period(exact(1499, 1, 1), exact(1501, 12, 31)),
        # (long, but it begins in the month, and on a day of it: a date of them like any other)
        "begins in March": period(exact(1500, 3, 2), exact(1520, 12, 31)),
    }.items():
        await Factoid.Create(label=label, when=when).save()
    await Mass.Create(
        label="chantry", when=period(exact(1470, 1, 1), exact(1530, 1, 1))
    ).save()
    second = parse_day("J1500-03-02")

    day = await service.day(second, J)
    assert day.covering == 4 and not day.truncated
    # (the period of the year 1500 covers the day too, but is not long: it is still a date of the day)
    assert labels(day.hits, "stated") == ["begins in March", "exact", "period"]
    month = await service.month(J, 1500, 3)
    assert month.covering == 4
    assert [s.ref.label for s in month.spanning] == ["period", "begins in March"]
    # (and the year counts every month's dates without them)
    year = await service.year_report(J, 1500)
    assert [m.count for m in year.months][0] == 1

    # read a page at a time, the earliest to begin first, of every field
    first = await service.covering(second, second, page=1, page_size=3)
    assert (first.count, first.page, first.page_size) == (4, 1, 3)
    assert [(s.ref.label, s.ref.type, s.ref.field) for s in first.results] == [
        ("chantry", "Mass", "when"),
        ("life", "Factoid", "when"),
        ("office", "Factoid", "when"),
    ]
    assert first.results[0].first.julian == "J1470-01-01"
    assert first.results[0].last.julian == "J1530-01-01"
    rest = await service.covering(second, second, page=2, page_size=3)
    assert rest.count == 4 and [s.ref.label for s in rest.results] == ["term"]
    assert (await service.covering(second, second, page=3, page_size=3)).results == []
    # of the whole month, the same four (the one that begins in it is not one)
    first_of_month, last_of_month = parse_day("J1500-03-01"), parse_day("J1500-03-31")
    whole = await service.covering(first_of_month, last_of_month)
    assert whole.count == 4 and len(whole.results) == 4
    # of three years, only those that begin before them and end after
    wide = await service.covering(parse_day("J1499-01-01"), parse_day("J1501-12-31"))
    assert [s.ref.label for s in wide.results] == ["chantry", "life", "office"]
    with pytest.raises(ValueError):
        await service.covering(last_of_month, first_of_month)

    # the route, by a day's name or its number
    app = FastAPI()
    app.include_router(router)
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )
    got = await client.get(
        f"/api/calendar/covering?first={first_of_month}&last=J1500-03-31&page_size=2"
    )
    assert got.status_code == 200
    body = got.json()
    assert body["count"] == 4 and body["page"] == 1 and body["page_size"] == 2
    assert [s["ref"]["label"] for s in body["results"]] == ["chantry", "life"]
    assert body["first"]["julian"] == "J1500-03-01"
    one = (await client.get("/api/calendar/covering?first=J1500-03-02")).json()
    assert one["count"] == 4 and one["last"]["julian"] == "J1500-03-02"
    assert (await client.get("/api/calendar/day/J1500-03-02")).json()["covering"] == 4
    assert (
        await client.get("/api/calendar/covering?first=J1500-03-31&last=J1500-03-01")
    ).status_code == 422
    assert (
        await client.get("/api/calendar/covering?first=J1500-03-02&page_size=501")
    ).status_code == 422

    # `CALENDAR_LONG_DAYS` says what is long: with none long, they are dates of the day again
    monkeypatch.setattr(calendar_settings, "long_days", lambda settings=None: 10**9)
    day = await service.day(second, J)
    assert day.covering == 0 and labels(day.hits, "stated") == [
        "begins in March",
        "chantry",
        "exact",
        "life",
        "office",
        "period",
        "term",
    ]


@no_type_check
async def test_a_day_is_read_with_one_query_for_all_the_fields(
    clear_database, clear_calendar, monkeypatch
):
    """(There was a query for each field of each class: some sixty for a project with many kinds of statement)"""
    Factoid, Mass, FeastDay = models()
    await initialise_database()
    await Factoid.Create(label="a statement", when=exact(1500, 3, 2)).save()
    await Mass.Create(label="a mass", when=exact(1500, 3, 2)).save()
    asked = []
    dated_between = graph.dated_between

    async def counted(fields, *args, **kwargs):
        asked.append(fields)
        return await dated_between(fields, *args, **kwargs)

    monkeypatch.setattr(graph, "dated_between", counted)
    day = await service.day(parse_day("J1500-03-02"), J)
    assert [(h.ref.label, h.ref.type) for h in day.hits] == [
        ("a mass", "Mass"),
        ("a statement", "Factoid"),
    ]
    assert asked == [["Factoid.when", "Mass.when"]]
