from argparse import Action
from inspect import iscoroutinefunction
from typing import Annotated
from uuid import uuid7

import pytest
from pangloss_models import initialise
from pangloss_models.field_definitions import FieldSubclassing
from pangloss_models.model_bases.configs import RelationConfig
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.edge_model import EdgeModel
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.helpers import ViaEdge
from pangloss_users import current_request_username
from typing_extensions import no_type_check

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_document_get(clear_database):
    class Statement(Document):
        pass

    initialise()

    assert Statement.get
    assert iscoroutinefunction(Statement.get)

    resp = await Statement.get(uuid7())
    assert resp


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
async def test_document_write_with_user_contextvar():
    class Statement(Document):
        pass

    initialise()

    with current_request_username.set("john_smith"):
        st = Statement.Create(label="A Statement")
        result = await st.save()
    assert result.id
    assert result.label == "A Statement"
    assert result.type == "Statement"
    assert result.meta.created_by == "john_smith"


@no_type_check
async def test_document_write_with_different_types(clear_database):
    class Statement(Document):
        name: str
        age: int
        stuff: list[str]

    initialise()

    st = Statement.Create(
        label="A Statement", name="Statement", age=100, stuff=["one", "two", "three"]
    )

    result = await st.save()
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
    assert data["p"]["head_node_id"] == data["st"]["id"]


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
        MATCH (st:Action)-[r:carried_out_by]->(p:Person {{id: "{str(p_created.id)}"}})
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
async def test_write_nested_statements(db_driver):
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
