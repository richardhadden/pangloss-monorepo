import datetime
from typing import no_type_check

import pytest
from pangloss_models import initialise
from pangloss_models.model_bases.annotated_value import AnnotatedValue
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.embedded import Embedded
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.reified_relation import (
    ReifiedRelation,
    ReifiedRelationDocument,
)
from pangloss_models.model_bases.semantic_space import SemanticSpace

pytestmark = pytest.mark.asyncio(loop_scope="session")


@no_type_check
async def test_read_nested_object(clear_database):
    class Negative[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Statement | Negative[Statement]]

    class Statement(Document):
        _meta = Document.Meta(abstract=True)

    class Order(Statement):
        order_given_by: Person
        order_received_by: Person
        thing_ordered: list[Action]

    class Action(Statement):
        action_carried_out_by: Person

    class Person(Entity):
        pass

    initialise()

    js = Person.Create(label="John Smith")
    js = await js.save()
    assert js.id

    km = Person.Create(label="Kaiser Maximilian")
    km = await km.save()
    assert km.id

    factoid = Factoid.Create(
        label="A Factoid",
        statements=[
            {
                "type": "Negative",
                "contents": [
                    {
                        "type": "Order",
                        "label": "KM orders JS to take an action",
                        "order_given_by": {"type": "Person", "id": km.id},
                        "order_received_by": {"type": "Person", "id": js.id},
                        "thing_ordered": [
                            {
                                "type": "Action",
                                "label": "JS carries out an action",
                                "action_carried_out_by": {
                                    "type": "Person",
                                    "id": js.id,
                                },
                            }
                        ],
                    }
                ],
            }
        ],
    )

    factoid_ref = await factoid.save(return_type="Full")
    assert isinstance(factoid_ref, Factoid.HeadView)
    assert factoid_ref.id

    assert factoid_ref.statements[0].contents[0].type == "Order"

    order_id = factoid_ref.statements[0].contents[0].id

    order_from_db = await Order.get(id=str(order_id))

    assert order_from_db.meta.head_node_type == "Factoid"
    assert order_from_db.meta.head_node_id == factoid_ref.id

    assert order_from_db.meta.created_by == "pangloss_default_user"
    assert order_from_db.meta.semantic_spaces == ["Negative"]
    assert order_from_db.meta.context_labels == [
        {
            "type": "Negative",
            "contents": [{"id": str(order_from_db.id), "type": "Order"}],
        }
    ]
    assert order_from_db.order_given_by.id == km.id
    assert order_from_db.order_given_by.label == "Kaiser Maximilian"
    assert order_from_db.order_received_by.id == js.id
    assert order_from_db.order_received_by.label == "John Smith"

    thing_ordered = order_from_db.thing_ordered[0]
    assert thing_ordered

    assert thing_ordered.type == "Action"

    assert thing_ordered.meta.semantic_spaces == ["Negative"]
    assert thing_ordered.meta.context_labels == [
        {
            "type": "Negative",
            "contents": [
                {"id": str(order_from_db.id), "type": "Order"},
                {"id": str(thing_ordered.id), "type": "Action"},
            ],
        }
    ]

    assert thing_ordered.action_carried_out_by.id == js.id


@no_type_check
async def test_read_nested_document_without_entities(clear_database):
    class Action(Document):
        detail: str

    class Statement(Document):
        action: Action
        actions: list[Action]

    initialise()

    saved = await Statement.Create(
        label="A Statement",
        action={"type": "Action", "label": "One", "detail": "one"},
        actions=[{"type": "Action", "label": "Two", "detail": "two"}],
    ).save()

    read = await Statement.get(id=saved.id)
    assert read.action.detail == "one"
    assert [a.detail for a in read.actions] == ["two"]


@no_type_check
async def test_read_deeply_nested_documents_without_entities(clear_database):
    class Leaf(Document):
        value: str

    class Branch(Document):
        leaves: list[Leaf]

    class Root(Document):
        branch: Branch

    initialise()

    saved = await Root.Create(
        label="Root",
        branch={
            "type": "Branch",
            "label": "Branch",
            "leaves": [
                {"type": "Leaf", "label": "One", "value": "1"},
                {"type": "Leaf", "label": "Two", "value": "2"},
            ],
        },
    ).save()

    read = await Root.get(id=saved.id)
    assert read.branch.label == "Branch"
    assert sorted(leaf.value for leaf in read.branch.leaves) == ["1", "2"]


