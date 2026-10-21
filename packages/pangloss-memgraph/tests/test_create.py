import datetime
from decimal import Decimal
from enum import Enum, IntEnum
from inspect import iscoroutinefunction
from typing import Annotated, NotRequired, TypedDict, no_type_check
from uuid import uuid4, uuid7

import pytest
from pangloss_models import initialise
from pangloss_models.model_registry import ModelRegistry
from pangloss_models.exceptions import (
    PanglossConflictError,
    PanglossWriteError,
    PanglossReferenceError,
    PanglossUserNotFoundError,
)
from pangloss_models.field_definitions import FieldSubclassing
from pangloss_models.model_bases.annotated_value import AnnotatedValue
from pangloss_models.model_bases.configs import RelationConfig
from pangloss_models.model_bases.conjunction import Conjunction
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
from pangloss_models.model_bases.trait import Trait
from pangloss_users import current_request_username
from pydantic import AnyHttpUrl

from pangloss_memgraph.databases.memgraph.initialise_database import (
    initialise_database,
)

from .helpers import count_nodes, labels_of, native, run

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_document_get(clear_database):
    class Statement(Document):
        pass

    initialise()

    assert Statement.get
    assert iscoroutinefunction(Statement.get)


@no_type_check
async def test_document_write(clear_database):
    class Statement(Document):
        pass

    initialise()

    st = Statement.Create(label="A Statement")

    result = await st.save()
    assert result.id
    assert result.label == "A Statement"
    assert result.type == "Statement"
    assert result.meta.created_by == "pangloss_default_user"


@no_type_check
async def test_document_write_with_user_contextvar(db_driver, clear_database):
    class Statement(Document):
        pass

    initialise()

    run(db_driver, "MERGE (:PGUser {username: 'john_smith'})")

    with current_request_username.set("john_smith"):
        st = Statement.Create(label="A Statement")
        result = await st.save()
    assert result.id
    assert result.label == "A Statement"
    assert result.type == "Statement"
    assert result.meta.created_by == "john_smith"


@no_type_check
async def test_document_write_with_different_types():
    class Statement(Document):
        name: str
        age: int
        stuff: list[str]

    initialise()

    st = Statement.Create(
        label="A Statement", name="Statement", age=100, stuff=["one", "two", "three"]
    )

    saved = await st.save()

    result = await Statement.get(id=saved.id)

    assert result.id
    assert result.label == "A Statement"
    assert result.type == "Statement"
    assert result.meta.created_by == "pangloss_default_user"
    assert result.name == "Statement"
    assert result.age == 100
    assert result.stuff == ["one", "two", "three"]


@no_type_check
async def test_write_entity(clear_database):
    class Person(Entity):
        pass

    initialise()

    p = Person.Create(label="John Smith")

    result = await p.save()

    assert result.label == "John Smith"


@no_type_check
async def test_write_existing_related_entity(db_driver, clear_database):
    class Person(Entity):
        pass

    class Statement(Document):
        concerns_person: Person

    initialise()

    p_to_create = Person.Create(label="John Smith")
    p_created = await p_to_create.save()
    assert p_created.id

    st = Statement.Create(
        label="A Statement", concerns_person={"type": "Person", "id": p_created.id}
    )

    await st.save()

    records, summary, keys = db_driver.execute_query(
        "MATCH (st:Statement)-[r:concerns_person]->(p:Person) RETURN st, r, p"
    )

    data = records[0].data()
    assert data

    assert data["p"]["label"] == "John Smith"
    assert data["st"]["label"] == "A Statement"
    assert data["r"][1] == "concerns_person"


@no_type_check
async def test_write_with_relation_to_new_entity(db_driver, clear_database):
    class Person(Entity):
        _meta = Entity.Meta(create_inline=True, create_with_id=True)

    class Statement(Document):
        concerns_person: Person

    initialise()

    st = Statement.Create(
        label="A Statement",
        concerns_person={
            "id": uuid7(),
            "type": "Person",
            "label": "John Smith",
            "create_new": True,
        },
    )

    assert isinstance(st.concerns_person, Person.Create)

    st_db = st._to_db_model()

    assert isinstance(st_db.concerns_person, Person.CreateDB)

    await st.save()

    records, summary, keys = db_driver.execute_query(
        "MATCH (st:Statement)-[r:concerns_person]->(p:Person) RETURN st, r, p"
    )

    data = records[0].data()
    assert data

    assert data["p"]["label"] == "John Smith"
    assert data["st"]["label"] == "A Statement"
    assert data["r"][1] == "concerns_person"
    # (the entity is not part of the statement that created it)
    assert "head_node_id" not in data["p"]


@no_type_check
async def test_we_can_match_id_with_wrong_type_as_long_as_its_allowed(
    db_driver, clear_database
):
    class Person(Entity):
        pass

    class Dude(Entity):
        pass

    class Statement(Document):
        concerns_person: Person | Dude

    initialise()

    p_to_create = Person.Create(label="John Smith")
    p_created = await p_to_create.save()
    assert p_created.id

    st = Statement.Create(
        # type of concerned person is deliberately wrong!
        label="A Statement",
        concerns_person={"type": "Dude", "id": p_created.id},
    )

    await st.save()

    records, summary, keys = db_driver.execute_query(
        "MATCH (st:Statement)-[r:concerns_person]->(p:Person) RETURN st, r, p"
    )

    data = records[0].data()
    assert data

    assert data["p"]["label"] == "John Smith"
    assert data["st"]["label"] == "A Statement"
    assert data["r"][1] == "concerns_person"


@no_type_check
async def test_write_subclassed_edges(db_driver, clear_database):
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

    p_to_create = Person.Create(label="John Smith")
    p_created = await p_to_create.save()
    assert p_created.id

    ac = Action.Create(
        # type of concerned person is deliberately wrong!
        label="An Action",
        carried_out_by={"type": "Person", "id": p_created.id},
    )

    await ac.save()

    records, summary, keys = db_driver.execute_query(f"""
        MATCH (st:Action)-[r:carried_out_by]->(p:Person {{id: "{p_created.id!s}"}})
        MATCH (st)-[:concerns_person]->(p)
        MATCH (st)<-[:carried_out_by_reverse]-(p)
        MATCH (st)<-[:concerns_person_reverse]-(p)
        RETURN st, r, p

        """)
    data = records[0].data()
    assert data["p"]
    assert data["st"]


@no_type_check
async def test_write_edge_properties(db_driver, clear_database):
    class SomeEdge(EdgeModel):
        number: int

    class Person(Entity):
        pass

    class Statement(Document):
        concerns_person: ViaEdge[Person, SomeEdge]

    initialise()

    p_to_create = Person.Create(label="John Smith")
    p_created = await p_to_create.save()
    assert p_created.id

    st = Statement.Create(
        label="A Statement",
        concerns_person={
            "type": "Person",
            "id": p_created.id,
            "edge_properties": {"number": 1},
        },
    )

    await st.save()


@no_type_check
async def test_write_nested_statements(db_driver, clear_database):
    class Action(Document):
        action_carried_out_by: Person

    class Order(Document):
        order_given_by: Person
        order_received_by: Person
        thing_ordered: Action

    class Person(Entity):
        pass

    initialise()

    js = Person.Create(label="John Smith")
    john_smith = await js.save()
    assert john_smith.id

    km = Person.Create(label="Kaiser Maximilian")
    kaiser_maximilian = await km.save()
    assert kaiser_maximilian.id

    order = Order.Create(
        label="An Order",
        order_given_by={"type": "Person", "id": kaiser_maximilian.id},
        order_received_by={"type": "Person", "id": john_smith.id},
        thing_ordered={
            "type": "Action",
            "label": "An Action",
            "action_carried_out_by": {"type": "Person", "id": john_smith.id},
        },
    )

    await order.save()

    records, summary, keys = db_driver.execute_query("""
        MATCH (order:Order)-[:order_given_by]->(km:Person)
        MATCH (order)-[:order_received_by]->(js:Person)
        MATCH (order)-[:thing_ordered]->(action:Action)-[:action_carried_out_by]->(js)

        RETURN order, action, km, js

        """)

    data = records[0].data()

    assert data["order"]
    assert data["action"]
    assert data["km"]
    assert data["js"]


@no_type_check
async def test_massive_write(clear_database):
    class Action(Document):
        action_carried_out_by: list[Person]

    class Person(Entity):
        _meta = Entity.Meta(create_inline=True, create_with_id=True)

    initialise()

    uids = [uuid7() for _ in range(200)]

    for i, uid in enumerate(uids):
        p = Person.Create(type="Person", id=uid, label=f"A Person{i}", create_new=True)
        await p.save()

    action = Action.Create(
        label="An Action",
        action_carried_out_by=[{"type": "Person", "id": uid} for uid in uids],
    )

    await action.save()


