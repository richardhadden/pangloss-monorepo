"""Reading an entity: its own values, `meta`, and the documents (and entities) that
refer to it, in a field for each reverse relation."""

import datetime
from typing import Annotated, no_type_check
from uuid import uuid7

import pytest
from pangloss_models import initialise
from pangloss_models.field_definitions import FieldSubclassing
from pangloss_models.model_bases.configs import RelationConfig
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.embedded import Embedded
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.reified_relation import (
    ReifiedRelation,
    ReifiedRelationDocument,
)
from pangloss_models.model_bases.semantic_space import SemanticSpace
from pydantic import AnyHttpUrl

from .helpers import run

pytestmark = pytest.mark.asyncio(loop_scope="session")


@no_type_check
async def test_entity_own_values_and_meta(clear_database):
    class Person(Entity):
        born: int | None
        nickname: str | None

    initialise()

    saved = await Person.Create(label="John Smith", born=1900, nickname=None).save()

    read = await Person.get(id=saved.id)
    assert isinstance(read, Person.HeadView)
    assert read.id == saved.id
    assert read.type == "Person"
    assert read.label == "John Smith"
    assert read.born == 1900
    assert read.nickname is None
    assert read.meta.created_by == "pangloss_default_user"
    assert read.meta.created_when is not None
    assert read.meta.updated_by is None
    assert read.meta.head_node_type == "Person"
    assert read.meta.head_node_id == saved.id


@no_type_check
async def test_missing_entity_is_none(clear_database):
    class Person(Entity):
        pass

    initialise()

    assert await Person.get(id=uuid7()) is None


@no_type_check
async def test_entity_of_a_different_type_is_none(clear_database):
    class Person(Entity):
        pass

    class Place(Entity):
        pass

    initialise()

    place = await Place.Create(label="A Place").save()
    assert await Person.get(id=place.id) is None


@no_type_check
async def test_entity_with_no_incoming_relations(clear_database):
    class Person(Entity):
        pass

    class Statement(Document):
        concerns_person: Person

    initialise()

    saved = await Person.Create(label="John Smith").save()

    read = await Person.get(id=saved.id)
    assert read.concerns_person_reverse == []


@no_type_check
async def test_entity_by_url(clear_database):
    class Person(Entity):
        _meta = Entity.Meta(create_with_id=True)

    initialise()

    url = "http://example.com/people/john-smith"
    saved = await Person.Create(id=AnyHttpUrl(url), create_new=True, label="JS").save()

    read = await Person.get(id=AnyHttpUrl(url))
    assert read.id == saved.id
    assert await Person.get(id=AnyHttpUrl("http://example.com/nobody")) is None


@no_type_check
async def test_entity_own_relations_are_read_as_well(clear_database):
    class Place(Entity):
        pass

    class Person(Entity):
        lives_in: list[Place]

    initialise()

    place = await Place.Create(label="Vienna").save()
    saved = await Person.Create(
        label="John Smith", lives_in=[{"type": "Place", "id": place.id}]
    ).save()

    read = await Person.get(id=saved.id)
    assert [p.id for p in read.lives_in] == [place.id]
    assert [p.label for p in read.lives_in] == ["Vienna"]

    # ... and the place, from the other side
    read_place = await Place.get(id=place.id)
    assert [p.id for p in read_place.lives_in_reverse] == [saved.id]
    assert read_place.lives_in_reverse[0].type == "Person"
    assert read_place.lives_in_reverse[0].label == "John Smith"


# ---------------------------------------------------------------------------
# Relations from documents
# ---------------------------------------------------------------------------


