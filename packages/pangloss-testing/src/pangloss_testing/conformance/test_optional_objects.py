"""A single relation or embedded object declared optional (`spouse: Person | None`, `born: Day | None`) may be left
out or given as `None`: it is stored as no edge and no node, and read back as `None`; an update can take it away or
give it again."""

from typing import no_type_check

import pytest
from pangloss_models import Document, Embedded, Entity, Match, initialise

from .helpers import run

pytestmark = pytest.mark.asyncio(loop_scope="session")


@no_type_check
def declare():
    class Day(Embedded):
        year: int

    class Person(Entity):
        spouse: "Person | None"
        born: Day | None

    class Place(Entity):
        pass

    class Note(Document):
        text: str
        about: Person | Place | None

    initialise()
    return Person, Place, Note


@no_type_check
async def test_left_out_is_no_edge_and_no_node_and_reads_back_as_none(
    db_driver, clear_database
):
    Person, _, Note = declare()

    alone = await Person.Create(label="Alone").save()
    note = await Note.Create(label="A note", text="t").save()

    assert run(db_driver, "MATCH (:Person)-[e]->() RETURN e") == []
    assert run(db_driver, "MATCH (n:Day) RETURN n") == []
    assert run(db_driver, "MATCH (:Note)-[e]->() RETURN e") == []

    read = await Person.get(alone.id)
    assert read.spouse is None and read.born is None
    assert (await Note.get(note.id)).about is None
    # (given as None, the same)
    explicit = await Person.Create(label="Also", spouse=None, born=None).save()
    assert (await Person.get(explicit.id)).spouse is None


@no_type_check
async def test_given_is_one_edge_or_node_and_reads_back_as_one(
    db_driver, clear_database
):
    Person, Place, Note = declare()

    jane = await Person.Create(label="Jane").save()
    john = await Person.Create(
        label="John",
        spouse={"type": "Person", "id": jane.id},
        born={"type": "Day", "year": 1500},
    ).save()
    place = await Place.Create(label="Vienna").save()
    note = await Note.Create(
        label="A note", text="t", about={"type": "Place", "id": place.id}
    ).save()

    read = await Person.get(john.id)
    assert read.spouse.id == jane.id
    assert read.born.year == 1500
    about = (await Note.get(note.id)).about
    assert about.type == "Place" and about.id == place.id
    # (one edge forward, one back)
    assert (
        len(
            run(
                db_driver,
                "MATCH (:Person {label: 'John'})-[e:spouse]->(:Person) RETURN e",
            )
        )
        == 1
    )


@no_type_check
async def test_an_update_takes_it_away_and_gives_it_again(db_driver, clear_database):
    Person, _, _ = declare()

    jane = await Person.Create(label="Jane").save()
    john = await Person.Create(
        label="John",
        spouse={"type": "Person", "id": jane.id},
        born={"type": "Day", "year": 1500},
    ).save()

    await Person.Update(id=john.id, label="John").save()
    read = await Person.get(john.id)
    assert read.spouse is None and read.born is None
    assert run(db_driver, "MATCH (n:Day) RETURN n") == []
    assert (
        run(db_driver, "MATCH (:Person {label: 'John'})-[e:spouse]->() RETURN e") == []
    )
    # (the entity that was the spouse is untouched)
    assert (await Person.get(jane.id)).label == "Jane"

    await Person.Update(
        id=john.id,
        label="John",
        spouse={"type": "Person", "id": jane.id},
        born={"type": "Day", "year": 1501},
    ).save()
    read = await Person.get(john.id)
    assert read.spouse.id == jane.id and read.born.year == 1501


@no_type_check
async def test_searched_by(clear_database):
    Person, _, _ = declare()

    jane = await Person.Create(label="Jane").save()
    await Person.Create(label="John", spouse={"type": "Person", "id": jane.id}).save()

    found = await Person.search(Match(where={"spouse": {"is": str(jane.id)}}))
    assert [item.label for item in found.results] == ["John"]


@no_type_check
async def test_an_optional_reified_relation_and_relation_with_an_edge_model(
    db_driver, clear_database
):
    from pangloss_models import EdgeModel, ReifiedRelation, ViaEdge

    class Certainty(EdgeModel):
        certainty: int

    class Person(Entity):
        pass

    class InRole[T](ReifiedRelation[T]):
        role: str

    class Act(Document):
        by: ViaEdge[Person, Certainty] | None
        in_role: InRole[Person] | None

    initialise()

    jane = await Person.Create(label="Jane").save()
    act = await Act.Create(
        label="An act",
        by={"type": "Person", "id": jane.id, "edge_properties": {"certainty": 2}},
        in_role={
            "type": "InRole",
            "role": "witness",
            "target": [{"type": "Person", "id": jane.id}],
        },
    ).save()
    read = await Act.get(act.id)
    assert read.by.id == jane.id and read.by.edge_properties.certainty == 2
    assert read.in_role.role == "witness" and read.in_role.target[0].id == jane.id

    await Act.Update(id=act.id, label="An act").save()
    read = await Act.get(act.id)
    assert read.by is None and read.in_role is None
    assert run(db_driver, "MATCH (n:InRole) RETURN n") == []