@no_type_check
async def test_massive_nested_write(clear_database):
    class Action(Document):
        action_carried_out_by: list[Person]

    class Order(Document):
        order_given_by: Person
        order_received_by: Person
        thing_ordered: list[Action]

    class Person(Entity):
        _meta = Entity.Meta(create_inline=True, create_with_id=True)

    initialise()

    order = Order.Create(
        label="An Order",
        order_given_by={
            "type": "Person",
            "id": uuid7(),
            "label": "DudeX",
            "create_new": True,
        },
        order_received_by={
            "type": "Person",
            "id": uuid7(),
            "label": "DudeY",
            "create_new": True,
        },
        thing_ordered=[
            {
                "type": "Action",
                "label": f"An Action {j}",
                "action_carried_out_by": [
                    {
                        "type": "Person",
                        "id": uuid7(),
                        "label": f"Dude{i}",
                        "create_new": True,
                    }
                    for i in range(20)
                ],
            }
            for j in range(20)
        ],
    )

    assert isinstance(order.thing_ordered[0], Action.Create)
    assert isinstance(order.thing_ordered[0].action_carried_out_by[0], Person.Create)

    order_db = order._to_db_model()
    assert isinstance(order_db.thing_ordered[0], Action.CreateDB)
    assert isinstance(
        order_db.thing_ordered[0].action_carried_out_by[0], Person.CreateDB
    )

    order_ref = await order.save()

    order_from_db = await Order.get(id=order_ref.id)

    assert order_from_db.order_given_by.type == "Person"
    assert order_from_db.order_given_by.id
    assert order_from_db.order_received_by.type == "Person"
    assert order_from_db.order_received_by.id

    assert len(order_from_db.thing_ordered) == 20
    assert len(order_from_db.thing_ordered[0].action_carried_out_by) == 20
    assert order_from_db.thing_ordered[0].action_carried_out_by[0].type == "Person"


@no_type_check
async def test_write_semantic_spaces(clear_database):

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

    factoid_from_db = await Factoid.get(id=factoid_ref.id)
    assert factoid_from_db.type == "Factoid"
    assert factoid_from_db.statements[0].type == "Negative"
    assert factoid_from_db.statements[0].contents[0].type == "Order"
    assert (
        factoid_from_db.statements[0].contents[0].label
        == "KM orders JS to take an action"
    )
    assert factoid_from_db.statements[0].contents[0].order_given_by.id == km.id
    assert factoid_from_db.statements[0].contents[0].order_received_by.id == js.id
    assert factoid_from_db.statements[0].contents[0].thing_ordered[0].type == "Action"
    assert (
        factoid_from_db.statements[0]
        .contents[0]
        .thing_ordered[0]
        .action_carried_out_by.type
        == "Person"
    )


# ---------------------------------------------------------------------------
# Head nodes: labels, properties, creation record
# ---------------------------------------------------------------------------


@no_type_check
async def test_head_node_labels_include_parents_and_kind(db_driver, clear_database):
    class Statement(Document):
        pass

    class Action(Statement):
        pass

    class Person(Entity):
        pass

    class Employee(Person):
        pass

    initialise()

    action = await Action.Create(label="An Action").save()
    employee = await Employee.Create(label="An Employee").save()

    assert labels_of(db_driver, action.id) == {
        "Action",
        "Statement",
        "Document",
        "HeadNode",
        "PGIndexableNode",
    }
    assert labels_of(db_driver, employee.id) == {
        "Employee",
        "Person",
        "Entity",
        "HeadNode",
        "PGIndexableNode",
    }


@no_type_check
async def test_head_node_properties(db_driver, clear_database):
    class Statement(Document):
        text: str

    initialise()

    saved = await Statement.Create(label="A Statement", text="Some text").save()

    node = run(db_driver, "MATCH (n:Statement) RETURN n")[0]["n"]
    assert node["id"] == str(saved.id)
    assert node["type"] == "Statement"
    assert node["label"] == "A Statement"
    assert node["text"] == "Some text"
    # A head node is its own head: no pointer to a head node, and its
    # creation metadata lives on the PGCreation node instead
    assert "head_node_id" not in node
    assert "head_node_type" not in node
    assert "meta" not in node


@no_type_check
async def test_each_save_creates_a_new_node_with_a_new_id(db_driver, clear_database):
    class Statement(Document):
        pass

    initialise()

    first = await Statement.Create(label="Same label").save()
    second = await Statement.Create(label="Same label").save()

    assert first.id != second.id
    assert count_nodes(db_driver, "Statement") == 2


@no_type_check
async def test_document_create_with_given_id(db_driver, clear_database):
    class Statement(Document):
        _meta = Document.Meta(create_with_id=True)

    initialise()

    given_id = uuid7()
    saved = await Statement.Create(id=given_id, create_new=True, label="Given").save()

    assert saved.id == given_id
    rows = run(db_driver, "MATCH (n:Statement {id: $id}) RETURN n", id=str(given_id))
    assert len(rows) == 1


@no_type_check
async def test_creating_with_an_id_already_in_use_raises(db_driver, clear_database):
    class Statement(Document):
        _meta = Document.Meta(create_with_id=True)

    initialise()

    given_id = uuid7()
    await Statement.Create(id=given_id, create_new=True, label="First").save()

    with pytest.raises(PanglossConflictError, match=str(given_id)):
        await Statement.Create(id=given_id, create_new=True, label="Second").save()

    assert count_nodes(db_driver, "Statement") == 1
    assert run(db_driver, "MATCH (n:Statement) RETURN n.label AS l") == [
        {"l": "First"}
    ]


@no_type_check
async def test_creation_record_is_linked_to_head_node_and_user(
    db_driver, clear_database
):
    class Statement(Document):
        pass

    initialise()

    saved = await Statement.Create(label="A Statement").save()

    rows = run(
        db_driver,
        """
        MATCH (user:PGUser)<-[:created_by]-(c:PGCreation)-[:is_creation_of]->(n:Statement)
        RETURN user.username AS username, c.created_when AS created_when, n.id AS id
        """,
    )
    assert len(rows) == 1
    assert rows[0]["id"] == str(saved.id)
    assert rows[0]["username"] == "pangloss_default_user"
    assert rows[0]["created_when"] is not None


@no_type_check
async def test_creation_record_uses_current_user(db_driver, clear_database):
    class Statement(Document):
        pass

    initialise()

    run(db_driver, "MERGE (:PGUser {username: 'john_smith'})")

    token = current_request_username.set("john_smith")
    try:
        saved = await Statement.Create(label="A Statement").save()
    finally:
        current_request_username.reset(token)

    assert saved.meta.created_by == "john_smith"
    rows = run(
        db_driver,
        "MATCH (:Statement)<-[:is_creation_of]-(:PGCreation)-[:created_by]->(u:PGUser) "
        "RETURN u.username AS username",
    )
    assert [r["username"] for r in rows] == ["john_smith"]


@no_type_check
async def test_writing_as_unknown_user_raises_and_writes_nothing(
    db_driver, clear_database
):

    class Statement(Document):
        pass

    initialise()

    token = current_request_username.set("nobody_by_this_name")
    try:
        with pytest.raises(PanglossUserNotFoundError, match="nobody_by_this_name"):
            await Statement.Create(label="A Statement").save()
    finally:
        current_request_username.reset(token)

    assert count_nodes(db_driver, "Statement") == 0
    assert count_nodes(db_driver, "PGCreation") == 0


@no_type_check
async def test_a_single_creation_record_for_a_nested_write(db_driver, clear_database):
    class Leaf(Document):
        pass

    class Branch(Document):
        leaf: Leaf

    class Root(Document):
        branch: Branch

    initialise()

    await Root.Create(
        label="Root",
        branch={
            "type": "Branch",
            "label": "Branch",
            "leaf": {"type": "Leaf", "label": "Leaf"},
        },
    ).save()

    assert count_nodes(db_driver, "PGCreation") == 1


@no_type_check
async def test_save_return_types(db_driver, clear_database):
    class Statement(Document):
        text: str

    initialise()

    reference = await Statement.Create(label="A Statement", text="hello").save()
    assert isinstance(reference, Statement.ReferenceView)
    assert reference.label == "A Statement"
    assert reference.type == "Statement"
    assert reference.meta.created_by == "pangloss_default_user"

    full = await Statement.Create(label="Another", text="world").save(detail=True)
    assert isinstance(full, Statement.HeadView)
    assert full.text == "world"
    assert full.meta.created_by == "pangloss_default_user"
    assert full.meta.head_node_type == "Statement"


# ---------------------------------------------------------------------------
# Literal fields
# ---------------------------------------------------------------------------


@no_type_check
async def test_literal_types_are_written(db_driver, clear_database):
    class Statement(Document):
        text: str
        number: int
        ratio: float
        on_date: datetime.date
        at_time: datetime.datetime
        tags: list[str]
        numbers: list[int]

    initialise()

    await Statement.Create(
        label="Literals",
        text="hello",
        number=42,
        ratio=1.5,
        on_date=datetime.date(2020, 3, 4),
        at_time=datetime.datetime(2020, 3, 4, 5, 6, 7),
        tags=["a", "b"],
        numbers=[1, 2, 3],
    ).save()

    node = run(db_driver, "MATCH (n:Statement) RETURN n")[0]["n"]
    assert node["text"] == "hello"
    assert node["number"] == 42
    assert node["ratio"] == 1.5
    assert native(node["on_date"]) == datetime.date(2020, 3, 4)
    assert native(node["at_time"]) == datetime.datetime(2020, 3, 4, 5, 6, 7)
    assert node["tags"] == ["a", "b"]
    assert node["numbers"] == [1, 2, 3]