@no_type_check
async def test_incoming_relation_from_documents(clear_database):
    class Person(Entity):
        pass

    class Statement(Document):
        concerns_person: Person

    class Order(Document):
        given_by: Person

    initialise()

    person = await Person.Create(label="John Smith").save()
    reference = {"type": "Person", "id": person.id}
    first = await Statement.Create(label="First", concerns_person=reference).save()
    second = await Statement.Create(label="Second", concerns_person=reference).save()
    order = await Order.Create(label="An Order", given_by=reference).save()

    read = await Person.get(id=person.id)

    assert {s.id for s in read.concerns_person_reverse} == {first.id, second.id}
    for item in read.concerns_person_reverse:
        assert isinstance(item, Statement.ReferenceView)
        assert item.type == "Statement"
        assert item.label in ("First", "Second")
        assert item.meta.is_head_node is True
        assert item.meta.head_node_id == item.id
        assert item.meta.created_by == "pangloss_default_user"
        assert item.meta.created_when is not None

    assert [o.id for o in read.given_by_reverse] == [order.id]
    assert read.given_by_reverse[0].label == "An Order"


@no_type_check
async def test_incoming_relation_from_nested_document(clear_database):
    class Person(Entity):
        pass

    class Action(Document):
        carried_out_by: Person

    class Statement(Document):
        action: Action

    initialise()

    person = await Person.Create(label="John Smith").save()
    statement = await Statement.Create(
        label="A Statement",
        action={
            "type": "Action",
            "label": "An Action",
            "carried_out_by": {"type": "Person", "id": person.id},
        },
    ).save()

    read = await Person.get(id=person.id)

    assert len(read.carried_out_by_reverse) == 1
    item = read.carried_out_by_reverse[0]
    assert isinstance(item, Action.ReferenceView)
    assert item.label == "An Action"
    assert item.meta.is_head_node is False
    assert item.meta.head_node_id == statement.id
    assert item.meta.head_node_type == "Statement"
    assert item.meta.created_by == "pangloss_default_user"


@no_type_check
async def test_incoming_relation_with_custom_reverse_name(clear_database):
    class Person(Entity):
        pass

    class Statement(Document):
        concerns_person: Annotated[
            Person, RelationConfig(reverse_name="is concerned in")
        ]

    initialise()

    person = await Person.Create(label="John Smith").save()
    statement = await Statement.Create(
        label="A Statement", concerns_person={"type": "Person", "id": person.id}
    ).save()

    read = await Person.get(id=person.id)
    assert [s.id for s in read.is_concerned_in] == [statement.id]


@no_type_check
async def test_incoming_relation_from_document_in_a_semantic_space(clear_database):
    class Negative[T](SemanticSpace[T]):
        pass

    class Person(Entity):
        pass

    class Statement(Document):
        concerns_person: Person

    class Factoid(Document):
        statements: list[Negative[Statement]]

    initialise()

    person = await Person.Create(label="John Smith").save()
    await Factoid.Create(
        label="A Factoid",
        statements=[
            {
                "type": "Negative",
                "contents": [
                    {
                        "type": "Statement",
                        "label": "Not true",
                        "concerns_person": {"type": "Person", "id": person.id},
                    }
                ],
            }
        ],
    ).save()

    read = await Person.get(id=person.id)
    assert [s.label for s in read.concerns_person_reverse] == ["Not true"]
    assert read.concerns_person_reverse[0].meta.semantic_spaces == ["Negative"]


@no_type_check
async def test_incoming_relations_follow_updates(clear_database):
    class Person(Entity):
        pass

    class Statement(Document):
        concerns_person: list[Person]

    initialise()

    person = await Person.Create(label="John Smith").save()
    saved = await Statement.Create(
        label="A Statement",
        concerns_person=[{"type": "Person", "id": person.id}],
    ).save()
    assert len((await Person.get(id=person.id)).concerns_person_reverse) == 1

    await Statement.Update(id=saved.id, label="A Statement", concerns_person=[]).save()
    assert (await Person.get(id=person.id)).concerns_person_reverse == []

    await Statement.Update(
        id=saved.id,
        label="Edited",
        concerns_person=[{"type": "Person", "id": person.id}],
    ).save()
    read = await Person.get(id=person.id)
    assert [s.label for s in read.concerns_person_reverse] == ["Edited"]
    assert read.concerns_person_reverse[0].meta.updated_by == "pangloss_default_user"


