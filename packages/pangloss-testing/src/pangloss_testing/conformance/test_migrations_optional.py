"""A single relation or embedded object that becomes optional (`Person` -> `Person | None`), or required again, or a
list that becomes an optional single one: what is stored does not change, and making one required checks that every
node has one (there is no default to give)."""

from types import SimpleNamespace as ns
from typing import no_type_check

import pytest
from pangloss_models import Document, Embedded, Entity, PanglossMigrationNotSupported
from pangloss_models.migrations import AlterNullability

from .migration_support import declare, migrate, with_answers

pytestmark = pytest.mark.asyncio(loop_scope="session")


def versions(home, born):
    def version():
        class Place(Entity):
            pass

        class Day(Embedded):
            year: int

        Person = type(
            "Person",
            (Document,),
            {"__annotations__": {"home": home(Place), "born": born(Day)}},
        )

        return ns(Place=Place, Day=Day, Person=Person)

    return version


def one(t):
    return t


def optional(t):
    return t | None


def many(t):
    return list[t]


@no_type_check
async def test_becoming_optional_is_safe_and_changes_nothing_stored(clear_database):
    old_models, old = declare(versions(one, one))
    place = await old_models.Place.Create(label="Vienna").save()
    person = await old_models.Person.Create(
        label="P",
        home={"type": "Place", "id": place.id},
        born={"type": "Day", "year": 1500},
    ).save()
    new_models, new = declare(versions(optional, optional))

    changes = await migrate(old, new)
    assert {(c.kind, c.name, c.nullable) for c in changes} == {
        ("AlterNullability", "home", True),
        ("AlterNullability", "born", True),
    }
    assert all(c.safety == "safe" for c in changes)

    read = await new_models.Person.get(person.id)
    assert read.home.id == place.id and read.born.year == 1500
    assert (await new_models.Person.Create(label="Q").save()).id


@no_type_check
async def test_becoming_required_fails_naming_how_many_have_none_and_passes_when_all_have_one(
    clear_database,
):
    old_models, old = declare(versions(optional, optional))
    place = await old_models.Place.Create(label="Vienna").save()
    await old_models.Person.Create(
        label="Has",
        home={"type": "Place", "id": place.id},
        born={"type": "Day", "year": 1500},
    ).save()
    without = await old_models.Person.Create(label="Has not").save()
    _, new = declare(versions(one, one))

    with pytest.raises(PanglossMigrationNotSupported, match="1 nodes have none"):
        await migrate(old, new)

    old_models, _ = declare(versions(optional, optional))
    await old_models.Person.Update(
        id=without.id,
        label="Has now",
        home={"type": "Place", "id": place.id},
        born={"type": "Day", "year": 1},
    ).save()
    new_models, new = declare(versions(one, one))
    await migrate(old, new)
    assert (await new_models.Person.get(without.id)).home.id == place.id


@no_type_check
async def test_a_list_that_becomes_an_optional_single_relation_keeps_one(
    clear_database,
):
    old_models, old = declare(versions(many, one))
    first = await old_models.Place.Create(label="First").save()
    second = await old_models.Place.Create(label="Second").save()
    both = await old_models.Person.Create(
        label="Both",
        home=[{"type": "Place", "id": first.id}, {"type": "Place", "id": second.id}],
        born={"type": "Day", "year": 1},
    ).save()
    none = await old_models.Person.Create(
        label="None", home=[], born={"type": "Day", "year": 1}
    ).save()
    new_models, new = declare(versions(optional, one))

    changes = await migrate(
        old, new, answer=with_answers(AlterCardinality={"keep": "first"})
    )
    assert any(isinstance(c, AlterNullability) and c.nullable for c in changes)
    assert (await new_models.Person.get(both.id)).home.id == first.id
    assert (await new_models.Person.get(none.id)).home is None


@no_type_check
async def test_an_optional_relation_that_becomes_a_list_is_not_checked(clear_database):
    old_models, old = declare(versions(optional, one))
    person = await old_models.Person.Create(
        label="None", born={"type": "Day", "year": 1}
    ).save()
    new_models, new = declare(versions(many, one))

    await migrate(old, new)
    assert (await new_models.Person.get(person.id)).home == []