@no_type_check
async def test_literal_types_read_back(db_driver, clear_database):
    class Statement(Document):
        text: str
        number: int
        ratio: float
        at_time: datetime.datetime
        tags: list[str]
        numbers: list[int]

    initialise()

    saved = await Statement.Create(
        label="Literals",
        text="hello",
        number=42,
        ratio=1.5,
        at_time=datetime.datetime(2020, 3, 4, 5, 6, 7),
        tags=["a", "b"],
        numbers=[1, 2, 3],
    ).save()

    read = await Statement.get(id=saved.id)
    assert read.text == "hello"
    assert read.number == 42
    assert read.ratio == 1.5
    assert read.at_time == datetime.datetime(2020, 3, 4, 5, 6, 7)
    assert read.tags == ["a", "b"]
    assert read.numbers == [1, 2, 3]


@no_type_check
async def test_date_literal_read_back(db_driver, clear_database):
    class Statement(Document):
        on_date: datetime.date

    initialise()

    saved = await Statement.Create(
        label="A date", on_date=datetime.date(2020, 3, 4)
    ).save()

    read = await Statement.get(id=saved.id)
    assert read.on_date == datetime.date(2020, 3, 4)


@no_type_check
async def test_bool_literals_are_written_and_read_back(db_driver, clear_database):
    class Statement(Document):
        true_flag: bool
        false_flag: bool
        flags: list[bool]

    initialise()

    saved = await Statement.Create(
        label="Bools", true_flag=True, false_flag=False, flags=[True, False]
    ).save()

    node = run(db_driver, "MATCH (n:Statement) RETURN n")[0]["n"]
    assert node["true_flag"] is True
    assert node["false_flag"] is False
    assert node["flags"] == [True, False]

    read = await Statement.get(id=saved.id)
    assert read.true_flag is True
    assert read.false_flag is False
    assert read.flags == [True, False]


class Colour(Enum):
    RED = "red"
    BLUE = "blue"


class Size(IntEnum):
    SMALL = 1
    LARGE = 2


class Dimensions(TypedDict):
    width: int
    height: int
    note: NotRequired[str]


@no_type_check
async def test_decimal_is_written_exactly_and_read_back(db_driver, clear_database):
    class Statement(Document):
        price: Decimal
        prices: list[Decimal]

    initialise()

    saved = await Statement.Create(
        label="Priced",
        price="1234567890.123456789012345678",
        prices=["0.10", "2.50", "0"],
    ).save()

    # Stored as strings, so that no precision is lost
    node = run(db_driver, "MATCH (n:Statement) RETURN n")[0]["n"]
    assert node["price"] == "1234567890.123456789012345678"
    assert node["prices"] == ["0.10", "2.50", "0"]

    read = await Statement.get(id=saved.id)
    assert read.price == Decimal("1234567890.123456789012345678")
    assert read.prices == [Decimal("0.10"), Decimal("2.50"), Decimal("0")]


@no_type_check
async def test_enum_is_written_as_its_value_and_read_back(db_driver, clear_database):
    class Statement(Document):
        colour: Colour
        size: Size
        colours: list[Colour]

    initialise()
    await initialise_database()

    saved = await Statement.Create(
        label="Enumerated",
        colour=Colour.RED,
        size=Size.LARGE,
        colours=["red", Colour.BLUE],
    ).save()

    node = run(db_driver, "MATCH (n:Statement) RETURN n")[0]["n"]
    # The values of the members, as plain strings
    assert node["colour"] == Colour.RED.value
    assert node["size"] == Size.LARGE.value
    assert node["colours"] == [Colour.RED.value, Colour.BLUE.value]

    read = await Statement.get(id=saved.id)
    assert read.colour is Colour.RED
    assert read.size is Size.LARGE
    assert read.colours == [Colour.RED, Colour.BLUE]


@no_type_check
@pytest.mark.parametrize("annotation", [int, Colour, Decimal, Dimensions])
async def test_optional_literal_set_to_none_reads_back_as_none(
    db_driver, clear_database, annotation
):
    class Statement(Document):
        optional: annotation | None

    initialise()

    saved = await Statement.Create(label="Sparse", optional=None).save()

    node = run(db_driver, "MATCH (n:Statement) RETURN n")[0]["n"]
    assert "optional" not in node

    read = await Statement.get(id=saved.id)
    assert read.optional is None


@no_type_check
async def test_optional_literal_can_be_left_out(db_driver, clear_database):
    class Statement(Document):
        number: int | None
        colour: Colour | None

    initialise()

    saved = await Statement.Create(label="Left out").save()

    node = run(db_driver, "MATCH (n:Statement) RETURN n")[0]["n"]
    assert "number" not in node
    assert "colour" not in node

    read = await Statement.get(id=saved.id)
    assert read.number is None
    assert read.colour is None


@no_type_check
async def test_optional_literal_with_value_reads_back(db_driver, clear_database):
    class Statement(Document):
        number: int | None
        colour: Colour | None
        price: Decimal | None

    initialise()
    await initialise_database()

    saved = await Statement.Create(
        label="Set", number=0, colour="red", price="1.5"
    ).save()

    read = await Statement.get(id=saved.id)
    assert read.number == 0
    assert read.colour is Colour.RED
    assert read.price == Decimal("1.5")


@no_type_check
async def test_optional_reference_view_extra_field_is_listed(db_driver, clear_database):
    class Statement(Document):
        _meta = Document.Meta(reference_view_extra_fields=["note"])
        note: str | None

    initialise()

    await Statement.Create(label="With", note="a note").save()
    await Statement.Create(label="Without", note=None).save()

    listed = await Statement.list()
    notes = {item.label: item.note for item in listed.results}
    assert notes == {"With": "a note", "Without": None}


@no_type_check
async def test_typeddict_is_written_as_a_map_and_read_back(db_driver, clear_database):
    class Inner(TypedDict):
        values: list[int]
        price: Decimal
        colour: Colour

    class Outer(TypedDict):
        name: str
        inner: Inner

    class Statement(Document):
        dimensions: Dimensions
        nested: Outer
        all_dimensions: list[Dimensions]

    initialise()
    await initialise_database()

    saved = await Statement.Create(
        label="Dictionary",
        dimensions={"width": 1, "height": 2, "note": "small"},
        nested={
            "name": "outer",
            "inner": {"values": [1, 2], "price": "1.50", "colour": "blue"},
        },
        all_dimensions=[{"width": 3, "height": 4}, {"width": 5, "height": 6}],
    ).save()

    node = run(db_driver, "MATCH (n:Statement) RETURN n")[0]["n"]
    assert node["dimensions"] == {"width": 1, "height": 2, "note": "small"}
    assert node["nested"] == {
        "name": "outer",
        "inner": {"values": [1, 2], "price": "1.50", "colour": Colour.BLUE.value},
    }
    assert node["all_dimensions"] == [
        {"width": 3, "height": 4},
        {"width": 5, "height": 6},
    ]

    read = await Statement.get(id=saved.id)
    assert read.dimensions == {"width": 1, "height": 2, "note": "small"}
    assert read.nested["inner"]["price"] == Decimal("1.50")
    assert read.nested["inner"]["colour"] is Colour.BLUE
    assert read.all_dimensions == [
        {"width": 3, "height": 4},
        {"width": 5, "height": 6},
    ]


@no_type_check
async def test_typeddict_with_optional_key_missing(db_driver, clear_database):
    class Statement(Document):
        dimensions: Dimensions

    initialise()

    saved = await Statement.Create(
        label="No note", dimensions={"width": 1, "height": 2}
    ).save()

    read = await Statement.get(id=saved.id)
    assert read.dimensions == {"width": 1, "height": 2}


@no_type_check
async def test_decimal_enum_and_typeddict_on_nested_documents_and_entities(
    db_driver, clear_database
):
    class Person(Entity):
        favourite: Colour
        height: Decimal

    class Action(Document):
        size: Size
        dimensions: Dimensions

    class Statement(Document):
        action: Action

    initialise()
    await initialise_database()

    person = await Person.Create(
        label="John Smith", favourite="blue", height="1.85"
    ).save()
    assert labels_of(db_driver, person.id)
    node = run(db_driver, "MATCH (n:Person) RETURN n")[0]["n"]
    assert node["favourite"] == Colour.BLUE.value
    assert node["height"] == "1.85"

    await Statement.Create(
        label="A Statement",
        action={
            "type": "Action",
            "label": "An Action",
            "size": 1,
            "dimensions": {"width": 1, "height": 2},
        },
    ).save()

    action = run(db_driver, "MATCH (a:Action) RETURN a")[0]["a"]
    assert action["size"] == Size.SMALL.value
    assert action["dimensions"] == {"width": 1, "height": 2}


@no_type_check
async def test_decimal_enum_and_typeddict_as_edge_properties(db_driver, clear_database):
    class Certainty(EdgeModel):
        weight: Decimal
        colour: Colour
        dimensions: Dimensions

    class Person(Entity):
        pass

    class Statement(Document):
        concerns_person: ViaEdge[Person, Certainty]

    initialise()
    await initialise_database()

    person = await Person.Create(label="John Smith").save()
    await Statement.Create(
        label="A Statement",
        concerns_person={
            "type": "Person",
            "id": person.id,
            "edge_properties": {
                "weight": "0.75",
                "colour": "red",
                "dimensions": {"width": 1, "height": 2},
            },
        },
    ).save()

    for edge in ("concerns_person", "concerns_person_reverse"):
        props = run(db_driver, f"MATCH ()-[r:{edge}]->() RETURN properties(r) AS p")[0][
            "p"
        ]
        assert props["weight"] == "0.75", edge
        assert props["colour"] == Colour.RED.value, edge
        assert props["dimensions"] == {"width": 1, "height": 2}, edge