@no_type_check
async def test_updating_an_entity_keeps_its_incoming_relations(clear_database):
    class Person(Entity):
        pass

    class Statement(Document):
        concerns_person: Person

    initialise()

    person = await Person.Create(label="John Smith").save()
    await Statement.Create(
        label="A Statement", concerns_person={"type": "Person", "id": person.id}
    ).save()

    await Person.Update(id=person.id, label="John Smith, edited").save()

    read = await Person.get(id=person.id)
    assert read.label == "John Smith, edited"
    assert read.meta.updated_by == "pangloss_default_user"
    assert [s.label for s in read.concerns_person_reverse] == ["A Statement"]


# ---------------------------------------------------------------------------
# Subclassed relations
# ---------------------------------------------------------------------------


@no_type_check
async def test_subclassed_relation_appears_only_under_the_most_specific_name(
    db_driver, clear_database
):
    """A relation that a subclass narrows ("is entity involved in" to "is person
    involved in") is stored under both names, but is only shown under the narrower"""

    class Person(Entity):
        pass

    class Statement(Document):
        concerns_person: Person

    class Action(Statement):
        carried_out_by: Annotated[
            Person,
            RelationConfig(
                subclasses_parent_fields=[
                    FieldSubclassing(
                        field_name="concerns_person", field_on_model=Statement
                    )
                ]
            ),
        ]

    initialise()

    person = await Person.Create(label="John Smith").save()
    reference = {"type": "Person", "id": person.id}
    plain = await Statement.Create(label="Plain", concerns_person=reference).save()
    action = await Action.Create(label="An Action", carried_out_by=reference).save()

    # Both names are stored in the graph...
    stored = run(
        db_driver,
        "MATCH (:Person)-[r {reverse: true}]->(:Action) RETURN type(r) AS type ORDER BY type",
    )
    assert [row["type"] for row in stored] == [
        "carried_out_by_reverse",
        "concerns_person_reverse",
    ]

    # ... but it is only shown under the most specific
    read = await Person.get(id=person.id)

    assert [s.id for s in read.concerns_person_reverse] == [plain.id]
    assert [a.id for a in read.carried_out_by_reverse] == [action.id]
    assert read.carried_out_by_reverse[0].type == "Action"


# ---------------------------------------------------------------------------
# Embedded objects
# ---------------------------------------------------------------------------


@no_type_check
async def test_incoming_relation_through_embedded_objects_points_to_the_document(
    clear_database,
):
    class Person(Entity):
        pass

    class DateSpecific(Embedded):
        note: str
        about: Person

    class Date(Embedded):
        when: datetime.date
        specific: DateSpecific

    class Statement(Document):
        date: Date

    initialise()

    person = await Person.Create(label="John Smith").save()
    statement = await Statement.Create(
        label="A Statement",
        date={
            "type": "Date",
            "when": "2020-01-01",
            "specific": {
                "type": "DateSpecific",
                "note": "a note",
                "about": {"type": "Person", "id": person.id},
            },
        },
    ).save()

    read = await Person.get(id=person.id)

    # Not the embedded objects: the document that the chain of them starts from
    assert len(read.about_reverse) == 1
    item = read.about_reverse[0]
    assert isinstance(item, Statement.ReferenceView)
    assert item.id == statement.id
    assert item.label == "A Statement"
    assert item.type == "Statement"
    assert item.meta.is_head_node is True


@no_type_check
async def test_incoming_relation_through_embedded_object_in_a_nested_document(
    clear_database,
):
    class Person(Entity):
        pass

    class Date(Embedded):
        about: Person

    class Action(Document):
        date: Date

    class Statement(Document):
        action: Action

    initialise()

    person = await Person.Create(label="John Smith").save()
    statement = await Statement.Create(
        label="A Statement",
        action={
            "type": "Action",
            "label": "An Action",
            "date": {"type": "Date", "about": {"type": "Person", "id": person.id}},
        },
    ).save()

    read = await Person.get(id=person.id)
    # The immediate document: the nested Action, not the Statement it is part of
    assert [a.label for a in read.about_reverse] == ["An Action"]
    assert read.about_reverse[0].type == "Action"
    assert read.about_reverse[0].meta.head_node_id == statement.id


