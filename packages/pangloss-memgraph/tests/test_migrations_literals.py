"""Applying changes to literal fields: data written with the old models, migrated,
and read with the new"""

from enum import Enum
from types import SimpleNamespace as ns
from typing import Annotated, no_type_check

import pytest
from pangloss_memgraph.databases.memgraph.database import Database
from pangloss_models.exceptions import PanglossMigrationAnswerNeeded
from pangloss_models.migrations import PossibleRename
from pangloss_models.model_bases.annotated_value import AnnotatedValue
from pangloss_models.model_bases.entity import Entity

from .helpers import run
from .migration_support import declare, migrate, with_answers

pytestmark = pytest.mark.asyncio(loop_scope="session")


# ---------------------------------------------------------------------------
# Adding, removing and renaming
# ---------------------------------------------------------------------------


@no_type_check
async def test_a_required_field_is_given_a_value_for_what_exists(db_driver, clear_database):
    def v1():
        class Person(Entity):
            name: str

        return ns(Person=Person)

    def v2():
        class Person(Entity):
            name: str
            born: int

        return ns(Person=Person)

    old_models, old = declare(v1)
    saved = await old_models.Person.Create(label="Ann", name="Ann").save()
    new_models, new = declare(v2)

    # (it needs an answer, and says so)
    with pytest.raises(PanglossMigrationAnswerNeeded, match="value for the nodes that exist"):
        await migrate(old, new)

    await migrate(old, new, answer=with_answers(AddField={"default": 1900}))
    read = await new_models.Person.get(id=saved.id)
    assert (read.name, read.born) == ("Ann", 1900)


@no_type_check
async def test_an_optional_field_is_added_and_a_field_removed(db_driver, clear_database):
    def v1():
        class Person(Entity):
            name: str
            nickname: str | None

        return ns(Person=Person)

    def v2():
        class Person(Entity):
            name: str
            title: str | None

        return ns(Person=Person)

    old_models, old = declare(v1)
    saved = await old_models.Person.Create(label="Ann", name="Ann", nickname="A").save()
    new_models, new = declare(v2)
    # (nickname and title: a removal and an addition, as the answer is that it is not a rename)
    not_a_rename = PossibleRename(what="field", scope="Person", old="nickname", new="title")
    await migrate(old, new, declined=[not_a_rename])

    props = run(db_driver, "MATCH (p:Person) RETURN properties(p) AS p")[0]["p"]
    assert "nickname" not in props
    read = await new_models.Person.get(id=saved.id)
    assert read.title is None


@no_type_check
async def test_a_renamed_field_keeps_its_values(db_driver, clear_database):
    def v1():
        class Person(Entity):
            born: int

        return ns(Person=Person)

    def v2():
        class Person(Entity):
            birth_year: int

        return ns(Person=Person)

    old_models, old = declare(v1)
    saved = await old_models.Person.Create(label="Ann", born=1900).save()
    new_models, new = declare(v2)

    rename = PossibleRename(what="field", scope="Person", old="born", new="birth_year")
    await migrate(old, new, confirmed=[rename])

    read = await new_models.Person.get(id=saved.id)
    assert read.birth_year == 1900


@no_type_check
async def test_a_field_that_may_no_longer_be_null(db_driver, clear_database):
    def v1():
        class Person(Entity):
            born: int | None

        return ns(Person=Person)

    def v2():
        class Person(Entity):
            born: int

        return ns(Person=Person)

    old_models, old = declare(v1)
    with_value = await old_models.Person.Create(label="Ann", born=1900).save()
    without = await old_models.Person.Create(label="Bob", born=None).save()
    new_models, new = declare(v2)

    with pytest.raises(PanglossMigrationAnswerNeeded):
        await migrate(old, new)
    await migrate(old, new, answer=with_answers(AlterNullability={"default": 0}))

    assert (await new_models.Person.get(id=with_value.id)).born == 1900
    assert (await new_models.Person.get(id=without.id)).born == 0


# ---------------------------------------------------------------------------
# Changing a type
# ---------------------------------------------------------------------------