@no_type_check
async def test_read_nested_documents_with_entities_at_every_level(clear_database):
    class Person(Entity):
        pass

    class Action(Document):
        carried_out_by: list[Person]

    class Order(Document):
        given_by: Person
        actions: list[Action]
        single_action: Action

    initialise()

    first = await Person.Create(label="First").save()
    second = await Person.Create(label="Second").save()

    saved = await Order.Create(
        label="An Order",
        given_by={"type": "Person", "id": first.id},
        single_action={
            "type": "Action",
            "label": "Single",
            "carried_out_by": [{"type": "Person", "id": second.id}],
        },
        actions=[
            {
                "type": "Action",
                "label": "Many",
                "carried_out_by": [
                    {"type": "Person", "id": first.id},
                    {"type": "Person", "id": second.id},
                ],
            },
            {"type": "Action", "label": "None", "carried_out_by": []},
        ],
    ).save()

    read = await Order.get(id=saved.id)
    assert read.given_by.id == first.id
    assert [p.id for p in read.single_action.carried_out_by] == [second.id]
    actions = {a.label: a for a in read.actions}
    assert set(actions) == {"Many", "None"}
    assert {p.id for p in actions["Many"].carried_out_by} == {first.id, second.id}
    assert actions["None"].carried_out_by == []


@no_type_check
async def test_read_does_not_follow_entities_into_their_own_relations(
    clear_database,
):
    class Place(Entity):
        pass

    class Person(Entity):
        lives_in: list[Place]

    class Statement(Document):
        concerns_person: Person

    initialise()

    place = await Place.Create(label="A Place").save()
    person = await Person.Create(
        label="John Smith", lives_in=[{"type": "Place", "id": place.id}]
    ).save()
    saved = await Statement.Create(
        label="A Statement", concerns_person={"type": "Person", "id": person.id}
    ).save()

    read = await Statement.get(id=saved.id)
    assert read.concerns_person.id == person.id
    # The entity is a reference; its relations are not part of this document
    assert not hasattr(read.concerns_person, "lives_in")


@no_type_check
async def test_read_returns_none_for_a_missing_document(clear_database):
    class Statement(Document):
        pass

    initialise()

    from uuid import uuid7

    assert await Statement.get(id=uuid7()) is None


@no_type_check
async def test_read_semantic_spaces_and_conjunctions_with_documents_only(
    clear_database,
):
    class Negative[T](SemanticSpace[T]):
        pass

    class Statement(Document):
        text: str

    class Factoid(Document):
        statements: list[Statement | Negative[Statement]]

    initialise()

    saved = await Factoid.Create(
        label="A Factoid",
        statements=[
            {"type": "Statement", "label": "Plain", "text": "plain"},
            {
                "type": "Negative",
                "contents": [{"type": "Statement", "label": "Negated", "text": "no"}],
            },
        ],
    ).save()

    read = await Factoid.get(id=saved.id)
    by_type = {s.type: s for s in read.statements}
    assert by_type["Statement"].text == "plain"
    assert by_type["Negative"].contents[0].text == "no"


# ---------------------------------------------------------------------------
# Embedded objects, reified relations, annotated values
# ---------------------------------------------------------------------------


@no_type_check
async def test_read_embedded_object(clear_database):
    class Date(Embedded):
        when: datetime.date
        note: str

    class Statement(Document):
        date: Date

    initialise()

    saved = await Statement.Create(
        label="A Statement",
        date={"type": "Date", "when": "2020-01-02", "note": "a note"},
    ).save()

    read = await Statement.get(id=saved.id)
    assert read.date.type == "Date"
    assert read.date.when == datetime.date(2020, 1, 2)
    assert read.date.note == "a note"


@no_type_check
async def test_read_union_of_embedded_objects(clear_database):
    class Date(Embedded):
        when: datetime.date

    class DateRange(Embedded):
        start: datetime.date
        end: datetime.date

    class Statement(Document):
        date: Date | DateRange

    initialise()

    saved = await Statement.Create(
        label="A Statement",
        date={"type": "DateRange", "start": "2020-01-01", "end": "2020-12-31"},
    ).save()

    read = await Statement.get(id=saved.id)
    assert read.date.type == "DateRange"
    assert read.date.end == datetime.date(2020, 12, 31)


@no_type_check
async def test_read_embedded_object_in_nested_document(clear_database):
    class Date(Embedded):
        when: datetime.date

    class Person(Entity):
        pass

    class Action(Document):
        date: Date
        carried_out_by: Person

    class Statement(Document):
        action: Action

    initialise()

    person = await Person.Create(label="John Smith").save()
    saved = await Statement.Create(
        label="A Statement",
        action={
            "type": "Action",
            "label": "An Action",
            "date": {"type": "Date", "when": "2020-01-02"},
            "carried_out_by": {"type": "Person", "id": person.id},
        },
    ).save()

    read = await Statement.get(id=saved.id)
    assert read.action.date.when == datetime.date(2020, 1, 2)
    assert read.action.carried_out_by.id == person.id