# ---------------------------------------------------------------------------
# Reified relations
# ---------------------------------------------------------------------------


@no_type_check
async def test_incoming_relation_through_a_reified_relation(clear_database):
    class Person(Entity):
        pass

    class Identification[T](ReifiedRelation[T]):
        certainty: int

    class Statement(Document):
        text: str
        concerns_person: Person
        involves_person: Identification[Person]

    initialise()

    person = await Person.Create(label="John Smith").save()
    other = await Person.Create(label="Jane Doe").save()
    statement = await Statement.Create(
        label="A Statement",
        text="some text",
        concerns_person={"type": "Person", "id": other.id},
        involves_person={
            "type": "Identification",
            "certainty": 3,
            "target": [
                {"type": "Person", "id": person.id},
                {"type": "Person", "id": other.id},
            ],
        },
    ).save()

    read = await Person.get(id=person.id)

    assert read.concerns_person_reverse == []
    assert len(read.involves_person_reverse) == 1
    item = read.involves_person_reverse[0]

    # The linked document, with only the fields of this chain
    assert item.id == statement.id
    assert item.type == "Statement"
    assert not hasattr(item, "text")
    assert not hasattr(item, "concerns_person")

    # The reified relation, with its own values, and its targets
    assert item.involves_person.certainty == 3
    assert {t.id for t in item.involves_person.target} == {person.id, other.id}
    assert {t.label for t in item.involves_person.target} == {
        "John Smith",
        "Jane Doe",
    }

    # Seen from the other person, the same relation is there as well, with the
    # direct relation (which is hers alone) in its own field
    read_other = await Person.get(id=other.id)
    assert len(read_other.involves_person_reverse) == 1
    assert [s.id for s in read_other.concerns_person_reverse] == [statement.id]


@no_type_check
async def test_incoming_relations_through_several_reified_relations(clear_database):
    class Person(Entity):
        pass

    class Identification[T](ReifiedRelation[T]):
        certainty: int

    class Statement(Document):
        involves_people: list[Identification[Person]]

    initialise()

    person = await Person.Create(label="John Smith").save()
    reference = {"type": "Person", "id": person.id}
    await Statement.Create(
        label="A Statement",
        involves_people=[
            {"type": "Identification", "certainty": c, "target": [reference]}
            for c in (1, 2)
        ],
    ).save()

    read = await Person.get(id=person.id)

    # One entry for each reified relation, each with its own (one-item) list
    assert len(read.involves_people_reverse) == 2
    for item in read.involves_people_reverse:
        assert len(item.involves_people) == 1
    assert sorted(i.involves_people[0].certainty for i in read.involves_people_reverse) == [
        1,
        2,
    ]


@no_type_check
async def test_incoming_relation_through_a_chain_of_reified_relations(clear_database):
    class Person(Entity):
        pass

    class Identification[T](ReifiedRelation[T]):
        certainty: int

    class Statement(Document):
        involves: Identification[Identification[Person]]

    initialise()

    person = await Person.Create(label="John Smith").save()
    other = await Person.Create(label="Jane Doe").save()
    third = await Person.Create(label="Third Person").save()
    statement = await Statement.Create(
        label="A Statement",
        involves={
            "type": "Identification",
            "certainty": 1,
            "target": [
                {
                    "type": "Identification",
                    "certainty": 2,
                    "target": [
                        {"type": "Person", "id": person.id},
                        {"type": "Person", "id": other.id},
                    ],
                },
            ],
        },
    ).save()
    assert third.id and statement.id

    read = await Person.get(id=person.id)

    assert len(read.involves_reverse) == 1
    item = read.involves_reverse[0]
    assert item.id == statement.id

    # Outermost first, each with the next in the chain as its target, and, at the
    # end, all targets of the last reified relation
    outer = item.involves
    assert outer.certainty == 1
    assert len(outer.target) == 1
    inner = outer.target[0]
    assert inner.certainty == 2
    assert {t.id for t in inner.target} == {person.id, other.id}