@no_type_check
async def test_decimal_and_enum_in_annotated_value(db_driver, clear_database):
    class WithWeight[T](AnnotatedValue[T]):
        weight: Decimal
        colour: Colour
        when: datetime.date

    class Naming(Document):
        name: WithWeight[str]

    initialise()
    await initialise_database()

    await Naming.Create(
        label="A Naming",
        name={"value": "John", "weight": "0.5", "colour": "red", "when": "2020-01-02"},
    ).save()

    node = run(db_driver, "MATCH (n:Naming) RETURN n")[0]["n"]
    assert node["name"]["value"] == "John"
    assert node["name"]["weight"] == "0.5"
    assert node["name"]["colour"] == Colour.RED.value
    assert native(node["name"]["when"]) == datetime.date(2020, 1, 2)


@no_type_check
async def test_none_literals_are_not_written(db_driver, clear_database):
    class Statement(Document):
        text: str | None
        number: int | None

    initialise()

    await Statement.Create(label="Sparse", text=None, number=None).save()

    node = run(db_driver, "MATCH (n:Statement) RETURN n")[0]["n"]
    assert "text" not in node
    assert "number" not in node


@no_type_check
async def test_literals_with_special_characters_are_stored_verbatim(
    db_driver, clear_database
):
    class Statement(Document):
        text: str

    initialise()

    run(db_driver, "CREATE (:Canary {id: 'canary'})")

    nasty = "x'}) DETACH DELETE n //\" \\ ünïcödé 日本語\nnewline"
    await Statement.Create(label=nasty, text=nasty).save()

    node = run(db_driver, "MATCH (n:Statement) RETURN n")[0]["n"]
    assert node["label"] == nasty
    assert node["text"] == nasty
    assert count_nodes(db_driver, "Canary") == 1


@no_type_check
async def test_falsy_literals_are_written(db_driver, clear_database):
    class Statement(Document):
        number: int
        ratio: float
        text: str
        tags: list[str]

    initialise()

    await Statement.Create(label="Falsy", number=0, ratio=0.0, text="", tags=[]).save()

    node = run(db_driver, "MATCH (n:Statement) RETURN n")[0]["n"]
    assert node["number"] == 0
    assert node["ratio"] == 0.0
    assert node["text"] == ""
    assert node["tags"] == []


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------


@no_type_check
async def test_entity_head_node(db_driver, clear_database):
    class Person(Entity):
        born: datetime.date | None = None

    initialise()

    saved = await Person.Create(
        label="John Smith", born=datetime.date(1900, 1, 1)
    ).save()

    assert isinstance(saved, Person.ReferenceView)
    node = run(db_driver, "MATCH (n:Person) RETURN n")[0]["n"]
    assert node["id"] == str(saved.id)
    assert node["label"] == "John Smith"
    assert native(node["born"]) == datetime.date(1900, 1, 1)
    assert labels_of(db_driver, saved.id) == {
        "Person",
        "Entity",
        "HeadNode",
        "PGIndexableNode",
    }


@no_type_check
async def test_entity_with_url_as_id_is_given_a_uuid(db_driver, clear_database):
    class Person(Entity):
        _meta = Entity.Meta(create_with_id=True)

    initialise()

    url = "http://example.com/people/john-smith"
    saved = await Person.Create(id=AnyHttpUrl(url), create_new=True, label="JS").save()

    rows = run(db_driver, "MATCH (n:Person) RETURN n.id AS id")
    assert len(rows) == 1
    assert rows[0]["id"] == str(saved.id)
    assert rows[0]["id"] != url


@no_type_check
async def test_entity_url_id_is_stored_as_a_url_node(db_driver, clear_database):
    class Person(Entity):
        _meta = Entity.Meta(create_with_id=True)

    initialise()

    url = "http://example.com/people/john-smith"
    await Person.Create(id=AnyHttpUrl(url), create_new=True, label="JS").save()

    # The URL is a node that the entity has, not a property of it
    node = run(db_driver, "MATCH (n:Person) RETURN n")[0]["n"]
    assert "urls" not in node
    rows = run(db_driver, "MATCH (:Person)-[:has_url]->(u:PGUrl) RETURN u.url AS url")
    assert rows == [{"url": url}]


# ---------------------------------------------------------------------------
# Relations to existing nodes
# ---------------------------------------------------------------------------


@no_type_check
async def test_relation_to_existing_entity_writes_forward_and_reverse_edges(
    db_driver, clear_database
):
    class Person(Entity):
        pass

    class Statement(Document):
        concerns_person: Person

    initialise()

    person = await Person.Create(label="John Smith").save()
    statement = await Statement.Create(
        label="A Statement", concerns_person={"type": "Person", "id": person.id}
    ).save()

    rows = run(
        db_driver,
        """
        MATCH (s:Statement)-[f:concerns_person]->(p:Person)
        MATCH (s)<-[r:concerns_person_reverse]-(p)
        RETURN s.id AS s, p.id AS p, properties(f) AS fp, properties(r) AS rp
        """,
    )
    assert len(rows) == 1
    assert rows[0]["s"] == str(statement.id)
    assert rows[0]["p"] == str(person.id)
    assert rows[0]["rp"] == {"reverse": True}
    assert "reverse" not in rows[0]["fp"]
    # The existing entity is not duplicated or altered
    assert count_nodes(db_driver, "Person") == 1


@no_type_check
async def test_relation_with_custom_reverse_name(db_driver, clear_database):
    class Person(Entity):
        pass

    class Statement(Document):
        concerns_person: Annotated[
            Person, RelationConfig(reverse_name="Is Concerned In")
        ]

    initialise()

    person = await Person.Create(label="John Smith").save()
    await Statement.Create(
        label="A Statement", concerns_person={"type": "Person", "id": person.id}
    ).save()

    rows = run(
        db_driver,
        "MATCH (:Statement)<-[r:is_concerned_in]-(:Person) RETURN count(r) AS c",
    )
    assert rows[0]["c"] == 1
    assert (
        run(db_driver, "MATCH ()-[r:concerns_person_reverse]->() RETURN count(r) AS c")[
            0
        ]["c"]
        == 0
    )


@no_type_check
async def test_list_relation_to_existing_entities(db_driver, clear_database):
    class Person(Entity):
        pass

    class Statement(Document):
        concerns_people: list[Person]

    initialise()

    people = [await Person.Create(label=f"Person {i}").save() for i in range(5)]
    await Statement.Create(
        label="A Statement",
        concerns_people=[{"type": "Person", "id": p.id} for p in people],
    ).save()

    rows = run(
        db_driver,
        "MATCH (:Statement)-[:concerns_people]->(p:Person) RETURN p.id AS id",
    )
    assert {r["id"] for r in rows} == {str(p.id) for p in people}
    assert (
        run(db_driver, "MATCH ()-[r:concerns_people_reverse]->() RETURN count(r) AS c")[
            0
        ]["c"]
        == 5
    )


@no_type_check
async def test_empty_list_relation_writes_no_edges(db_driver, clear_database):
    class Person(Entity):
        pass

    class Statement(Document):
        everyone: list[Person]

    initialise()

    await Statement.Create(label="A Statement", everyone=[]).save()

    assert count_nodes(db_driver, "Statement") == 1
    assert (
        run(
            db_driver,
            "MATCH ()-[r]->() WHERE type(r) = 'everyone' RETURN r",
        )
        == []
    )


@no_type_check
async def test_relation_to_union_of_entity_types(db_driver, clear_database):
    class Person(Entity):
        pass

    class Place(Entity):
        pass

    class Statement(Document):
        concerns: list[Person | Place]

    initialise()

    person = await Person.Create(label="A Person").save()
    place = await Place.Create(label="A Place").save()

    await Statement.Create(
        label="A Statement",
        concerns=[
            {"type": "Person", "id": person.id},
            {"type": "Place", "id": place.id},
        ],
    ).save()

    rows = run(db_driver, "MATCH (:Statement)-[:concerns]->(n) RETURN n.type AS t")
    assert sorted(r["t"] for r in rows) == ["Person", "Place"]


@no_type_check
async def test_relation_to_subclass_of_allowed_entity_type(db_driver, clear_database):
    class Person(Entity):
        pass

    class Employee(Person):
        pass

    class Statement(Document):
        concerns_person: Person

    initialise()

    employee = await Employee.Create(label="An Employee").save()
    await Statement.Create(
        label="A Statement", concerns_person={"type": "Employee", "id": employee.id}
    ).save()

    rows = run(
        db_driver,
        "MATCH (:Statement)-[:concerns_person]->(e:Employee) RETURN e.id AS id",
    )
    assert [r["id"] for r in rows] == [str(employee.id)]