@no_type_check
async def test_read_reified_relation_to_entities(clear_database):
    class Person(Entity):
        pass

    class Identification[T](ReifiedRelation[T]):
        certainty: int

    class Statement(Document):
        identified: Identification[Person]

    initialise()

    first = await Person.Create(label="First").save()
    second = await Person.Create(label="Second").save()
    saved = await Statement.Create(
        label="A Statement",
        identified={
            "type": "Identification",
            "certainty": 2,
            "target": [
                {"type": "Person", "id": first.id},
                {"type": "Person", "id": second.id},
            ],
        },
    ).save()

    read = await Statement.get(id=saved.id)
    assert read.identified.type == "Identification"
    assert read.identified.certainty == 2
    assert {p.id for p in read.identified.target} == {first.id, second.id}


@no_type_check
async def test_read_reified_relation_to_documents(clear_database):
    class Place(Document):
        name: str

    class Located[T](ReifiedRelation[T]):
        certainty: int

    class Statement(Document):
        located: Located[Place]

    initialise()

    saved = await Statement.Create(
        label="A Statement",
        located={
            "type": "Located",
            "certainty": 3,
            "target": [{"type": "Place", "label": "A Place", "name": "Vienna"}],
        },
    ).save()

    read = await Statement.get(id=saved.id)
    assert read.located.certainty == 3
    assert read.located.target[0].name == "Vienna"


@no_type_check
async def test_read_reified_relations_in_a_list_and_nested(clear_database):
    class Person(Entity):
        pass

    class Identification[T](ReifiedRelation[T]):
        certainty: int

    class Action(Document):
        identified: list[Identification[Person]]

    class Statement(Document):
        action: Action

    initialise()

    person = await Person.Create(label="John Smith").save()
    saved = await Statement.Create(
        label="A Statement",
        action={
            "type": "Action",
            "label": "An Action",
            "identified": [
                {
                    "type": "Identification",
                    "certainty": c,
                    "target": [{"type": "Person", "id": person.id}],
                }
                for c in (1, 2)
            ],
        },
    ).save()

    read = await Statement.get(id=saved.id)
    assert sorted(i.certainty for i in read.action.identified) == [1, 2]
    for identified in read.action.identified:
        assert identified.target[0].id == person.id


@no_type_check
async def test_read_reified_relation_in_a_semantic_space(clear_database):
    class Negative[T](SemanticSpace[T]):
        pass

    class Person(Entity):
        pass

    class Identification[T](ReifiedRelation[T]):
        certainty: int

    class Statement(Document):
        identified: Identification[Person]

    class Factoid(Document):
        statements: list[Negative[Statement]]

    initialise()

    person = await Person.Create(label="John Smith").save()
    saved = await Factoid.Create(
        label="A Factoid",
        statements=[
            {
                "type": "Negative",
                "contents": [
                    {
                        "type": "Statement",
                        "label": "A Statement",
                        "identified": {
                            "type": "Identification",
                            "certainty": 1,
                            "target": [{"type": "Person", "id": person.id}],
                        },
                    }
                ],
            }
        ],
    ).save()

    read = await Factoid.get(id=saved.id)
    statement = read.statements[0].contents[0]
    assert statement.identified.certainty == 1
    assert statement.identified.target[0].id == person.id


@no_type_check
async def test_read_reified_relation_document(clear_database):
    class Person(Entity):
        pass

    class Role[T](ReifiedRelationDocument[T]):
        since: datetime.date

    class Statement(Document):
        role: Role[Person]

    initialise()

    person = await Person.Create(label="John Smith").save()
    saved = await Statement.Create(
        label="A Statement",
        role={
            "type": "Role",
            "since": "2000-01-01",
            "target": [{"type": "Person", "id": person.id}],
        },
    ).save()

    read = await Statement.get(id=saved.id)
    assert read.role.since == datetime.date(2000, 1, 1)
    assert read.role.target[0].id == person.id


@no_type_check
async def test_read_annotated_value(clear_database):
    class WithCertainty[T](AnnotatedValue[T]):
        certainty: int

    class Naming(Document):
        name: WithCertainty[str]

    initialise()

    saved = await Naming.Create(
        label="A Naming", name={"value": "John", "certainty": 2}
    ).save()

    read = await Naming.get(id=saved.id)
    assert read.name.value == "John"
    assert read.name.certainty == 2




@no_type_check
async def test_read_annotated_value_with_a_list_of_literals(clear_database):
    class WithCertainty[T](AnnotatedValue[T]):
        certainty: int

    class Naming(Document):
        aliases: WithCertainty[list[str]]

    initialise()

    saved = await Naming.Create(
        label="A Naming", aliases={"value": ["a", "b", "c"], "certainty": 2}
    ).save()

    read = await Naming.get(id=saved.id)
    assert read.aliases.value == ["a", "b", "c"]
    assert read.aliases.certainty == 2