@no_type_check
async def test_a_type_is_converted(db_driver, clear_database):
    def v1():
        class Person(Entity):
            age: str
            weights: list[str]

        return ns(Person=Person)

    def v2():
        class Person(Entity):
            age: int
            weights: list[float]

        return ns(Person=Person)

    old_models, old = declare(v1)
    saved = await old_models.Person.Create(label="Ann", age="42", weights=["1.5", "2"]).save()
    new_models, new = declare(v2)
    await migrate(old, new)

    read = await new_models.Person.get(id=saved.id)
    assert read.age == 42
    assert read.weights == [1.5, 2.0]


@no_type_check
async def test_what_does_not_convert_has_to_be_dealt_with(db_driver, clear_database):
    def v1():
        class Person(Entity):
            age: str

        return ns(Person=Person)

    def v2():
        class Person(Entity):
            age: int

        return ns(Person=Person)

    old_models, old = declare(v1)
    good = await old_models.Person.Create(label="Ann", age="42").save()
    bad = await old_models.Person.Create(label="Bob", age="forty").save()
    new_models, new = declare(v2)

    # by default it fails, and nothing is changed
    with pytest.raises(PanglossMigrationAnswerNeeded, match="1 values of Person.age"):
        await migrate(old, new)
    ages = run(db_driver, "MATCH (p:Person) RETURN p.age AS age ORDER BY age")
    assert [row["age"] for row in ages] == ["42", "forty"]

    await migrate(old, new, answer=with_answers(AlterLiteralType={"on_failure": "default", "default": -1}))
    assert (await new_models.Person.get(id=good.id)).age == 42
    assert (await new_models.Person.get(id=bad.id)).age == -1


@no_type_check
async def test_what_does_not_convert_can_be_dropped(db_driver, clear_database):
    def v1():
        class Person(Entity):
            age: str | None

        return ns(Person=Person)

    def v2():
        class Person(Entity):
            age: int | None

        return ns(Person=Person)

    old_models, old = declare(v1)
    bad = await old_models.Person.Create(label="Bob", age="forty").save()
    new_models, new = declare(v2)
    await migrate(old, new, answer=with_answers(AlterLiteralType={"on_failure": "null"}))
    assert (await new_models.Person.get(id=bad.id)).age is None


@no_type_check
async def test_a_field_becomes_an_annotated_value_and_back(db_driver, clear_database):
    def v1():
        class Person(Entity):
            name: str

        return ns(Person=Person)

    def v2():
        class WithCertainty[T](AnnotatedValue[T]):
            certainty: int

        class Person(Entity):
            name: WithCertainty[str]

        return ns(Person=Person)

    old_models, old = declare(v1)
    saved = await old_models.Person.Create(label="Ann", name="Ann").save()
    new_models, new = declare(v2)

    with pytest.raises(PanglossMigrationAnswerNeeded, match="certainty"):
        await migrate(old, new)
    await migrate(old, new, answer=with_answers(LiteralToAnnotatedValue={"defaults": {"certainty": 3}}))
    read = await new_models.Person.get(id=saved.id)
    assert (read.name.value, read.name.certainty) == ("Ann", 3)

    # ... and back
    await migrate(new, old)
    assert (await old_models.Person.get(id=saved.id)).name == "Ann"  # (the extra field is lost)
    props = run(db_driver, "MATCH (p:Person) RETURN p.name AS name")
    assert props == [{"name": "Ann"}]


@no_type_check
async def test_a_list_that_is_needed_starts_empty(db_driver, clear_database):
    def v1():
        class Person(Entity):
            name: str

        return ns(Person=Person)

    def v2():
        class Person(Entity):
            name: str
            aliases: list[str]

        return ns(Person=Person)

    old_models, old = declare(v1)
    saved = await old_models.Person.Create(label="Ann", name="Ann").save()
    new_models, new = declare(v2)
    await migrate(old, new)  # (no answer: it is not asked for)
    assert (await new_models.Person.get(id=saved.id)).aliases == []
