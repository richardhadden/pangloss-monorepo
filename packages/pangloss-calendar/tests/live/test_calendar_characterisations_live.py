"""Characterisations (feasts and the like) on a real database: edges from a rule, attached by hand, and what is out of reach"""

import importlib
from typing import no_type_check

import pytest
from calendar_live_support import count, structure
from pangloss_calendar import graph, service
from pangloss_calendar import settings as calendar_settings
from pangloss_calendar.days import parse_day
from pangloss_dates.calendar import Calendar, to_jdn
from pangloss_dates.easter import easter
from pangloss_models import initialise
from pangloss_models.model_bases.document import Document
from pangloss_testing.live import initialise_database, run

pytestmark = pytest.mark.asyncio(loop_scope="session")

J = Calendar.JULIAN


def exact(year, month=None, day=None):
    return {
        "type": "ExactDate",
        "calendar": "julian",
        "year": year,
        "month": month,
        "day": day,
    }


def models():
    """A feast day, a document with a date, and the base, made again (the registry is emptied for each test)"""
    from pangloss_calendar import models as calendar_models
    from pangloss_dates import julian
    from pangloss_dates import models as date_models

    for module in (date_models, julian, calendar_models):
        importlib.reload(module)

    class FeastDay(calendar_models.DateCharacterisation):
        pass

    class Factoid(Document):
        when: julian.JulianDate

    initialise()
    return FeastDay, Factoid


def yearly(first_year, last_year, **rule):
    return {
        "type": "Recurrence",
        "calendar": "julian",
        "frequency": "yearly",
        "weekdays": [],
        "excluded_days": [],
        "start": exact(first_year),
        "end": exact(last_year, 12, 31),
        **rule,
    }


async def make_feasts(FeastDay):
    return {
        "benedict": await FeastDay.Create(
            label="Benedict",
            use="sarum",
            rank="major",
            when=yearly(1450, 1530, month=3, month_day=21),
        ).save(),
        "pentecost": await FeastDay.Create(
            label="Pentecost", use="sarum", when=yearly(1450, 1530, easter_offset=49)
        ).save(),
        "far": await FeastDay.Create(
            label="Far away",
            use="sarum",
            when=yearly(-400, -300, month=1, month_day=5),
        ).save(),
        "by hand": await FeastDay.Create(
            label="Term day", when={"type": "NoRule"}
        ).save(),
    }


SPAN = (to_jdn(1500, 1, 1, J), to_jdn(1501, 12, 31, J))
REACH = (to_jdn(1490, 1, 1, J), to_jdn(1511, 12, 31, J))


@no_type_check
async def test_rules_are_linked_within_the_span_and_the_margin_and_the_calendar_grows_to_fit(
    clear_database, db_driver, clear_calendar
):
    FeastDay, _ = models()
    await initialise_database()
    await structure()
    await make_feasts(FeastDay)
    await graph.seed(1500, 1501, J)
    report = await graph.link_rules(*REACH, SPAN)
    # Benedict and Pentecost each reach beyond the margin (1450 to 1530); the far one is wholly outside
    assert (report.characterisations, report.clipped, report.outside) == (3, 2, 1)
    assert report.edges == 2 * 22
    assert report.extended > 0
    assert (
        run(
            db_driver,
            "MATCH (d:CalendarDay {jdn: $j}) RETURN count(d) AS c",
            j=parse_day("J1490-03-21"),
        )[0]["c"]
        == 1
    )
    assert (
        run(
            db_driver,
            "MATCH (d:CalendarDay {jdn: $j}) RETURN count(d) AS c",
            j=parse_day("J1489-03-21"),
        )[0]["c"]
        == 0
    )
    edge = run(
        db_driver,
        "MATCH (d:CalendarDay {jdn: $j})-[e:CHARACTERISED_BY]->(c) RETURN e.origin AS o, c.label AS l",
        j=parse_day("J1505-03-21"),
    )
    assert edge == [{"o": "rule", "l": "Benedict"}]
    pentecost = run(
        db_driver,
        "MATCH (d:CalendarDay)-[:CHARACTERISED_BY]->(:FeastDay {label: 'Pentecost'}) WHERE d.jdn = $j RETURN count(d) AS c",
        j=easter(1500, J) + 49,
    )
    assert pentecost[0]["c"] == 1
    # nothing for the far one, and the calendar did not grow towards it
    assert (
        run(
            db_driver,
            "MATCH (:CalendarDay)-[:CHARACTERISED_BY]->(:FeastDay {label: 'Far away'}) RETURN count(*) AS c",
        )[0]["c"]
        == 0
    )
    assert (await graph.status())["first"] == parse_day("J1490-03-21")  # (only as far as a day is needed)


