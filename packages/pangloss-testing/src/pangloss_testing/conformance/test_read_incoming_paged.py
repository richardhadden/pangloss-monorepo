"""What refers to an entity, some of it at a time: `get_entity_with_some` (the entity with the first few of each
incoming field, and how many there are), its two halves `get_entity_without_incoming` and `get_incoming_fields` (for
a page that reads the entity first and what refers to it apart), and `get_incoming` (a page of one field). For the
page of an entity that thousands of documents refer to, which `Entity.get` reads whole."""

import uuid
from typing import no_type_check

import pytest
from pangloss_core import storage_of
from pangloss_models import (
    Document,
    Entity,
    PanglossReferenceError,
    ReifiedRelation,
    initialise,
)
from pangloss_testing.under_test.initialise_database import (
    initialise_database,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


def models():
    class Person(Entity):
        pass

    class Scholar(Person):
        pass

    class Identification[T](ReifiedRelation[T]):
        pass

    class Statement(Document):
        concerns: Person

    class Event(Document):
        witnessed_by: list[Person]

    class Gift(Document):
        given_by: Identification[Person]

    initialise()
    return Person, Scholar, Statement, Event, Gift


async def referred_to(Person, Statement, Event, Gift, cls=None):
    """A person that seven statements concern (one of them deleted), three events were witnessed by, and two gifts
    were given by (through a reified relation)"""
    person = await (cls or Person).Create(label="Alcuin").save()
    ref = {"type": (cls or Person).__name__, "id": person.id}
    # (made out of order: they are read by label)
    for n in (4, 1, 6, 0, 3, 5, 2):
        made = await Statement.Create(label=f"Statement {n}", concerns=ref).save()
        if n == 6:
            await Statement.delete(made.id)
    for n in (2, 0, 1):
        await Event.Create(label=f"Event {n}", witnessed_by=[ref]).save()
    for n in (1, 0):
        await Gift.Create(
            label=f"Gift {n}", given_by={"type": "Identification", "target": [ref]}
        ).save()
    return person


@no_type_check
async def test_an_entity_is_read_with_some_of_what_refers_to_it_and_the_counts(
    clear_database,
):
    Person, Scholar, Statement, Event, Gift = models()
    await initialise_database()
    person = await referred_to(Person, Statement, Event, Gift)
    operations = storage_of().operations

    # all of it, as before (and by label)
    whole = await Person.get(person.id)
    assert [s.label for s in whole.concerns_reverse] == [
        f"Statement {n}" for n in range(6)
    ]
    assert len(whole.witnessed_by_reverse) == 3 and len(whole.given_by_reverse) == 2

    some, counts = await operations.get_entity_with_some(Person, person.id, 2)
    assert type(some) is Person.HeadView and some.label == "Alcuin"
    assert [s.label for s in some.concerns_reverse] == ["Statement 0", "Statement 1"]
    assert [e.label for e in some.witnessed_by_reverse] == ["Event 0", "Event 1"]
    assert [g.label for g in some.given_by_reverse] == ["Gift 0", "Gift 1"]
    # (the deleted statement is not counted)
    assert counts == {
        "concerns_reverse": 6,
        "witnessed_by_reverse": 3,
        "given_by_reverse": 2,
    }
    # a limit that nothing reaches gives everything
    everything, counts = await operations.get_entity_with_some(Person, person.id, 50)
    assert everything == whole and sum(counts.values()) == 11
    # no such entity
    assert await operations.get_entity_with_some(Person, uuid.uuid7(), 2) is None
    # one that nothing refers to has no counts
    alone = await Person.Create(label="Nobody").save()
    lonely, counts = await operations.get_entity_with_some(Person, alone.id, 2)
    assert lonely.concerns_reverse == [] and counts == {}


@no_type_check
async def test_an_entity_and_what_refers_to_it_are_read_apart(clear_database):
    Person, Scholar, Statement, Event, Gift = models()
    await initialise_database()
    person = await referred_to(Person, Statement, Event, Gift)
    operations = storage_of().operations

    # the entity alone: its own values, and nothing in its incoming fields
    alone = await operations.get_entity_without_incoming(Person, person.id)
    assert type(alone) is Person.HeadView and alone.label == "Alcuin"
    assert alone.concerns_reverse == [] and alone.witnessed_by_reverse == []
    assert alone.given_by_reverse == []
    assert await operations.get_entity_without_incoming(Person, uuid.uuid7()) is None

    # what refers to it, the first of each field, and the counts: the same as `get_entity_with_some` gives
    some, counts = await operations.get_entity_with_some(Person, person.id, 2)
    incoming = await operations.get_incoming_fields(Person, person.id, 2)
    assert incoming.model is Person
    assert (
        incoming.counts
        == counts
        == {
            "concerns_reverse": 6,
            "witnessed_by_reverse": 3,
            "given_by_reverse": 2,
        }
    )
    assert set(incoming.fields) == set(counts)
    assert incoming.fields["concerns_reverse"] == some.concerns_reverse
    assert incoming.fields["witnessed_by_reverse"] == some.witnessed_by_reverse
    assert incoming.fields["given_by_reverse"] == some.given_by_reverse
    assert incoming.fields["given_by_reverse"][0].given_by.target[0].id == person.id
    assert await operations.get_incoming_fields(Person, uuid.uuid7(), 2) is None
    # one that nothing refers to: no fields, no counts
    nobody = await Person.Create(label="Nobody").save()
    empty = await operations.get_incoming_fields(Person, nobody.id, 2)
    assert empty.fields == {} and empty.counts == {}
    # of a subclass: as the subclass
    scholar = await referred_to(Person, Statement, Event, Gift, cls=Scholar)
    assert (
        type(await operations.get_entity_without_incoming(Person, scholar.id))
        is Scholar.HeadView
    )
    assert (
        await operations.get_incoming_fields(Person, scholar.id, 1)
    ).model is Scholar


@no_type_check
async def test_one_relation_to_an_entity_is_read_a_page_at_a_time(clear_database):
    Person, Scholar, Statement, Event, Gift = models()
    await initialise_database()
    person = await referred_to(Person, Statement, Event, Gift)
    operations = storage_of().operations

    page = await operations.get_incoming(
        Person, person.id, "concerns_reverse", skip=0, limit=4
    )
    assert (page.model, page.field, page.count) == (Person, "concerns_reverse", 6)
    assert [s.label for s in page.items] == [f"Statement {n}" for n in range(4)]
    # (as they are in the view of the entity)
    whole = await Person.get(person.id)
    assert page.items == whole.concerns_reverse[:4]
    rest = await operations.get_incoming(
        Person, person.id, "concerns_reverse", skip=4, limit=4
    )
    assert [s.label for s in rest.items] == ["Statement 4", "Statement 5"]
    # past the end: nothing, and still how many there are
    beyond = await operations.get_incoming(
        Person, person.id, "concerns_reverse", skip=8, limit=4
    )
    assert beyond.items == [] and beyond.count == 6

    # through a reified relation: the document with the relation in its field, as in the view; the field by the
    # name JSON has for it
    gifts = await operations.get_incoming(Person, person.id, "givenByReverse")
    assert gifts.field == "given_by_reverse" and gifts.count == 2
    assert [g.label for g in gifts.items] == ["Gift 0", "Gift 1"]
    assert gifts.items == whole.given_by_reverse
    assert gifts.items[0].given_by.target[0].id == person.id

    # a field the class does not have, and an entity that is not there
    with pytest.raises(PanglossReferenceError, match="called concerns"):
        await operations.get_incoming(Person, person.id, "concerns")
    assert (
        await operations.get_incoming(Person, uuid.uuid7(), "concerns_reverse") is None
    )
    # nothing refers by it: an empty page
    alone = await Person.Create(label="Nobody").save()
    empty = await operations.get_incoming(Person, alone.id, "concerns_reverse")
    assert empty.items == [] and empty.count == 0


@no_type_check
async def test_an_entity_of_a_subclass_is_read_as_the_subclass(clear_database):
    Person, Scholar, Statement, Event, Gift = models()
    await initialise_database()
    scholar = await referred_to(Person, Statement, Event, Gift, cls=Scholar)
    operations = storage_of().operations

    some, counts = await operations.get_entity_with_some(Person, scholar.id, 1)
    assert type(some) is Scholar.HeadView
    assert [s.label for s in some.concerns_reverse] == ["Statement 0"]
    assert counts["concerns_reverse"] == 6
    page = await operations.get_incoming(Person, scholar.id, "witnessed_by_reverse")
    assert page.model is Scholar and [e.label for e in page.items] == [
        "Event 0",
        "Event 1",
        "Event 2",
    ]


async def test_the_incoming_query_is_the_same_text_for_every_entity_and_page():
    """(the database finds its plan again by the text of the query)"""
    from pangloss_cypher.read_incoming import shown_relations
    from pangloss_cypher.read_query import build_fetch_incoming_query

    Person, *_ = models()
    allowed = shown_relations(Person)
    assert allowed == [
        "concerns_reverse|Statement|0",
        "given_by_reverse|Gift|1",
        "witnessed_by_reverse|Event|0",
    ]
    whole, _ = build_fetch_incoming_query(Person, uuid.uuid7(), allowed)
    again, _ = build_fetch_incoming_query(Person, uuid.uuid7(), allowed)
    assert whole == again
    first, first_params = build_fetch_incoming_query(
        Person, uuid.uuid7(), allowed, field="concerns_reverse", skip=0, limit=25
    )
    second, second_params = build_fetch_incoming_query(
        Person, uuid.uuid7(), allowed, field="given_by_reverse", skip=50, limit=10
    )
    assert first == second and first != whole
    assert (first_params["skip"], second_params["skip"]) == (0, 50)
