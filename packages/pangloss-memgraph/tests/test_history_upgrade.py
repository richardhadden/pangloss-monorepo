"""Upgrading a stored version (`pangloss-history`): the document function of each change is
checked against the Cypher operation. The same data is written with the old models, then
(a) migrated in the database and read with the new models, and (b) upgraded as a stored version
and validated as an `Update` of the new models: both must say the same."""

import json
from enum import Enum
from types import SimpleNamespace as ns
from typing import no_type_check

import pytest
from pangloss_history.upgrade import apply_migrations
from pangloss_models import hooks
from pangloss_models.meta_kit.migrations import PossibleRename
from pangloss_models.meta_kit.migrations.files import Migration
from pangloss_models.meta_kit.migrations.snapshot import data_view
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity

from .migration_support import declare, migrate, with_answers

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.fixture
def written():
    """What is written, as JSON, by id (what history stores)"""
    stored: dict[str, dict] = {}

    def keep(event):
        stored[str(event.id)] = json.loads(event.payload.model_dump_json())

    hooks.after_write.append(keep)
    yield stored
    hooks.after_write.remove(keep)


def same(value):
    """A reference is its type and id (a view of it has a label as well)"""
    if isinstance(value, list):
        return [same(v) for v in value]
    if hasattr(value, "id") and hasattr(value, "type"):
        return (value.type, value.id)
    return value


async def both_ways(
    written, old, old_models, new_models, new, saved, model, fields, **migration
):
    """Migrate the database and upgrade the stored version; check that they agree on `fields`.
    Returns the problems of the upgrade."""
    changes = await migrate(old, new, **migration)
    result = apply_migrations(
        written[str(saved.id)],
        data_view(old),
        [Migration(app="t", name="0002_change", changes=tuple(changes))],
    )
    model = getattr(new_models, model)
    read = await model.get(id=saved.id)
    upgraded = model.Update.model_validate(result.data)
    for name in fields:
        assert same(getattr(upgraded, name)) == same(getattr(read, name)), name
    return result.problems


@no_type_check
async def test_a_field_that_is_added_has_the_value_the_migration_gave(
    db_driver, clear_database, written
):
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

    problems = await both_ways(
        written,
        old,
        old_models,
        new_models,
        new,
        saved,
        "Person",
        ["name", "born"],
        answer=with_answers(AddField={"default": 1900}),
    )
    assert problems == []


@no_type_check
async def test_a_field_that_is_removed_is_dropped_and_said(
    db_driver, clear_database, written
):
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

    problems = await both_ways(
        written,
        old,
        old_models,
        new_models,
        new,
        saved,
        "Person",
        ["name", "title"],
        declined=[
            PossibleRename(what="field", scope="Person", old="nickname", new="title")
        ],
    )
    (problem,) = problems
    assert (problem.kind, problem.path, problem.old_value, problem.blocking) == (
        "removed-field",
        "nickname",
        "A",
        False,
    )


@no_type_check
async def test_a_renamed_field_keeps_its_value(db_driver, clear_database, written):
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

    problems = await both_ways(
        written,
        old,
        old_models,
        new_models,
        new,
        saved,
        "Person",
        ["birth_year"],
        confirmed=[
            PossibleRename(what="field", scope="Person", old="born", new="birth_year")
        ],
    )
    assert problems == []


@no_type_check
@pytest.mark.parametrize(
    "age, answer, expected",
    [
        ("42", {}, 42),
        ("forty", {"on_failure": "default", "default": -1}, -1),
        ("forty", {"on_failure": "null"}, None),
    ],
)
async def test_a_value_is_converted_as_the_database_converts_it(
    db_driver, clear_database, written, age, answer, expected
):
    def v1():
        class Person(Entity):
            age: str | None

        return ns(Person=Person)

    def v2():
        class Person(Entity):
            age: int | None

        return ns(Person=Person)

    old_models, old = declare(v1)
    saved = await old_models.Person.Create(label="Ann", age=age).save()
    new_models, new = declare(v2)

    problems = await both_ways(
        written,
        old,
        old_models,
        new_models,
        new,
        saved,
        "Person",
        ["age"],
        answer=with_answers(AlterLiteralType=answer),
    )
    assert problems == []
    assert (await new_models.Person.get(id=saved.id)).age == expected


