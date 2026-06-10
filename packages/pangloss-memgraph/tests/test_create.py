from inspect import iscoroutinefunction
from uuid import uuid7

import pytest
from pangloss_models import initialise
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from pangloss_users import current_request_username
from typing_extensions import no_type_check

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_document_get():
    class Statement(Document):
        pass

    initialise()

    assert Statement.get
    assert iscoroutinefunction(Statement.get)

    resp = await Statement.get(uuid7())
    assert resp


@no_type_check
async def test_document_write():
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
async def test_document_write_with_different_types():
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
async def test_write_entity():
    class Person(Entity):
        pass

    initialise()

    p = Person.Create(label="John Smith")

    result = await p.save()

    assert result.label == "John Smith"