@no_type_check
async def test_relation_to_trait_accepts_every_implementer(db_driver, clear_database):
    class Agent(Trait):
        pass

    class Person(Entity, Agent):
        pass

    class Group(Entity, Agent):
        pass

    class Statement(Document):
        carried_out_by: list[Agent]

    initialise()

    person = await Person.Create(label="A Person").save()
    group = await Group.Create(label="A Group").save()

    await Statement.Create(
        label="A Statement",
        carried_out_by=[
            {"type": "Person", "id": person.id},
            {"type": "Group", "id": group.id},
        ],
    ).save()

    rows = run(
        db_driver, "MATCH (:Statement)-[:carried_out_by]->(n) RETURN n.type AS t"
    )
    assert sorted(r["t"] for r in rows) == ["Group", "Person"]


@no_type_check
async def test_trait_labels_are_added_to_nodes(db_driver, clear_database):
    class Agent(Trait):
        pass

    class Person(Entity, Agent):
        pass

    initialise()

    person = await Person.Create(label="A Person").save()

    assert "Agent" in labels_of(db_driver, person.id)


@no_type_check
async def test_relation_to_entity_of_disallowed_type_raises_and_writes_nothing(
    db_driver, clear_database
):
    class Person(Entity):
        pass

    class Place(Entity):
        pass

    class Statement(Document):
        concerns_person: Person

    initialise()

    place = await Place.Create(label="A Place").save()

    with pytest.raises(PanglossReferenceError, match="concerns_person"):
        await Statement.Create(
            label="A Statement", concerns_person={"type": "Person", "id": place.id}
        ).save()

    assert count_nodes(db_driver, "Statement") == 0


@no_type_check
async def test_relation_to_missing_entity_raises_and_writes_nothing(
    db_driver, clear_database
):
    class Person(Entity):
        pass

    class Statement(Document):
        concerns_person: Person

    initialise()

    missing_id = uuid7()
    with pytest.raises(PanglossReferenceError, match=str(missing_id)):
        await Statement.Create(
            label="A Statement", concerns_person={"type": "Person", "id": missing_id}
        ).save()

    assert count_nodes(db_driver, "Statement") == 0
    assert count_nodes(db_driver, "PGCreation") == 0


@no_type_check
async def test_one_missing_entity_among_many_raises_and_writes_nothing(
    db_driver, clear_database
):
    """A write is all-or-nothing: no partial documents"""

    class Person(Entity):
        pass

    class Statement(Document):
        concerns_people: list[Person]

    initialise()

    person = await Person.Create(label="Exists").save()

    with pytest.raises(PanglossReferenceError):
        await Statement.Create(
            label="A Statement",
            concerns_people=[
                {"type": "Person", "id": person.id},
                {"type": "Person", "id": uuid7()},
            ],
        ).save()

    assert count_nodes(db_driver, "Statement") == 0
    assert (
        run(db_driver, "MATCH ()-[r:concerns_people]->() RETURN count(r) AS c")[0]["c"]
        == 0
    )


@no_type_check
async def test_same_entity_in_two_fields(db_driver, clear_database):
    class Person(Entity):
        pass

    class Order(Document):
        order_given_by: Person
        order_received_by: Person

    initialise()

    person = await Person.Create(label="Self-orderer").save()
    reference = {"type": "Person", "id": person.id}
    await Order.Create(
        label="An Order", order_given_by=reference, order_received_by=reference
    ).save()

    for edge in ("order_given_by", "order_received_by"):
        rows = run(
            db_driver, f"MATCH (:Order)-[r:{edge}]->(:Person) RETURN count(r) AS c"
        )
        assert rows[0]["c"] == 1


@no_type_check
async def test_relation_to_existing_entity_by_url(db_driver, clear_database):
    class Person(Entity):
        _meta = Entity.Meta(create_with_id=True)

    class Statement(Document):
        concerns_person: Person

    initialise()

    url = AnyHttpUrl("http://example.com/people/john-smith")
    await Person.Create(id=url, create_new=True, label="JS").save()

    await Statement.Create(
        label="A Statement", concerns_person={"type": "Person", "id": url}
    ).save()

    assert count_nodes(db_driver, "Statement") == 1


# ---------------------------------------------------------------------------
# Edge properties
# ---------------------------------------------------------------------------


@no_type_check
async def test_edge_properties_are_written_to_both_edges(db_driver, clear_database):
    class Certainty(EdgeModel):
        number: int
        note: str
        weight: float
        tags: list[str]
        when: datetime.date

    class Person(Entity):
        pass

    class Statement(Document):
        concerns_person: ViaEdge[Person, Certainty]

    initialise()

    person = await Person.Create(label="John Smith").save()
    await Statement.Create(
        label="A Statement",
        concerns_person={
            "type": "Person",
            "id": person.id,
            "edge_properties": {
                "number": 3,
                "note": "fairly sure",
                "weight": 0.5,
                "tags": ["a", "b"],
                "when": "2020-01-02",
            },
        },
    ).save()

    rows = run(
        db_driver,
        """
        MATCH (:Statement)-[f:concerns_person]->(:Person)
        MATCH (:Statement)<-[r:concerns_person_reverse]-(:Person)
        RETURN properties(f) AS f, properties(r) AS r
        """,
    )
    assert len(rows) == 1
    forward, reverse = rows[0]["f"], rows[0]["r"]
    for props in (forward, reverse):
        assert props["number"] == 3
        assert props["note"] == "fairly sure"
        assert props["weight"] == 0.5
        assert props["tags"] == ["a", "b"]
        assert native(props["when"]) == datetime.date(2020, 1, 2)
    assert "reverse" not in forward


@no_type_check
async def test_reverse_edge_keeps_reverse_flag_when_it_has_edge_properties(
    db_driver, clear_database
):
    class Certainty(EdgeModel):
        number: int

    class Person(Entity):
        pass

    class Statement(Document):
        concerns_person: ViaEdge[Person, Certainty]

    initialise()

    person = await Person.Create(label="John Smith").save()
    await Statement.Create(
        label="A Statement",
        concerns_person={
            "type": "Person",
            "id": person.id,
            "edge_properties": {"number": 1},
        },
    ).save()

    rows = run(
        db_driver,
        "MATCH (:Statement)<-[r:concerns_person_reverse]-(:Person) RETURN properties(r) AS r",
    )
    assert rows[0]["r"]["reverse"] is True
    assert rows[0]["r"]["number"] == 1


@no_type_check
async def test_edge_properties_on_each_item_of_a_list_are_separate(
    db_driver, clear_database
):
    class Certainty(EdgeModel):
        number: int

    class Person(Entity):
        pass

    class Statement(Document):
        concerns: list[ViaEdge[Person, Certainty]]

    initialise()

    first = await Person.Create(label="First").save()
    second = await Person.Create(label="Second").save()

    await Statement.Create(
        label="A Statement",
        concerns=[
            {"type": "Person", "id": first.id, "edge_properties": {"number": 1}},
            {"type": "Person", "id": second.id, "edge_properties": {"number": 2}},
        ],
    ).save()

    rows = run(
        db_driver,
        "MATCH (:Statement)-[r:concerns]->(p:Person) RETURN p.id AS id, r.number AS n",
    )
    assert {r["id"]: r["n"] for r in rows} == {str(first.id): 1, str(second.id): 2}


@no_type_check
async def test_edge_properties_on_edge_to_nested_document(db_driver, clear_database):
    class Certainty(EdgeModel):
        number: int

    class Action(Document):
        pass

    class Statement(Document):
        action: ViaEdge[Action, Certainty]

    initialise()

    await Statement.Create(
        label="A Statement",
        action={
            "type": "Action",
            "label": "An Action",
            "edge_properties": {"number": 7},
        },
    ).save()

    rows = run(
        db_driver,
        """
        MATCH (:Statement)-[f:action]->(a:Action)
        MATCH (:Statement)<-[r:action_reverse]-(a)
        RETURN f.number AS f, r.number AS r
        """,
    )
    assert rows == [{"f": 7, "r": 7}]


@no_type_check
async def test_edge_properties_on_nested_document_inside_a_list(
    db_driver, clear_database
):
    class Certainty(EdgeModel):
        number: int

    class Person(Entity):
        pass

    class Action(Document):
        carried_out_by: ViaEdge[Person, Certainty]

    class Statement(Document):
        actions: list[Action]

    initialise()

    person = await Person.Create(label="John Smith").save()
    await Statement.Create(
        label="A Statement",
        actions=[
            {
                "type": "Action",
                "label": f"Action {i}",
                "carried_out_by": {
                    "type": "Person",
                    "id": person.id,
                    "edge_properties": {"number": i},
                },
            }
            for i in range(3)
        ],
    ).save()

    rows = run(
        db_driver,
        "MATCH (a:Action)-[r:carried_out_by]->(:Person) RETURN a.label AS l, r.number AS n",
    )
    assert {r["l"]: r["n"] for r in rows} == {
        "Action 0": 0,
        "Action 1": 1,
        "Action 2": 2,
    }


# ---------------------------------------------------------------------------
# Nested documents
# ---------------------------------------------------------------------------


