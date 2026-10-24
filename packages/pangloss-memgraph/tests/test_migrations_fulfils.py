"""Which classes a node fulfils (`Fulfils`) is a matter of the labels it has: a migration that
changes what a model fulfils gives the nodes the labels that new writes give them"""

from types import SimpleNamespace as ns
from typing import Annotated, no_type_check

import pytest
from pangloss_models.field_definitions import FieldSubclassing
from pangloss_models.meta_kit.migrations import changes as c
from pangloss_models.meta_kit.migrations import diff
from pangloss_models.model_bases.configs import RelationConfig
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.helpers import Fulfils

from .helpers import run
from .migration_support import declare, migrate
from .test_migration_batch_equivalence import both_ways

pytestmark = pytest.mark.asyncio(loop_scope="session")


def models(fulfils: bool, venue: bool = False):
    """`Meeting` (and `Seminar`, a subclass) fulfils `Dated` when `fulfils`. A meeting has a place
    only through it; `Dated` also needs a venue, if `venue`."""

    def declare_models():
        class Person(Entity):
            pass

        class Place(Entity):
            pass

        if venue:

            class Dated(Document):
                who: Person
                place: Place
                venue: Place

        else:

            class Dated(Document):
                who: Person
                place: Place

        if fulfils:
            stands_in = Annotated[
                Person,
                RelationConfig(
                    subclasses_parent_fields=[
                        FieldSubclassing("who", field_on_model=Dated)
                    ]
                ),
            ]

            class Meeting(Document, Fulfils[Dated]):
                attendee: stands_in

        else:

            class Meeting(Document):
                attendee: Person
                place: Place

        class Seminar(Meeting):
            pass

        return ns(
            Person=Person, Place=Place, Dated=Dated, Meeting=Meeting, Seminar=Seminar
        )

    return declare_models


def labels(db_driver) -> dict[str, set[str]]:
    rows = run(
        db_driver, "MATCH (n:Meeting) RETURN n.label AS label, labels(n) AS labels"
    )
    return {row["label"]: set(row["labels"]) for row in rows}


async def write(
    made, person, place, label: str, with_place: bool, seminar: bool = False
):
    payload = {"label": label, "attendee": {"type": "Person", "id": person.id}}
    if with_place:
        payload["place"] = {"type": "Place", "id": place.id}
    return await (made.Seminar if seminar else made.Meeting).Create(**payload).save()


@no_type_check
async def test_fulfilment_is_in_the_snapshot_and_a_change_to_it_is_found(
    db_driver, clear_database
):
    _, plain = declare(models(fulfils=False))
    _, fulfilling = declare(models(fulfils=True))

    assert (
        "fulfils" not in plain["models"]["Meeting"]
    )  # (so a model that fulfils nothing is as it was)
    assert fulfilling["models"]["Meeting"]["fulfils"] == [
        {"class": "Dated", "fields": {"place": "place", "who": "attendee"}}
    ]
    assert (
        fulfilling["models"]["Seminar"]["fulfils"]
        == fulfilling["models"]["Meeting"]["fulfils"]
    )

    found = [
        ch
        for ch in diff(plain, fulfilling).changes
        if isinstance(ch, c.RecomputeFulfils)
    ]
    assert sorted(ch.model for ch in found) == ["Meeting", "Seminar"]
    meeting = next(ch for ch in found if ch.model == "Meeting")
    assert meeting.before == []
    assert meeting.after == [
        {
            "class": "Dated",
            "labels": ["Dated", "Document"],
            "needs": [{"edge": "attendee"}, {"edge": "place"}],
        }
    ]


