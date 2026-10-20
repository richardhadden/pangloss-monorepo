import datetime
from typing import TypedDict, no_type_check

import pytest
from pangloss_models import initialise
from pangloss_models.model_bases.annotated_value import AnnotatedValue
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.edge_model import EdgeModel
from pangloss_models.model_bases.embedded import Embedded
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.helpers import ViaEdge
from pangloss_models.model_bases.reified_relation import (
    ReifiedRelation,
    ReifiedRelationDocument,
)
from pangloss_models.model_bases.semantic_space import SemanticSpace

from pangloss_memgraph.databases.memgraph.initialise_database import (
    initialise_database,
)

from .test_create import Colour, Size  # noqa: E402

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

    factoid_ref = await factoid.save(detail=True)
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
async def test_write_and_read_every_member_of_a_union_of_embedded_objects(
    clear_database,
):
    class Place(Entity):
        pass

    class Date(Embedded):
        when: datetime.date

    class DateRange(Embedded):
        start: datetime.date
        end: datetime.date
        place: Place

    class Statement(Document):
        date: Date | DateRange

    initialise()

    place = await Place.Create(label="Paris").save()
    with_date = await Statement.Create(
        label="One", date={"type": "Date", "when": "2020-01-01"}
    ).save()
    with_range = await Statement.Create(
        label="Two",
        date={
            "type": "DateRange",
            "start": "2020-01-01",
            "end": "2020-12-31",
            "place": {"type": "Place", "id": place.id},
        },
    ).save()

    read = await Statement.get(id=with_date.id)
    assert read.date.type == "Date"
    assert read.date.when == datetime.date(2020, 1, 1)

    read = await Statement.get(id=with_range.id)
    assert read.date.type == "DateRange"
    assert read.date.end == datetime.date(2020, 12, 31)
    assert read.date.place.id == place.id


@no_type_check
async def test_read_embedded_object_nested_in_a_member_of_a_union(clear_database):
    class Detail(Embedded):
        note: str

    class Date(Embedded):
        when: datetime.date

    class DateRange(Embedded):
        detail: Detail

    class Statement(Document):
        date: Date | DateRange

    initialise()

    saved = await Statement.Create(
        label="A Statement",
        date={"type": "DateRange", "detail": {"type": "Detail", "note": "a note"}},
    ).save()

    read = await Statement.get(id=saved.id)
    assert read.date.type == "DateRange"
    assert read.date.detail.note == "a note"


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
            "label": "A Role",
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


# ---------------------------------------------------------------------------
# Edge properties, enums
# ---------------------------------------------------------------------------


@no_type_check
async def test_read_edge_properties(clear_database):
    class Certainty(EdgeModel):
        number: int

    class Person(Entity):
        pass

    class Action(Document):
        pass

    class Statement(Document):
        concerns: ViaEdge[Person, Certainty]
        action: ViaEdge[Action, Certainty]
        actions: list[ViaEdge[Action, Certainty]]

    initialise()

    person = await Person.Create(label="John Smith").save()
    saved = await Statement.Create(
        label="A Statement",
        concerns={"type": "Person", "id": person.id, "edge_properties": {"number": 1}},
        action={
            "type": "Action",
            "label": "One",
            "edge_properties": {"number": 2},
        },
        actions=[
            {
                "type": "Action",
                "label": f"Many {i}",
                "edge_properties": {"number": 10 + i},
            }
            for i in range(2)
        ],
    ).save()

    read = await Statement.get(id=saved.id)
    assert read.concerns.id == person.id
    assert read.concerns.edge_properties.number == 1
    assert read.action.edge_properties.number == 2
    assert sorted(a.edge_properties.number for a in read.actions) == [10, 11]


@no_type_check
async def test_read_enums_everywhere(clear_database):
    class Dimensions(TypedDict):
        size: Size
        colours: list[Colour]

    class WithColour[T](AnnotatedValue[T]):
        colour: Colour

    class Person(Entity):
        favourite: Colour

    class Action(Document):
        size: Size
        sizes: list[Size]

    class Statement(Document):
        colour: Colour
        optional_colour: Colour | None
        dimensions: Dimensions
        name: WithColour[str]
        action: Action
        actions: list[Action]
        concerns: Person

    initialise()
    await initialise_database()

    person = await Person.Create(label="John Smith", favourite="blue").save()
    saved = await Statement.Create(
        label="A Statement",
        colour="red",
        optional_colour=Colour.BLUE,
        dimensions={"size": Size.LARGE, "colours": [Colour.RED, Colour.BLUE]},
        name={"value": "John", "colour": Colour.BLUE},
        action={"type": "Action", "label": "A", "size": Size.SMALL, "sizes": [Size.LARGE]},
        actions=[
            {"type": "Action", "label": "B", "size": Size.LARGE, "sizes": []},
        ],
        concerns={"type": "Person", "id": person.id},
    ).save()

    read = await Statement.get(id=saved.id)
    assert read.colour is Colour.RED
    assert read.optional_colour is Colour.BLUE
    assert read.dimensions == {"size": Size.LARGE, "colours": [Colour.RED, Colour.BLUE]}
    assert read.name.colour is Colour.BLUE
    assert read.action.size is Size.SMALL
    assert read.action.sizes == [Size.LARGE]
    assert read.actions[0].size is Size.LARGE
    assert read.concerns.id == person.id

    read_person = await Person.get(id=person.id)
    assert read_person.favourite is Colour.BLUE


@no_type_check
async def test_list_documents_with_an_enum_in_the_reference_view(clear_database):
    class Statement(Document):
        _meta = Document.Meta(reference_view_extra_fields=["colour"])
        colour: Colour

    initialise()
    await initialise_database()

    await Statement.Create(label="Red", colour=Colour.RED).save()
    await Statement.Create(label="Blue", colour="blue").save()

    listed = await Statement.list()
    assert {item.label: item.colour for item in listed.results} == {
        "Red": Colour.RED,
        "Blue": Colour.BLUE,
    }


@no_type_check
async def test_read_entity_incoming_with_an_enum_in_the_reference_view(clear_database):
    class Person(Entity):
        pass

    class Statement(Document):
        _meta = Document.Meta(reference_view_extra_fields=["colour"])
        colour: Colour
        concerns: Person

    initialise()
    await initialise_database()

    person = await Person.Create(label="John Smith").save()
    await Statement.Create(
        label="A Statement",
        colour=Colour.BLUE,
        concerns={"type": "Person", "id": person.id},
    ).save()

    read = await Person.get(id=person.id)
    assert read.concerns_reverse[0].colour is Colour.BLUE


def test_the_read_query_is_the_same_text_for_every_document():
    """Memgraph keeps the plan of a query by its text: with the names of the parameters made for
    each call it planned the query afresh each time, which was most of what a read took"""
    import uuid

    from pangloss_memgraph.databases.memgraph.build_read_query import build_fetch_document_query
    from pangloss_models.model_bases.entity import Entity

    class Thing(Entity):
        pass

    first, first_params = build_fetch_document_query(Thing, uuid.uuid4())
    second, second_params = build_fetch_document_query(Thing, uuid.uuid4())
    assert first == second
    assert first_params["document_id"] != second_params["document_id"]