@no_type_check
async def test_nested_document_node(db_driver, clear_database):
    class Action(Document):
        detail: str

    class Statement(Document):
        action: Action

    initialise()

    statement = await Statement.Create(
        label="A Statement",
        action={"type": "Action", "label": "An Action", "detail": "details"},
    ).save()

    node = run(db_driver, "MATCH (:Statement)-[:action]->(a:Action) RETURN a")[0]["a"]
    assert node["label"] == "An Action"
    assert node["detail"] == "details"
    assert node["head_node_id"] == str(statement.id)
    assert node["head_node_type"] == "Statement"
    assert node["meta"]["created_by"] == "pangloss_default_user"
    assert node["meta"]["updated_by"] == "pangloss_default_user"
    assert node["meta"]["semantic_spaces"] == []
    assert node["meta"]["created_when"] is not None

    assert labels_of(db_driver, node["id"]) == {
        "Action",
        "Document",
        "PGIndexableNode",
    }
    assert (
        run(
            db_driver,
            "MATCH (:Statement)<-[r:action_reverse {reverse: true}]-(:Action) RETURN count(r) AS c",
        )[0]["c"]
        == 1
    )


@no_type_check
async def test_deeply_nested_documents_all_point_at_the_head_node(
    db_driver, clear_database
):
    class Leaf(Document):
        pass

    class Branch(Document):
        leaf: Leaf

    class Trunk(Document):
        branch: Branch

    class Root(Document):
        trunk: Trunk

    initialise()

    root = await Root.Create(
        label="Root",
        trunk={
            "type": "Trunk",
            "label": "Trunk",
            "branch": {
                "type": "Branch",
                "label": "Branch",
                "leaf": {"type": "Leaf", "label": "Leaf"},
            },
        },
    ).save()

    rows = run(
        db_driver,
        """
        MATCH (:Root)-[:trunk]->(:Trunk)-[:branch]->(:Branch)-[:leaf]->(l:Leaf)
        RETURN l.head_node_id AS head_id, l.head_node_type AS head_type
        """,
    )
    assert rows == [{"head_id": str(root.id), "head_type": "Root"}]

    head_nodes = run(db_driver, "MATCH (n:HeadNode) RETURN n.id AS id")
    assert [r["id"] for r in head_nodes] == [str(root.id)]

    others = run(
        db_driver,
        "MATCH (n:PGIndexableNode) WHERE n.id <> $id RETURN DISTINCT n.head_node_id AS h",
        id=str(root.id),
    )
    assert others == [{"h": str(root.id)}]


@no_type_check
async def test_list_of_nested_documents(db_driver, clear_database):
    class Action(Document):
        pass

    class Statement(Document):
        actions: list[Action]

    initialise()

    await Statement.Create(
        label="A Statement",
        actions=[{"type": "Action", "label": f"Action {i}"} for i in range(4)],
    ).save()

    rows = run(
        db_driver, "MATCH (:Statement)-[:actions]->(a:Action) RETURN a.label AS l"
    )
    assert sorted(r["l"] for r in rows) == [f"Action {i}" for i in range(4)]
    ids = run(db_driver, "MATCH (a:Action) RETURN DISTINCT a.id AS id")
    assert len(ids) == 4


@no_type_check
async def test_nested_document_of_a_subclass_has_parent_labels(
    db_driver, clear_database
):
    class Statement(Document):
        _meta = Document.Meta(abstract=True)

    class Action(Statement):
        pass

    class Order(Statement):
        pass

    class Factoid(Document):
        statements: list[Statement]

    initialise()

    await Factoid.Create(
        label="A Factoid",
        statements=[
            {"type": "Action", "label": "An Action"},
            {"type": "Order", "label": "An Order"},
        ],
    ).save()

    rows = run(
        db_driver,
        "MATCH (:Factoid)-[:statements]->(s:Statement) RETURN s.type AS t, labels(s) AS l",
    )
    assert {r["t"] for r in rows} == {"Action", "Order"}
    for row in rows:
        assert {row["t"], "Statement", "Document", "PGIndexableNode"} <= set(row["l"])


@no_type_check
async def test_nested_document_with_relation_to_existing_entity(
    db_driver, clear_database
):
    class Person(Entity):
        pass

    class Action(Document):
        carried_out_by: Person

    class Statement(Document):
        action: Action

    initialise()

    person = await Person.Create(label="John Smith").save()
    await Statement.Create(
        label="A Statement",
        action={
            "type": "Action",
            "label": "An Action",
            "carried_out_by": {"type": "Person", "id": person.id},
        },
    ).save()

    rows = run(
        db_driver,
        """
        MATCH (:Statement)-[:action]->(a:Action)-[:carried_out_by]->(p:Person)
        MATCH (a)<-[:carried_out_by_reverse]-(p)
        RETURN p.id AS id
        """,
    )
    assert [r["id"] for r in rows] == [str(person.id)]


@no_type_check
async def test_missing_entity_in_nested_document_raises_and_writes_nothing(
    db_driver, clear_database
):
    class Person(Entity):
        pass

    class Action(Document):
        carried_out_by: Person

    class Statement(Document):
        action: Action

    initialise()

    with pytest.raises(PanglossReferenceError):
        await Statement.Create(
            label="A Statement",
            action={
                "type": "Action",
                "label": "An Action",
                "carried_out_by": {"type": "Person", "id": uuid7()},
            },
        ).save()

    assert count_nodes(db_driver, "Statement") == 0
    assert count_nodes(db_driver, "Action") == 0


@no_type_check
async def test_relation_to_union_of_documents_and_entities(db_driver, clear_database):
    class Person(Entity):
        pass

    class Action(Document):
        pass

    class Statement(Document):
        subjects: list[Person | Action]

    initialise()

    person = await Person.Create(label="John Smith").save()
    await Statement.Create(
        label="A Statement",
        subjects=[
            {"type": "Person", "id": person.id},
            {"type": "Action", "label": "An Action"},
        ],
    ).save()

    rows = run(db_driver, "MATCH (:Statement)-[:subjects]->(n) RETURN n.type AS t")
    assert sorted(r["t"] for r in rows) == ["Action", "Person"]


@no_type_check
async def test_nested_document_with_inline_created_entity(db_driver, clear_database):
    class Person(Entity):
        _meta = Entity.Meta(create_inline=True, create_with_id=True)

    class Action(Document):
        carried_out_by: Person

    class Statement(Document):
        action: Action

    initialise()

    person_id = uuid7()
    statement = await Statement.Create(
        label="A Statement",
        action={
            "type": "Action",
            "label": "An Action",
            "carried_out_by": {
                "type": "Person",
                "id": person_id,
                "label": "John Smith",
                "create_new": True,
            },
        },
    ).save()

    person = run(db_driver, "MATCH (p:Person) RETURN p")[0]["p"]
    assert person["id"] == str(person_id)
    # It is an entity of its own, not part of the statement that created it
    assert "head_node_id" not in person
    assert "HeadNode" in labels_of(db_driver, person_id)
    assert statement.id


@no_type_check
async def test_inline_entity_with_existing_id_is_not_duplicated(
    db_driver, clear_database
):
    class Person(Entity):
        _meta = Entity.Meta(create_inline=True, create_with_id=True)

    class Statement(Document):
        concerns_person: Person

    initialise()

    person_id = uuid7()
    await Person.Create(id=person_id, create_new=True, label="Original").save()

    await Statement.Create(
        label="A Statement",
        concerns_person={
            "type": "Person",
            "id": person_id,
            "label": "Changed",
            "create_new": True,
        },
    ).save()

    people = run(db_driver, "MATCH (p:Person) RETURN p.label AS label")
    assert people == [{"label": "Original"}]
    assert (
        run(
            db_driver,
            "MATCH (:Statement)-[r:concerns_person]->(:Person) RETURN count(r) AS c",
        )[0]["c"]
        == 1
    )


@no_type_check
async def test_nested_documents_with_subclassed_edges(db_driver, clear_database):
    class Note(Document):
        pass

    class Base(Document):
        has_note: Note

    class Derived(Base):
        own_note: Annotated[
            Note,
            RelationConfig(
                subclasses_parent_fields=[
                    FieldSubclassing(field_name="has_note", field_on_model=Base)
                ]
            ),
        ]

    initialise()

    await Derived.Create(
        label="Derived", own_note={"type": "Note", "label": "A Note"}
    ).save()

    rows = run(
        db_driver,
        """
        MATCH (d:Derived)-[:own_note]->(n:Note)
        MATCH (d)-[:has_note]->(n)
        MATCH (d)<-[:own_note_reverse]-(n)
        MATCH (d)<-[:has_note_reverse]-(n)
        RETURN count(n) AS c
        """,
    )
    assert rows == [{"c": 1}]
    assert count_nodes(db_driver, "Note") == 1


