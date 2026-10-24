"""The events that listeners to writes (`pangloss_models.hooks.after_write`) are given:
after the commit, once for each write that changes a head node."""

from typing import no_type_check
from uuid import uuid7

import pytest
from pangloss_models import initialise
from pangloss_models.exceptions import (
    PanglossEntityInUseError,
    PanglossVersionConflictError,
)
from pangloss_models.hooks import WriteEvent, after_write
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.fixture
def events():
    heard: list[WriteEvent] = []
    after_write.append(heard.append)
    yield heard
    after_write.remove(heard.append)


@no_type_check
async def test_each_write_to_a_head_node_is_announced_with_its_version_and_payload(
    db_driver, clear_database, events
):
    class Statement(Document):
        text: str

    initialise()

    statement = await Statement.Create(label="S", text="one").save()
    await Statement.Update(id=statement.id, label="S", text="two").save()
    await Statement.delete(statement.id)
    await Statement.undelete(statement.id)

    assert [(e.op, e.version) for e in events] == [
        ("create", 1),
        ("update", 2),
        ("delete", 2),
        ("undelete", 2),
    ]
    assert all(e.model is Statement and e.id == statement.id for e in events)
    assert all(e.user and e.at for e in events)
    assert events[0].payload.text == "one" and events[0].payload.id == statement.id
    assert events[1].payload.text == "two"
    assert events[2].payload is None and events[3].payload is None


@no_type_check
async def test_a_write_that_fails_is_not_announced(db_driver, clear_database, events):
    class Person(Entity):
        pass

    initialise()

    person = await Person.Create(label="John").save()
    events.clear()

    with pytest.raises(PanglossVersionConflictError):
        await Person.Update(id=person.id, label="J").save(expected_version=5)
    assert events == []


@no_type_check
async def test_an_entity_that_is_marked_and_not_deleted_is_not_announced(
    db_driver, clear_database, events
):
    class Person(Entity):
        pass

    class Statement(Document):
        about: Person

    initialise()

    person = await Person.Create(label="John").save()
    await Statement.Create(label="S", about={"type": "Person", "id": person.id}).save()
    events.clear()

    with pytest.raises(PanglossEntityInUseError):
        await Person.delete(person.id)
    assert events == []


@no_type_check
async def test_the_entities_that_a_write_made_are_given_and_those_that_existed_are_not(
    db_driver, clear_database, events
):
    class Person(Entity):
        _meta = Entity.Meta(create_inline=True, create_with_id=True)

    class Statement(Document):
        about: Person

    initialise()

    new_id, old_id = uuid7(), uuid7()
    await Person.Create(label="Old", id=old_id, create_new=True).save()
    events.clear()

    def payload(id):
        return {"type": "Person", "id": id, "label": "P", "create_new": True}

    await Statement.Create(label="S1", about=payload(new_id)).save()
    await Statement.Create(label="S2", about=payload(old_id)).save()

    first, second = events
    assert [e.id for e in first.created_entities] == [new_id]
    assert first.created_entities[0].type == "Person"
    assert second.created_entities == ()


@no_type_check
async def test_a_listener_that_fails_does_not_fail_the_write_nor_stop_the_others(
    db_driver, clear_database, events
):
    class Person(Entity):
        pass

    initialise()

    def broken(event):
        raise RuntimeError("no")

    after_write.insert(0, broken)
    try:
        person = await Person.Create(label="John").save()
    finally:
        after_write.remove(broken)

    assert [e.id for e in events] == [person.id]
    assert (await Person.get(person.id)).label == "John"