@no_type_check
async def test_a_model_that_begins_to_fulfil_a_class_has_its_labels(
    db_driver, clear_database
):
    old_models, old = declare(models(fulfils=False))
    person = await old_models.Person.Create(label="P").save()
    place = await old_models.Place.Create(label="Pl").save()
    await write(old_models, person, place, "With", True)
    await write(old_models, person, place, "SeminarWith", True, seminar=True)
    # (a meeting that was written without a place: say, before it was needed)
    await write(old_models, person, place, "Without", True)
    run(db_driver, "MATCH (n:Meeting {label: 'Without'})-[e:place]->() DELETE e")
    run(
        db_driver, "MATCH ()-[e:place_reverse]->(n:Meeting {label: 'Without'}) DELETE e"
    )
    new_models, new = declare(models(fulfils=True))

    await migrate(old, new)

    found = labels(db_driver)
    assert "Dated" in found["With"] and "Dated" in found["SeminarWith"]
    assert "Dated" not in found["Without"]

    # ... the labels new writes give
    await write(new_models, person, place, "NativeWith", True)
    await write(new_models, person, place, "NativeWithout", False)
    found = labels(db_driver)
    assert found["With"] == found["NativeWith"]
    assert found["Without"] == found["NativeWithout"]


@no_type_check
async def test_a_model_that_stops_fulfilling_a_class_loses_its_labels(
    db_driver, clear_database
):
    old_models, old = declare(models(fulfils=True))
    person = await old_models.Person.Create(label="P").save()
    place = await old_models.Place.Create(label="Pl").save()
    await write(old_models, person, place, "With", True)
    await write(old_models, person, place, "SeminarWith", True, seminar=True)
    assert "Dated" in labels(db_driver)["With"]
    new_models, new = declare(models(fulfils=False))

    await migrate(old, new)

    found = labels(db_driver)
    assert "Dated" not in found["With"] and "Dated" not in found["SeminarWith"]
    assert {"Meeting", "Document", "HeadNode"} <= found["With"]  # (its own are kept)
    # ... the labels new writes give
    await write(new_models, person, place, "Native", True)
    assert found["With"] == labels(db_driver)["Native"]


@no_type_check
async def test_a_fulfilled_class_that_needs_more_takes_the_label_off_what_does_not_have_it(
    db_driver, clear_database
):
    old_models, old = declare(models(fulfils=True))
    person = await old_models.Person.Create(label="P").save()
    place = await old_models.Place.Create(label="Pl").save()
    await write(old_models, person, place, "With", True)
    assert "Dated" in labels(db_driver)["With"]
    new_models, new = declare(models(fulfils=True, venue=True))

    changes = await migrate(old, new)
    assert "RecomputeFulfils" in {ch.kind for ch in changes}
    # (`Dated` needs a venue now, and the meeting has none: it is not a `Dated` any more)
    assert "Dated" not in labels(db_driver)["With"]

    # ... as when it is written
    await write(new_models, person, place, "Native", True)
    assert labels(db_driver)["With"] == labels(db_driver)["Native"]


@no_type_check
async def test_fulfilment_is_the_same_in_batches_and_after_a_stop(
    db_driver, clear_database
):
    async def adding(batch):
        old_models, old = declare(models(fulfils=False))
        person = await old_models.Person.Create(label="P").save()
        place = await old_models.Place.Create(label="Pl").save()
        for n in range(6):
            await write(old_models, person, place, f"M{n}", True, seminar=n % 2 == 0)
        _, new = declare(models(fulfils=True))
        await migrate(old, new, batch_size=batch)

    graph = await both_ways(db_driver, adding)
    assert sum('"Dated"' in node for node in graph["nodes"]) == 6

    async def removing(batch):
        old_models, old = declare(models(fulfils=True))
        person = await old_models.Person.Create(label="P").save()
        place = await old_models.Place.Create(label="Pl").save()
        for n in range(6):
            await write(old_models, person, place, f"M{n}", True, seminar=n % 2 == 0)
        _, new = declare(models(fulfils=False))
        await migrate(old, new, batch_size=batch)

    graph = await both_ways(db_driver, removing)
    assert not any('"Dated"' in node for node in graph["nodes"])
