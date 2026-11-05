"""Dateable documents on a real database: the copy of the date is stored on the document, read in its reference view
(in a list and in what refers to an entity), ordered by, and made again when the date changes"""

import importlib
from typing import no_type_check

import pytest
from pangloss_dates import Calendar, to_jdn
from pangloss_models import Document, Entity, Match, ReifiedRelation, initialise
from pangloss_testing.live import initialise_database

pytestmark = pytest.mark.asyncio(loop_scope="session")

J = Calendar.JULIAN


def exact(year, month=None, day=None):
    return {"type": "JulianExactDate", "year": year, "month": month, "day": day}


def models():
    from pangloss_dates import dateable, gregorian, julian, models

    for module in (models, julian, gregorian, dateable):
        importlib.reload(module)

    class Person(Entity):
        pass

    class Identification[T](ReifiedRelation[T]):
        certainty: int

    class Event(Document, dateable.Dateable):
        date: julian.JulianDate  # ty: ignore[invalid-mutable-override]
        concerns: Person
        identified: list[Identification[Person]]

    class Note(Document):
        about: Person

    initialise()
    return Person, Event, Note


@no_type_check
async def test_a_dateable_is_listed_and_ordered_by_its_date(clear_database):
    Person, Event, _ = models()
    await initialise_database()
    person = await Person.Create(label="Ada").save()
    ref = {"type": "Person", "id": person.id}
    for label, year in (("b", 1510), ("a", 1520), ("c", 1500)):
        await Event.Create(
            label=label, date=exact(year), concerns=ref, identified=[]
        ).save()

    listed = await Event.list()
    texts = {item.label: item.date_text for item in listed.results}
    assert texts == {"a": "1520", "b": "1510", "c": "1500"}
    assert {item.label: item.date_sort_day for item in listed.results}["c"] == (
        to_jdn(1500, 1, 1, J) + to_jdn(1500, 12, 31, J)
    ) // 2

    found = await Event.search(Match(order_by=[{"field": "date_sort_day"}]))
    assert [item.label for item in found.results] == ["c", "b", "a"]


@no_type_check
async def test_what_refers_to_an_entity_carries_its_date(clear_database):
    Person, Event, Note = models()
    await initialise_database()
    person = await Person.Create(label="Ada").save()
    ref = {"type": "Person", "id": person.id}
    await Event.Create(
        label="Direct", date=exact(1500, 3), concerns=ref, identified=[]
    ).save()
    other = await Person.Create(label="Bea").save()
    await Event.Create(
        label="Through a reified relation",
        date={
            "type": "JulianDateRange",
            "not_before": exact(1501),
            "not_after": {"type": "JulianUnknownDate"},
        },
        concerns={"type": "Person", "id": other.id},
        identified=[{"type": "Identification", "certainty": 1, "target": [ref]}],
    ).save()
    await Note.Create(label="Not dateable", about=ref).save()

    read = (await Person.get(id=person.id)).model_dump(by_alias=True)
    (direct,) = read["concernsReverse"]
    assert direct["dateText"] == "1500-03"
    (through,) = read["identifiedReverse"]
    assert through["dateText"] == "≥ 1501"
    assert (
        through["dateSortDay"] == (to_jdn(1501, 1, 1, J) + to_jdn(1501, 12, 31, J)) // 2
    )
    (note,) = read["aboutReverse"]
    assert "dateText" not in note


@no_type_check
async def test_the_copy_follows_the_date_when_it_is_changed(clear_database):
    Person, Event, _ = models()
    await initialise_database()
    person = await Person.Create(label="Ada").save()
    ref = {"type": "Person", "id": person.id}
    event = await Event.Create(
        label="x", date=exact(1500), concerns=ref, identified=[]
    ).save()
    await Event.Update(
        id=event.id,
        label="x",
        date={
            "type": "JulianPeriod",
            "start": exact(1500),
            "end": {"type": "JulianOngoingDate"},
        },
        concerns=ref,
        identified=[],
    ).save()
    (listed,) = (await Event.list()).results
    assert listed.date_text == "1500–…"


@no_type_check
async def test_documents_written_before_they_were_dateable_are_filled_in(
    clear_database, db_driver
):
    from pangloss_cypher.migrations import apply_changes
    from pangloss_models.migrations import build_snapshot
    from pangloss_models.migrations import changes as c
    from pangloss_testing.live import run
    from pangloss_testing.under_test.database import current

    Person, Event, _ = models()
    await initialise_database()
    person = await Person.Create(label="Ada").save()
    ref = {"type": "Person", "id": person.id}
    dates = {
        "exact": exact(1500, 3),
        "open range": {
            "type": "JulianDateRange",
            "not_before": {"type": "JulianUnknownDate"},
            "not_after": exact(1502),
        },
        "period of a range": {
            "type": "JulianPeriod",
            "start": {
                "type": "JulianDateRange",
                "not_before": exact(1500),
                "not_after": exact(1501),
            },
            "end": {"type": "JulianOngoingDate"},
        },
    }
    for label, date in dates.items():
        await Event.Create(label=label, date=date, concerns=ref, identified=[]).save()
    expected = {item.label: item.date_text for item in (await Event.list()).results}
    assert expected["period of a range"] == "[1500–1501]–…"
    # (as a document of a class that was not dateable yet is stored)
    run(
        db_driver,
        "MATCH (n:Event) REMOVE n.date_sort_day, n.date_end_sort_day, n.date_text",
    )
    assert {i.date_text for i in (await Event.list()).results} == {None}

    await apply_changes(
        current(),
        build_snapshot(),
        [c.RunPython(function="pangloss_dates.dateable:fill_in_dateables")],
    )
    listed = (await Event.list()).results
    assert {item.label: item.date_text for item in listed} == expected
    assert all(item.date_sort_day for item in listed)
