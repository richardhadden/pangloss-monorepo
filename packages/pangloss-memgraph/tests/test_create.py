from inspect import iscoroutinefunction
from uuid import uuid7

import pytest
from pangloss_models import initialise
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
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
async def test_write_with_relation_to_new_entity(db_driver):
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

    """
    await st.save()

    records, summary, keys = db_driver.execute_query(
        "MATCH (st:Statement)-[r:concerns_person]->(p:Person) RETURN st, r, p"
    )

    data = records[0].data()
    assert data

    assert data["p"]["label"] == "John Smith"
    assert data["st"]["label"] == "A Statement"
    assert data["r"][1] == "concerns_person"
    """
