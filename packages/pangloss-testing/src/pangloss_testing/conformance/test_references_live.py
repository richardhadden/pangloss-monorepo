"""`Entity.references`: which of some entities are still there, with their labels as they are now"""

from typing import no_type_check
from uuid import uuid7

import pytest
from pangloss_models import initialise
from pangloss_models.model_bases.entity import Entity

pytestmark = pytest.mark.asyncio(loop_scope="session")


def models():
    class Agent(Entity):
        pass

    class Person(Agent):
        pass

    class Place(Entity):
        pass

    initialise()
    return Agent, Person, Place


def found(items):
    return [(item.id, item.type, item.label) for item in items]


@no_type_check
async def test_gives_the_type_and_label_now_in_the_order_asked(clear_database):
    Agent, Person, Place = models()
    john = await Person.Create(label="John").save()
    paris = await Place.Create(label="Paris").save()

    assert found(await Entity.references([paris.id, john.id])) == [
        (paris.id, "Place", "Paris"),
        (john.id, "Person", "John"),
    ]


@no_type_check
async def test_a_renamed_entity_has_its_new_label(clear_database):
    Agent, Person, Place = models()
    john = await Person.Create(label="John").save()
    edit = await Person.get_for_edit(john.id)
    await Person.Update(**edit.model_dump() | {"label": "John Smith"}).save()

    assert found(await Entity.references([john.id])) == [
        (john.id, "Person", "John Smith")
    ]


@no_type_check
async def test_what_is_deleted_or_unknown_is_left_out(clear_database):
    Agent, Person, Place = models()
    john = await Person.Create(label="John").save()
    gone = await Place.Create(label="Atlantis").save()
    await Place.delete(gone.id)

    assert found(await Entity.references([gone.id, uuid7(), john.id, john.id])) == [
        (john.id, "Person", "John")
    ]
    assert await Entity.references([]) == []


@no_type_check
async def test_of_a_class_only_its_own_and_its_subclasses(clear_database):
    Agent, Person, Place = models()
    john = await Person.Create(label="John").save()
    paris = await Place.Create(label="Paris").save()

    assert found(await Agent.references([john.id, paris.id])) == [
        (john.id, "Person", "John")
    ]
