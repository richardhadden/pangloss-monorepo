"""Reading by a class that has subclasses: the node is read as the class it is"""

from typing import no_type_check

import pytest
from pangloss_models import initialise
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from pydantic import AnyHttpUrl

pytestmark = pytest.mark.asyncio(loop_scope="session")


def models():
    class Base(Entity):
        _meta = Entity.Meta(create_with_id=True)

    class Sub(Base):
        extra: str | None = None

    class Sub2(Sub):
        pass

    class Note(Entity):
        about: Base

    class Paper(Document):
        text: str | None = None

    class Letter(Paper):
        recipient: str | None = None

    initialise()
    return Base, Sub, Sub2, Note, Paper, Letter


@no_type_check
async def test_an_entity_is_read_as_the_class_it_is_by_any_class_it_is_a_subclass_of(
    clear_database,
):
    Base, Sub, Sub2, Note, Paper, Letter = models()
    base = await Base.Create(label="b").save()
    sub = await Sub.Create(label="s", extra="x").save()
    sub2 = await Sub2.Create(label="s2").save()

    assert type(await Base.get(base.id)).__name__ == "BaseHeadView"
    for found_by, made, name in (
        (Base, sub, "Sub"),
        (Base, sub2, "Sub2"),
        (Sub, sub2, "Sub2"),
    ):
        read = await found_by.get(made.id)
        assert read.type == name
        assert isinstance(read, ModelRegistryClass(name).HeadView)
    assert (await Base.get(sub.id)).extra == "x"

    # (the other way: a parent is not a subclass)
    assert await Sub.get(base.id) is None
    assert await Sub2.get(sub.id) is None


def ModelRegistryClass(name):
    from pangloss_models.model_registry import ModelRegistry

    return ModelRegistry.all_models()[name]


@no_type_check
async def test_get_for_edit_gives_the_subclasss_edit_view(clear_database):
    Base, Sub, *_ = models()
    sub = await Sub.Create(label="s", extra="x").save()

    edit = await Base.get_for_edit(sub.id)

    assert isinstance(edit, Sub.EditView)
    assert edit.extra == "x"


@no_type_check
async def test_the_incoming_relations_are_those_of_the_subclass(clear_database):
    Base, Sub, Sub2, Note, *_ = models()
    sub = await Sub.Create(label="s").save()
    await Note.Create(label="n", about={"type": "Sub", "id": sub.id}).save()

    read = await Base.get(sub.id)

    assert [n.label for n in read.about_reverse] == ["n"]


@no_type_check
async def test_an_entity_is_found_by_url_through_its_parent(clear_database):
    Base, Sub, *_ = models()
    url = AnyHttpUrl("https://example.org/things/1")
    sub = await Sub.Create(id=url, create_new=True, label="s").save()

    read = await Base.get(url)

    assert read.id == sub.id and read.type == "Sub"


@no_type_check
async def test_a_head_document_is_read_as_the_class_it_is(clear_database):
    *_, Paper, Letter = models()
    letter = await Letter.Create(label="l", text="t", recipient="r").save()
    paper = await Paper.Create(label="p").save()

    read = await Paper.get(letter.id)

    assert isinstance(read, Letter.HeadView) and read.recipient == "r"
    assert await Letter.get(paper.id) is None
    assert (await Paper.get(paper.id)).type == "Paper"


@no_type_check
async def test_a_class_with_no_subclass_is_read_without_the_extra_lookup(
    clear_database,
):
    from uuid import uuid7

    from pangloss_neo4j.databases.neo4j.exposed_functions import class_of_node

    Base, Sub, Sub2, *_ = models()

    class NoDatabase:
        async def run(self, *args, **kwargs):
            raise AssertionError("it asked the database")

    assert await class_of_node(NoDatabase(), Sub2, uuid7()) is Sub2