@no_type_check
async def test_incoming_relation_through_a_reified_relation_in_embedded_objects(
    clear_database,
):
    class Person(Entity):
        pass

    class Identification[T](ReifiedRelation[T]):
        certainty: int

    class DateSpecific(Embedded):
        involves_person: Identification[Person]

    class Date(Embedded):
        specific: DateSpecific

    class Statement(Document):
        text: str
        date: Date

    initialise()

    person = await Person.Create(label="John Smith").save()
    statement = await Statement.Create(
        label="A Statement",
        text="text",
        date={
            "type": "Date",
            "specific": {
                "type": "DateSpecific",
                "involves_person": {
                    "type": "Identification",
                    "certainty": 4,
                    "target": [{"type": "Person", "id": person.id}],
                },
            },
        },
    ).save()

    read = await Person.get(id=person.id)

    assert len(read.involves_person_reverse) == 1
    item = read.involves_person_reverse[0]
    assert item.id == statement.id
    assert not hasattr(item, "text")
    assert item.involves_person.certainty == 4
    assert [t.id for t in item.involves_person.target] == [person.id]


@no_type_check
async def test_incoming_relation_through_a_reified_relation_document(clear_database):
    class Person(Entity):
        pass

    class Role[T](ReifiedRelationDocument[T]):
        since: datetime.date

    class Statement(Document):
        role: Role[Person]

    initialise()

    person = await Person.Create(label="John Smith").save()
    statement = await Statement.Create(
        label="A Statement",
        role={
            "type": "Role",
            "label": "A Role",
            "since": "2000-01-01",
            "target": [{"type": "Person", "id": person.id}],
        },
    ).save()

    read = await Person.get(id=person.id)

    assert len(read.role_reverse) == 1
    item = read.role_reverse[0]
    assert item.id == statement.id
    assert item.role.since == datetime.date(2000, 1, 1)
    assert [t.id for t in item.role.target] == [person.id]


@no_type_check
async def test_incoming_relation_through_reified_relation_in_nested_document(
    clear_database,
):
    class Person(Entity):
        pass

    class Identification[T](ReifiedRelation[T]):
        certainty: int

    class Action(Document):
        involves_person: Identification[Person]

    class Statement(Document):
        action: Action

    initialise()

    person = await Person.Create(label="John Smith").save()
    await Statement.Create(
        label="A Statement",
        action={
            "type": "Action",
            "label": "An Action",
            "involves_person": {
                "type": "Identification",
                "certainty": 1,
                "target": [{"type": "Person", "id": person.id}],
            },
        },
    ).save()

    read = await Person.get(id=person.id)
    assert len(read.involves_person_reverse) == 1
    item = read.involves_person_reverse[0]
    # The immediate (nested) document holding the relation
    assert item.type == "Action"
    assert item.involves_person.certainty == 1


@no_type_check
async def test_incoming_relations_of_different_kinds_together(clear_database):
    class Person(Entity):
        pass

    class Identification[T](ReifiedRelation[T]):
        certainty: int

    class Date(Embedded):
        about: Person

    class Statement(Document):
        direct: Person
        date: Date
        involves_person: Identification[Person]

    initialise()

    person = await Person.Create(label="John Smith").save()
    reference = {"type": "Person", "id": person.id}
    statement = await Statement.Create(
        label="A Statement",
        direct=reference,
        date={"type": "Date", "about": reference},
        involves_person={
            "type": "Identification",
            "certainty": 1,
            "target": [reference],
        },
    ).save()

    read = await Person.get(id=person.id)
    assert [s.id for s in read.direct_reverse] == [statement.id]
    assert [s.id for s in read.about_reverse] == [statement.id]
    assert [s.id for s in read.involves_person_reverse] == [statement.id]
    assert read.involves_person_reverse[0].involves_person.certainty == 1
