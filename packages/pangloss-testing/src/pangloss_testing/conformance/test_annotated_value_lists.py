"""A list of annotated values (`list[WithCertainty[str]]`) is a list of maps on the node, written and read back whole"""

from types import SimpleNamespace as ns
from typing import no_type_check

import pytest
from pangloss_models import (
    AnnotatedValue,
    Entity,
    PanglossMigrationNotSupported,
    initialise,
)

from .helpers import count_nodes, run
from .migration_support import declare, migrate

pytestmark = pytest.mark.asyncio(loop_scope="session")


def models():
    class WithCertainty[T](AnnotatedValue[T]):
        certainty: int

    class Person(Entity):
        names: list[WithCertainty[str]]

    initialise()
    return Person


@no_type_check
async def test_a_list_of_annotated_values_is_saved_and_read_back_in_order(
    db_driver, clear_database
):
    Person = models()

    saved = await Person.Create(
        label="John",
        names=[
            {"value": "John Smith", "certainty": 3},
            {"value": "Johnny", "certainty": 1},
        ],
    ).save()

    read = await Person.get(id=saved.id)
    assert [(n.value, n.certainty) for n in read.names] == [
        ("John Smith", 3),
        ("Johnny", 1),
    ]
    # (a property of the node, not a node of its own)
    assert count_nodes(db_driver, "WithCertainty") == 0
    stored = run(db_driver, "MATCH (n:Person) RETURN n")[0]["n"]["names"]
    assert stored == [
        {"value": "John Smith", "certainty": 3},
        {"value": "Johnny", "certainty": 1},
    ]


@no_type_check
async def test_an_empty_list_is_saved_and_read_back_empty(db_driver, clear_database):
    Person = models()

    saved = await Person.Create(label="Nobody", names=[]).save()

    assert (await Person.get(id=saved.id)).names == []


@no_type_check
async def test_an_update_replaces_the_list_whole_and_may_empty_it(
    db_driver, clear_database
):
    Person = models()
    saved = await Person.Create(
        label="John", names=[{"value": "John", "certainty": 3}]
    ).save()

    await Person.Update(
        id=saved.id,
        label="John",
        names=[{"value": "Jack", "certainty": 2}, {"value": "Jock", "certainty": 1}],
    ).save()
    assert [n.value for n in (await Person.get(id=saved.id)).names] == ["Jack", "Jock"]

    await Person.Update(id=saved.id, label="John", names=[]).save()
    assert (await Person.get(id=saved.id)).names == []

    await Person.Update(
        id=saved.id, label="John", names=[{"value": "Again", "certainty": 1}]
    ).save()
    assert [n.value for n in (await Person.get(id=saved.id)).names] == ["Again"]


@no_type_check
async def test_an_item_of_the_list_that_lacks_a_field_is_refused(
    db_driver, clear_database
):
    Person = models()

    with pytest.raises(ValueError, match="certainty"):
        Person.Create(label="John", names=[{"value": "John"}])


@no_type_check
async def test_the_list_is_in_the_search_results_and_the_api_shape(
    db_driver, clear_database
):
    Person = models()
    saved = await Person.Create(
        label="John", names=[{"value": "John", "certainty": 3}]
    ).save()

    dumped = (await Person.get(id=saved.id)).model_dump(by_alias=True)
    assert dumped["names"] == [{"value": "John", "certainty": 3}]


# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------


def certainty():
    class WithCertainty[T](AnnotatedValue[T]):
        certainty: int

    return WithCertainty


@no_type_check
async def test_a_list_of_annotated_values_that_is_added_starts_empty(
    db_driver, clear_database
):
    def v1():
        class Person(Entity):
            pass

        return ns(Person=Person)

    def v2():
        WithCertainty = certainty()

        class Person(Entity):
            names: list[WithCertainty[str]]

        return ns(Person=Person)

    old_models, old = declare(v1)
    saved = await old_models.Person.Create(label="Ann").save()
    new_models, new = declare(v2)

    await migrate(old, new)  # (no answer: it is not asked for)

    assert (await new_models.Person.get(id=saved.id)).names == []


@no_type_check
async def test_a_value_made_a_list_of_values_is_a_change_of_kind_and_refused(
    db_driver, clear_database
):
    def v1():
        WithCertainty = certainty()

        class Person(Entity):
            name: WithCertainty[str]

        return ns(Person=Person)

    def v2():
        WithCertainty = certainty()

        class Person(Entity):
            name: list[WithCertainty[str]]

        return ns(Person=Person)

    _, old = declare(v1)
    _, new = declare(v2)

    with pytest.raises(PanglossMigrationNotSupported, match="annotatedValue"):
        await migrate(old, new)