@no_type_check
async def test_linking_again_after_a_change_leaves_what_was_attached_by_hand(
    clear_database, db_driver, clear_calendar
):
    FeastDay, _ = models()
    await initialise_database()
    await structure()
    made = await make_feasts(FeastDay)
    await graph.seed(1500, 1501, J)
    await graph.link_rules(*REACH, SPAN)
    jdn = parse_day("J1500-03-21")
    assert await graph.attach(made["by hand"].id, graph.Target("day", first=jdn))
    await FeastDay.Update(
        id=made["benedict"].id,
        label="Benedict",
        use="sarum",
        rank="major",
        when=yearly(1450, 1530, month=3, month_day=22),
    ).save()
    again = await graph.link_rules(*REACH, SPAN)
    assert again.edges == 2 * 22
    on_21 = run(
        db_driver,
        "MATCH (d:CalendarDay {jdn: $j})-[e:CHARACTERISED_BY]->(c) RETURN c.label AS l, e.origin AS o ORDER BY l",
        j=jdn,
    )
    assert on_21 == [{"l": "Term day", "o": "manual"}]
    on_22 = run(
        db_driver,
        "MATCH (d:CalendarDay {jdn: $j})-[:CHARACTERISED_BY]->(c) RETURN c.label AS l",
        j=jdn + 1,
    )
    assert on_22 == [{"l": "Benedict"}]


@no_type_check
async def test_a_characterisation_is_attached_to_a_day_a_month_a_year_or_a_span_and_taken_away(
    clear_database, db_driver, clear_calendar
):
    FeastDay, _ = models()
    await initialise_database()
    await structure()
    made = await make_feasts(FeastDay)
    term = made["by hand"].id
    day = parse_day("J1500-03-02")
    targets = [
        graph.Target("day", first=day),
        graph.Target("month", calendar=J, year=1500, month=3),
        graph.Target("year", calendar=J, year=1500),
        graph.Target("span", first=day - 3, last=day + 40),
    ]
    for target in targets:
        assert await graph.attach(term, target)
        assert await graph.attach(term, target)  # (again is harmless)
    found = await graph.manual_between(day, day)
    assert sorted(row["via"] for row in found) == ["day", "month", "span", "year"]
    assert all(row["id"] == str(term) or row["id"] == term for row in found)
    month = next(r for r in found if r["via"] == "month")
    assert (month["lo"], month["hi"]) == (to_jdn(1500, 3, 1, J), to_jdn(1500, 3, 31, J))
    # a day in the same month sees all but the day itself; a day outside the span sees only the year
    assert sorted(r["via"] for r in await graph.manual_between(day + 1, day + 1)) == [
        "month",
        "span",
        "year",
    ]
    assert [
        r["via"]
        for r in await graph.manual_between(
            to_jdn(1500, 9, 1, J), to_jdn(1500, 9, 1, J)
        )
    ] == ["year"]
    for target in targets:
        assert await graph.detach(term, target) == 1
    assert await graph.manual_between(day, day) == []
    assert await graph.attach(made["far"].id, graph.Target("span", first=1, last=2))
    # a characterisation that is not there, or was deleted, cannot be attached to
    from uuid import uuid4

    assert not await graph.attach(uuid4(), graph.Target("day", first=day))
    assert count(db_driver, "CalendarSpan") == 2


@no_type_check
async def test_what_is_well_outside_the_calendar_is_refused_and_what_is_just_outside_grows_it(
    clear_database, db_driver, clear_calendar, monkeypatch
):
    FeastDay, _ = models()
    await initialise_database()
    await structure()
    made = await make_feasts(FeastDay)
    term = made["by hand"].id
    monkeypatch.setattr(calendar_settings, "reach_days", lambda settings=None: REACH)
    await graph.seed(1500, 1501, J)
    just_outside = graph.Target("day", first=parse_day("J1495-06-01"))
    assert await service.attach(
        term, just_outside
    )  # (inside the margin: the day is made)
    assert (
        run(
            db_driver,
            "MATCH (d:CalendarDay {jdn: $j}) RETURN count(d) AS c",
            j=just_outside.first,
        )[0]["c"]
        == 1
    )
    aristotle = graph.Target("day", first=to_jdn(-383, 3, 1, J))  # (a birth in 384 BC)
    with pytest.raises(service.OutsideCalendar, match="outside the calendar"):
        await service.attach(term, aristotle)
    with pytest.raises(service.OutsideCalendar):
        await service.attach(
            term, graph.Target("span", first=REACH[1] - 5, last=REACH[1] + 5)
        )
    assert (
        run(
            db_driver,
            "MATCH (d:CalendarDay {jdn: $j}) RETURN count(d) AS c",
            j=aristotle.first,
        )[0]["c"]
        == 0
    )