@no_type_check
async def test_subclassed_edges_to_existing_entity_carry_edge_properties(
    db_driver, clear_database
):
    class Certainty(EdgeModel):
        number: int

    class Person(Entity):
        pass

    class Statement(Document):
        concerns_person: ViaEdge[Person, Certainty]

    class Action(Statement):
        carried_out_by: Annotated[
            ViaEdge[Person, Certainty],
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
    await Action.Create(
        label="An Action",
        carried_out_by={
            "type": "Person",
            "id": person.id,
            "edge_properties": {"number": 9},
        },
    ).save()

    for edge in ("carried_out_by", "concerns_person"):
        rows = run(
            db_driver, f"MATCH (:Action)-[r:{edge}]->(:Person) RETURN r.number AS n"
        )
        assert rows == [{"n": 9}], edge


# ---------------------------------------------------------------------------
# Semantic spaces
# ---------------------------------------------------------------------------


@no_type_check
async def test_semantic_space_node_and_contents(db_driver, clear_database):
    class Negative[T](SemanticSpace[T]):
        pass

    class Statement(Document):
        pass

    class Factoid(Document):
        statements: list[Statement | Negative[Statement]]

    initialise()

    factoid = await Factoid.Create(
        label="A Factoid",
        statements=[
            {"type": "Statement", "label": "Plain"},
            {
                "type": "Negative",
                "contents": [{"type": "Statement", "label": "Negated"}],
            },
        ],
    ).save()

    space = run(db_driver, "MATCH (n:Negative) RETURN n")[0]["n"]
    assert labels_of(db_driver, space["id"]) == {
        "Negative",
        "SemanticSpace",
        "PGIndexableNode",
    }
    assert space["head_node_id"] == str(factoid.id)

    rows = run(
        db_driver,
        """
        MATCH (f:Factoid)-[:statements]->(n:Negative)-[:contents]->(s:Statement)
        MATCH (n)<-[:contents_reverse]-(s)
        RETURN s.label AS label
        """,
    )
    assert rows == [{"label": "Negated"}]


@no_type_check
async def test_semantic_space_is_recorded_on_contents_only(db_driver, clear_database):
    class Negative[T](SemanticSpace[T]):
        pass

    class Statement(Document):
        pass

    class Factoid(Document):
        statements: list[Statement | Negative[Statement]]

    initialise()

    await Factoid.Create(
        label="A Factoid",
        statements=[
            {"type": "Statement", "label": "Plain"},
            {
                "type": "Negative",
                "contents": [{"type": "Statement", "label": "Negated"}],
            },
        ],
    ).save()

    metas = {
        r["label"]: r["meta"]
        for r in run(
            db_driver, "MATCH (s:Statement) RETURN s.label AS label, s.meta AS meta"
        )
    }
    negated_id = run(
        db_driver, "MATCH (s:Statement {label: 'Negated'}) RETURN s.id AS id"
    )[0]["id"]

    assert metas["Plain"]["semantic_spaces"] == []
    assert metas["Negated"]["semantic_spaces"] == ["Negative"]
    assert metas["Negated"]["context_labels"] == [
        {"type": "Negative", "contents": [{"type": "Statement", "id": negated_id}]}
    ]


@no_type_check
async def test_semantic_space_applies_to_everything_beneath_it(
    db_driver, clear_database
):
    class Negative[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    class Order(Document):
        thing_ordered: list[Action]

    class Factoid(Document):
        statements: list[Order | Negative[Order]]

    initialise()

    await Factoid.Create(
        label="A Factoid",
        statements=[
            {
                "type": "Negative",
                "contents": [
                    {
                        "type": "Order",
                        "label": "An Order",
                        "thing_ordered": [{"type": "Action", "label": "An Action"}],
                    }
                ],
            }
        ],
    ).save()

    for label in ("Order", "Action"):
        meta = run(db_driver, f"MATCH (n:{label}) RETURN n.meta AS meta")[0]["meta"]
        assert meta["semantic_spaces"] == ["Negative"], label


@no_type_check
async def test_sibling_semantic_spaces_do_not_share_state(db_driver, clear_database):
    class Negative[T](SemanticSpace[T]):
        pass

    class Hypothetical[T](SemanticSpace[T]):
        pass

    class Statement(Document):
        pass

    class Factoid(Document):
        statements: list[Statement | Negative[Statement] | Hypothetical[Statement]]

    initialise()

    await Factoid.Create(
        label="A Factoid",
        statements=[
            {"type": "Negative", "contents": [{"type": "Statement", "label": "N"}]},
            {"type": "Hypothetical", "contents": [{"type": "Statement", "label": "H"}]},
            {"type": "Statement", "label": "P"},
        ],
    ).save()

    spaces = {
        r["label"]: r["meta"]["semantic_spaces"]
        for r in run(
            db_driver, "MATCH (s:Statement) RETURN s.label AS label, s.meta AS meta"
        )
    }
    assert spaces == {"N": ["Negative"], "H": ["Hypothetical"], "P": []}


@no_type_check
async def test_nested_semantic_spaces(db_driver, clear_database):
    class Negative[T](SemanticSpace[T]):
        pass

    class Hypothetical[T](SemanticSpace[T]):
        pass

    class Statement(Document):
        pass

    class Factoid(Document):
        statements: list[Hypothetical[Negative[Statement]]]

    initialise()

    await Factoid.Create(
        label="A Factoid",
        statements=[
            {
                "type": "Hypothetical",
                "contents": [
                    {
                        "type": "Negative",
                        "contents": [{"type": "Statement", "label": "Inner"}],
                    }
                ],
            }
        ],
    ).save()

    meta = run(db_driver, "MATCH (s:Statement) RETURN s.meta AS meta")[0]["meta"]
    assert meta["semantic_spaces"] == ["Hypothetical", "Negative"]
    assert [c["type"] for c in meta["context_labels"]] == ["Hypothetical", "Negative"]


@no_type_check
async def test_semantic_space_with_entity_contents_and_edges(db_driver, clear_database):
    class Negative[T](SemanticSpace[T]):
        pass

    class Person(Entity):
        pass

    class Action(Document):
        carried_out_by: Person

    class Factoid(Document):
        statements: list[Negative[Action]]

    initialise()

    person = await Person.Create(label="John Smith").save()
    await Factoid.Create(
        label="A Factoid",
        statements=[
            {
                "type": "Negative",
                "contents": [
                    {
                        "type": "Action",
                        "label": "An Action",
                        "carried_out_by": {"type": "Person", "id": person.id},
                    }
                ],
            }
        ],
    ).save()

    rows = run(
        db_driver,
        "MATCH (:Factoid)-[:statements]->(:Negative)-[:contents]->(:Action)-[:carried_out_by]->(p:Person) RETURN p.id AS id",
    )
    assert rows == [{"id": str(person.id)}]
    # An entity that is merely referenced is not given context
    assert "meta" not in run(db_driver, "MATCH (p:Person) RETURN p")[0]["p"]


# ---------------------------------------------------------------------------
# Conjunctions, reified relations, embedded objects, annotated values
# ---------------------------------------------------------------------------


@no_type_check
async def test_conjunction(db_driver, clear_database):
    class Causes[TCause, TResult](Conjunction):
        cause: TCause
        result: TResult

    class Action(Document):
        pass

    class Factoid(Document):
        has_statements: Action | Causes[Action, Action]

    initialise()

    factoid = await Factoid.Create(
        label="A Factoid",
        has_statements={
            "type": "Causes",
            "cause": {"type": "Action", "label": "The cause"},
            "result": {"type": "Action", "label": "The result"},
        },
    ).save()

    assert labels_of(
        db_driver,
        run(db_driver, "MATCH (c:Causes) RETURN c.id AS id")[0]["id"],
    ) == {"Causes", "Conjunction", "PGIndexableNode"}

    rows = run(
        db_driver,
        """
        MATCH (:Factoid)-[:has_statements]->(c:Causes)
        MATCH (c)-[:cause]->(cause:Action)
        MATCH (c)-[:result]->(result:Action)
        RETURN cause.label AS cause, result.label AS result,
               c.head_node_id AS head, cause.head_node_id AS cause_head
        """,
    )
    assert rows == [
        {
            "cause": "The cause",
            "result": "The result",
            "head": str(factoid.id),
            "cause_head": str(factoid.id),
        }
    ]


@no_type_check
async def test_conjunction_read_back(db_driver, clear_database):
    class Causes[TCause, TResult](Conjunction):
        cause: TCause
        result: TResult

    class Action(Document):
        pass

    class Factoid(Document):
        has_statements: Action | Causes[Action, Action]

    initialise()

    saved = await Factoid.Create(
        label="A Factoid",
        has_statements={
            "type": "Causes",
            "cause": {"type": "Action", "label": "The cause"},
            "result": {"type": "Action", "label": "The result"},
        },
    ).save()

    read = await Factoid.get(id=saved.id)
    assert read.has_statements.type == "Causes"
    assert read.has_statements.cause.label == "The cause"
    assert read.has_statements.result.label == "The result"


@no_type_check
async def test_reified_relation(db_driver, clear_database):
    class Person(Entity):
        pass

    class Proxy[T](ReifiedRelation[T]):
        certainty: int

    class Statement(Document):
        identified: Proxy[Person]

    initialise()

    person = await Person.Create(label="John Smith").save()
    statement = await Statement.Create(
        label="A Statement",
        identified={
            "type": "Proxy",
            "certainty": 2,
            "target": [{"type": "Person", "id": person.id}],
        },
    ).save()

    rows = run(
        db_driver,
        """
        MATCH (s:Statement)-[:identified]->(r:Proxy)-[:target]->(p:Person)
        RETURN r.certainty AS certainty, r.head_node_id AS head, p.id AS person
        """,
    )
    assert rows == [
        {"certainty": 2, "head": str(statement.id), "person": str(person.id)}
    ]


@no_type_check
async def test_reified_relation_node_labels_and_properties(db_driver, clear_database):
    """Reified relations with a *nested document* target do get written"""

    class Place(Document):
        pass

    class Located[T](ReifiedRelation[T]):
        certainty: int

    class Statement(Document):
        located: Located[Place]

    initialise()

    await Statement.Create(
        label="A Statement",
        located={
            "type": "Located",
            "certainty": 2,
            "target": [{"type": "Place", "label": "A Place"}],
        },
    ).save()

    rows = run(
        db_driver,
        """
        MATCH (:Statement)-[:located]->(r:Located)-[:target]->(p:Place)
        RETURN r.certainty AS certainty, labels(r) AS labels, p.label AS place
        """,
    )
    assert len(rows) == 1
    assert rows[0]["certainty"] == 2
    assert {"Located", "ReifiedRelation", "PGIndexableNode"} <= set(rows[0]["labels"])
    assert rows[0]["place"] == "A Place"


@no_type_check
async def test_reified_relation_document(db_driver, clear_database):
    class Place(Document):
        pass

    class Residence[T](ReifiedRelationDocument[T]):
        since: datetime.date

    class Statement(Document):
        residence: Residence[Place]

    initialise()

    await Statement.Create(
        label="A Statement",
        residence={
            "type": "Residence",
            "label": "A Residence",
            "since": "2000-01-01",
            "target": [{"type": "Place", "label": "A Place"}],
        },
    ).save()

    rows = run(
        db_driver,
        """
        MATCH (:Statement)-[:residence]->(r:Residence)-[:target]->(:Place)
        RETURN r.since AS since, labels(r) AS labels
        """,
    )
    assert len(rows) == 1
    assert native(rows[0]["since"]) == datetime.date(2000, 1, 1)
    assert "ReifiedRelationDocument" in rows[0]["labels"]


@no_type_check
async def test_embedded_object(db_driver, clear_database):
    class Date(Embedded):
        when: datetime.date

    class Statement(Document):
        date: Date

    initialise()

    statement = await Statement.Create(
        label="A Statement", date={"type": "Date", "when": "2020-01-02"}
    ).save()

    rows = run(
        db_driver,
        """
        MATCH (s:Statement)-[:date]->(d:Date)
        RETURN d.when AS when, d.head_node_id AS head, labels(d) AS labels
        """,
    )
    assert len(rows) == 1
    assert native(rows[0]["when"]) == datetime.date(2020, 1, 2)
    assert rows[0]["head"] == str(statement.id)
    assert "Embedded" in rows[0]["labels"]


@no_type_check
async def test_annotated_value(db_driver, clear_database):
    class WithCertainty[T](AnnotatedValue[T]):
        certainty: int

    class Naming(Document):
        name: WithCertainty[str]

    initialise()

    await Naming.Create(
        label="A Naming", name={"value": "John", "certainty": 2}
    ).save()

    # An annotated value is a map on the node it belongs to, not a node of its own
    node = run(db_driver, "MATCH (n:Naming) RETURN n")[0]["n"]
    assert node["name"] == {"value": "John", "certainty": 2}
    assert count_nodes(db_driver, "WithCertainty") == 0
    assert count_nodes(db_driver, "AnnotatedValue") == 0
    assert run(db_driver, "MATCH (:Naming)-[r]->() RETURN count(r) AS c") == [{"c": 0}]


# ---------------------------------------------------------------------------
# Binding and fulfilment
# ---------------------------------------------------------------------------


@no_type_check
async def test_bound_field_values_are_written_on_children(db_driver, clear_database):
    from pangloss_models.field_definitions import FieldBinding

    class Action(Document):
        action_when: datetime.date

    class Statement(Document):
        when: datetime.date
        action: Annotated[
            Action,
            RelationConfig(
                bind_to_child_field=[
                    FieldBinding(bound_field="when", child_fields=["action_when"])
                ]
            ),
        ]

    initialise()

    await Statement.Create(
        label="A Statement",
        when="2020-05-06",
        action={"type": "Action", "label": "An Action"},
    ).save()

    node = run(db_driver, "MATCH (a:Action) RETURN a")[0]["a"]
    assert native(node["action_when"]) == datetime.date(2020, 5, 6)


@no_type_check
async def test_explicit_child_value_wins_over_bound_value(db_driver, clear_database):
    from pangloss_models.field_definitions import FieldBinding

    class Action(Document):
        action_when: datetime.date

    class Statement(Document):
        when: datetime.date
        action: Annotated[
            Action,
            RelationConfig(
                bind_to_child_field=[
                    FieldBinding(bound_field="when", child_fields=["action_when"])
                ]
            ),
        ]

    initialise()

    await Statement.Create(
        label="A Statement",
        when="2020-05-06",
        action={"type": "Action", "label": "An Action", "action_when": "1999-01-01"},
    ).save()

    node = run(db_driver, "MATCH (a:Action) RETURN a")[0]["a"]
    assert native(node["action_when"]) == datetime.date(1999, 1, 1)


@no_type_check
async def test_dates_inside_typeddicts_and_embedded_fields_read_back(
    db_driver, clear_database
):
    class Period(TypedDict):
        start: datetime.date
        end: datetime.date

    class Statement(Document):
        period: Period
        on_date: datetime.date | None
        dates: list[datetime.date]

    initialise()

    saved = await Statement.Create(
        label="Dates",
        period={"start": "2020-01-01", "end": "2020-12-31"},
        on_date="2021-02-03",
        dates=["2000-01-01", "2000-01-02"],
    ).save()

    read = await Statement.get(id=saved.id)
    assert read.period == {
        "start": datetime.date(2020, 1, 1),
        "end": datetime.date(2020, 12, 31),
    }
    assert read.on_date == datetime.date(2021, 2, 3)
    assert read.dates == [datetime.date(2000, 1, 1), datetime.date(2000, 1, 2)]


@no_type_check
async def test_annotated_value_of_a_list_of_literals(db_driver, clear_database):
    """To annotate a list, annotate the whole list"""

    class WithCertainty[T](AnnotatedValue[T]):
        certainty: int

    class Naming(Document):
        aliases: WithCertainty[list[str]]

    initialise()

    await Naming.Create(
        label="A Naming", aliases={"value": ["a", "b"], "certainty": 2}
    ).save()

    node = run(db_driver, "MATCH (n:Naming) RETURN n")[0]["n"]
    assert node["aliases"] == {"value": ["a", "b"], "certainty": 2}


@no_type_check
async def test_annotated_value_is_written_on_nested_documents_and_entities(
    db_driver, clear_database
):
    class WithCertainty[T](AnnotatedValue[T]):
        certainty: int

    class Person(Entity):
        name: WithCertainty[str]

    class Naming(Document):
        name: WithCertainty[str]

    class Statement(Document):
        naming: Naming

    initialise()

    await Person.Create(label="P", name={"value": "John", "certainty": 1}).save()
    await Statement.Create(
        label="S",
        naming={
            "type": "Naming",
            "label": "N",
            "name": {"value": "Johann", "certainty": 2},
        },
    ).save()

    person = run(db_driver, "MATCH (n:Person) RETURN n")[0]["n"]
    assert person["name"] == {"value": "John", "certainty": 1}
    naming = run(db_driver, "MATCH (n:Naming) RETURN n")[0]["n"]
    assert naming["name"] == {"value": "Johann", "certainty": 2}



@no_type_check
async def test_save_detail_for_an_entity(db_driver, clear_database):
    class Person(Entity):
        pass

    initialise()

    reference = await Person.Create(label="John Smith").save()
    assert isinstance(reference, Person.ReferenceView)

    full = await Person.Create(label="Jane Smith").save(detail=True)
    assert isinstance(full, Person.HeadView)
    assert full.label == "Jane Smith"

    updated = await Person.Update(id=full.id, label="Jane Jones").save(detail=True)
    assert isinstance(updated, Person.HeadView)
    assert updated.label == "Jane Jones"


@no_type_check
async def test_a_stored_value_that_is_not_a_member_cannot_be_read(db_driver, clear_database):
    """The database does not check the value (the models do): a bad one is found on reading"""

    class Statement(Document):
        colour: Colour

    initialise()
    saved = await Statement.Create(label="S", colour=Colour.RED).save()
    run(db_driver, "MATCH (n:Statement) SET n.colour = 'purple'")

    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="colour"):
        await Statement.get(id=saved.id)


@no_type_check
async def test_a_write_of_the_same_shape_is_the_same_query_text(db_driver, clear_database):
    """Memgraph keeps the plan of a query by its text. Names for the variables and parameters made at
    random planned every write afresh; they are counted, so the text depends only on the shape"""
    import uuid

    from pangloss_memgraph.databases.memgraph.build_create_query import build_head_create_query

    class Person(Entity):
        pass

    class Action(Document):
        text: str

    class Statement(Document):
        who: Person
        action: Action

    initialise()

    def build(label: str):
        instance = Statement.Create(
            label=label,
            who={"type": "Person", "id": uuid.uuid4()},
            action={"type": "Action", "label": f"A {label}", "text": label},
        )._to_db_model()
        return build_head_create_query(instance)

    first, second = build("one"), build("two")
    assert first.to_query_string() == second.to_query_string()
    assert dict(first.params) != dict(second.params)  # (what differs is in the parameters)
    assert all(name.startswith("x") and name[1:].isdigit() for name in first.params)