@no_type_check
async def test_a_value_that_cannot_be_converted_is_a_problem_when_the_migration_would_fail(
    db_driver, clear_database, written
):
    def v1():
        class Person(Entity):
            age: str

        return ns(Person=Person)

    def v2():
        class Person(Entity):
            age: int

        return ns(Person=Person)

    old_models, old = declare(v1)
    saved = await old_models.Person.Create(label="Ann", age="forty").save()
    new_models, new = declare(v2)
    # (the migration is not applied to the database; only its changes are used)
    from pangloss_models.meta_kit.migrations import diff

    changes = diff(old, new).changes
    result = apply_migrations(
        written[str(saved.id)],
        data_view(old),
        [Migration(app="t", name="0002", changes=tuple(changes))],
    )
    (problem,) = result.problems
    assert (problem.kind, problem.path, problem.old_value, problem.blocking) == (
        "type-changed",
        "age",
        "forty",
        True,
    )
    assert result.data["age"] == "forty"  # (left as it was, for the person to decide)


def shade(**members):
    return Enum("Shade", members)


def shade_models(enum):
    class Person(Entity):
        favourite: enum
        others: list[enum]

    return ns(Person=Person)


@no_type_check
async def test_enum_values_are_mapped_when_a_member_changes_value_or_goes(
    db_driver, clear_database, written
):
    old_enum = shade(RED="red", GREEN="green", BLUE="blue")
    old_models, old = declare(lambda: shade_models(old_enum))
    saved = await old_models.Person.Create(
        label="Ann", favourite=old_enum.GREEN, others=[old_enum.GREEN, old_enum.BLUE]
    ).save()

    new_enum = shade(RED="red", GREEN="verde", BLUE="blue")
    new_models, new = declare(lambda: shade_models(new_enum))
    problems = await both_ways(
        written,
        old,
        old_models,
        new_models,
        new,
        saved,
        "Person",
        ["favourite", "others"],
    )
    assert problems == []


@no_type_check
async def test_a_member_that_goes_gives_its_values_to_the_replacement(
    db_driver, clear_database, written
):
    old_enum = shade(RED="red", GREEN="green", BLUE="blue")
    old_models, old = declare(lambda: shade_models(old_enum))
    saved = await old_models.Person.Create(
        label="Ann", favourite=old_enum.GREEN, others=[old_enum.GREEN, old_enum.BLUE]
    ).save()

    new_enum = shade(RED="red", BLUE="blue")
    new_models, new = declare(lambda: shade_models(new_enum))
    problems = await both_ways(
        written,
        old,
        old_models,
        new_models,
        new,
        saved,
        "Person",
        ["favourite", "others"],
        answer=with_answers(RemoveEnumMember={"replacement": "RED"}),
    )
    assert problems == []


@no_type_check
async def test_a_field_that_may_no_longer_be_null_is_given_the_default(
    db_driver, clear_database, written
):
    def v1():
        class Person(Entity):
            born: int | None

        return ns(Person=Person)

    def v2():
        class Person(Entity):
            born: int

        return ns(Person=Person)

    old_models, old = declare(v1)
    saved = await old_models.Person.Create(label="Ann", born=None).save()
    new_models, new = declare(v2)

    problems = await both_ways(
        written,
        old,
        old_models,
        new_models,
        new,
        saved,
        "Person",
        ["born"],
        answer=with_answers(AlterNullability={"default": 1900}),
    )
    assert problems == []


@no_type_check
async def test_a_renamed_model_is_renamed_in_the_document_and_in_what_refers_to_it(
    db_driver, clear_database, written
):
    def v1():
        class Place(Entity):
            pass

        class Statement(Document):
            text: str
            where: Place

        return ns(Place=Place, Statement=Statement)

    def v2():
        class Location(Entity):
            pass

        class Statement(Document):
            text: str
            where: Location

        return ns(Location=Location, Statement=Statement)

    old_models, old = declare(v1)
    place = await old_models.Place.Create(label="Rome").save()
    saved = await old_models.Statement.Create(
        label="S", text="t", where={"type": "Place", "id": place.id}
    ).save()
    new_models, new = declare(v2)

    problems = await both_ways(
        written,
        old,
        old_models,
        new_models,
        new,
        saved,
        "Statement",
        ["text", "where"],
        confirmed=[PossibleRename(what="model", old="Place", new="Location")],
    )
    assert problems == []


@no_type_check
async def test_a_list_that_becomes_a_single_value_keeps_the_one(
    db_driver, clear_database, written
):
    def v1():
        class Place(Entity):
            pass

        class Statement(Document):
            where: list[Place]

        return ns(Place=Place, Statement=Statement)

    def v2():
        class Place(Entity):
            pass

        class Statement(Document):
            where: Place

        return ns(Place=Place, Statement=Statement)

    old_models, old = declare(v1)
    place = await old_models.Place.Create(label="Rome").save()
    saved = await old_models.Statement.Create(
        label="S", where=[{"type": "Place", "id": place.id}]
    ).save()
    new_models, new = declare(v2)

    problems = await both_ways(
        written,
        old,
        old_models,
        new_models,
        new,
        saved,
        "Statement",
        [],
        answer=with_answers(AlterCardinality={"keep": "first"}),
    )
    assert problems == []
