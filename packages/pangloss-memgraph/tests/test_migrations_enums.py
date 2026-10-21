"""Enums are stored as the values of their members: changing a member, or the enum, is a change
to data like any other, wherever the value is kept (a field, a list, a `TypedDict`, an annotated
value, an edge)"""

from enum import Enum
from types import SimpleNamespace as ns
from typing import TypedDict, no_type_check

import pytest
from pangloss_models.exceptions import PanglossMigrationAnswerNeeded, PanglossMigrationNotSupported
from pangloss_models.migrations import PossibleRename
from pangloss_models.model_bases.annotated_value import AnnotatedValue
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.edge_model import EdgeModel
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.helpers import ViaEdge

from .helpers import run
from .migration_support import declare, migrate, with_answers

pytestmark = pytest.mark.asyncio(loop_scope="session")


def shade(**members: str) -> type[Enum]:
    return Enum("Shade", members)


def models(enum: type[Enum]):
    """A model that keeps the enum in every place it can be kept"""

    def declare_models():
        class Sizes(TypedDict):
            shade: enum
            shades: list[enum]
            other: str

        class Weighted[T](AnnotatedValue[T]):
            shade: enum

        class Certainty(EdgeModel):
            shade: enum

        class Person(Entity):
            pass

        class Statement(Document):
            favourite: enum
            others: list[enum]
            sizes: Sizes
            note: Weighted[str]
            about: ViaEdge[Person, Certainty]

        return ns(Person=Person, Statement=Statement)

    return declare_models


async def write_one(models_, name: str, first, second):
    person = await models_.Person.Create(label="P").save()
    return await models_.Statement.Create(
        label=name,
        favourite=first,
        others=[first, second, first],
        sizes={"shade": first, "shades": [second, first], "other": "green"},
        note={"value": "green", "shade": first},
        about={
            "type": "Person",
            "id": person.id,
            "edge_properties": {"shade": first},
        },
    ).save()


def stored(db_driver) -> dict:
    node = run(db_driver, "MATCH (n:Statement) RETURN n")[0]["n"]
    edges = run(db_driver, "MATCH ()-[e:about]->() RETURN e.shade AS shade")
    reverse = run(db_driver, "MATCH ()-[e:about_reverse]->() RETURN e.shade AS shade")
    return {
        "favourite": node["favourite"],
        "others": node["others"],
        "sizes": node["sizes"],
        "note": node["note"],
        "edge": edges[0]["shade"],
        "reverse": reverse[0]["shade"],
    }


V1 = {"RED": "red", "GREEN": "green", "BLUE": "blue"}


@no_type_check
async def test_a_value_that_changes_is_changed_wherever_it_is_stored(db_driver, clear_database):
    old_enum, new_enum = shade(**V1), shade(**{**V1, "GREEN": "verde"})
    old_models, old = declare(models(old_enum))
    saved = await write_one(old_models, "S", old_enum.GREEN, old_enum.BLUE)
    new_models, new = declare(models(new_enum))

    changes = await migrate(old, new)
    assert [c.kind for c in changes] == ["AlterEnumMemberValue"]

    assert stored(db_driver) == {
        "favourite": "verde",
        "others": ["verde", "blue", "verde"],
        # (what is not the enum is not touched: the text "green" stays)
        "sizes": {"shade": "verde", "shades": ["blue", "verde"], "other": "green"},
        "note": {"value": "green", "shade": "verde"},
        "edge": "verde",
        "reverse": "verde",
    }
    read = await new_models.Statement.get(id=saved.id)
    assert read.favourite is new_enum.GREEN
    assert [m.name for m in read.others] == ["GREEN", "BLUE", "GREEN"]
    assert read.sizes["shade"] is new_enum.GREEN
    assert read.note.shade is new_enum.GREEN and read.note.value == "green"


@no_type_check
async def test_values_that_are_taken_off_a_member_go_to_the_one_it_is_given(db_driver, clear_database):
    old_enum, new_enum = shade(**V1), shade(RED="red", BLUE="blue")
    old_models, old = declare(models(old_enum))
    saved = await write_one(old_models, "S", old_enum.GREEN, old_enum.BLUE)
    new_models, new = declare(models(new_enum))

    # (it has values: where, and how many, are said)
    with pytest.raises(PanglossMigrationAnswerNeeded, match=r"Statement\.favourite.*replacement"):
        await migrate(old, new)

    await migrate(old, new, answer=with_answers(RemoveEnumMember={"replacement": "RED"}))
    assert stored(db_driver) == {
        "favourite": "red",
        "others": ["red", "blue", "red"],
        "sizes": {"shade": "red", "shades": ["blue", "red"], "other": "green"},
        "note": {"value": "green", "shade": "red"},
        "edge": "red",
        "reverse": "red",
    }
    read = await new_models.Statement.get(id=saved.id)
    assert read.favourite is new_enum.RED


@no_type_check
async def test_a_member_with_no_values_can_go_without_an_answer(db_driver, clear_database):
    old_enum, new_enum = shade(**V1), shade(RED="red", GREEN="green")
    old_models, old = declare(models(old_enum))
    saved = await write_one(old_models, "S", old_enum.GREEN, old_enum.RED)
    new_models, new = declare(models(new_enum))

    await migrate(old, new)
    assert (await new_models.Statement.get(id=saved.id)).favourite is new_enum.GREEN


@no_type_check
async def test_a_member_renamed_with_its_value_changes_no_data(db_driver, clear_database):
    old_enum, new_enum = shade(**V1), shade(RED="red", LIME="green", BLUE="blue")
    old_models, old = declare(models(old_enum))
    saved = await write_one(old_models, "S", old_enum.GREEN, old_enum.BLUE)
    before = stored(db_driver)
    new_models, new = declare(models(new_enum))

    changes = await migrate(old, new)
    assert [c.kind for c in changes] == ["RenameEnumMember"]
    assert stored(db_driver) == before
    assert (await new_models.Statement.get(id=saved.id)).favourite is new_enum.LIME


@no_type_check
async def test_a_member_renamed_and_given_another_value_is_both(db_driver, clear_database):
    old_enum, new_enum = shade(**V1), shade(RED="red", LIME="lime", BLUE="blue")
    old_models, old = declare(models(old_enum))
    saved = await write_one(old_models, "S", old_enum.GREEN, old_enum.BLUE)
    new_models, new = declare(models(new_enum))

    rename = PossibleRename(what="enum_member", scope="Shade", old="GREEN", new="LIME")
    changes = await migrate(old, new, confirmed=[rename])
    assert [c.kind for c in changes] == ["RenameEnumMember", "AlterEnumMemberValue"]
    assert stored(db_driver)["favourite"] == "lime"
    assert (await new_models.Statement.get(id=saved.id)).favourite is new_enum.LIME


@no_type_check
async def test_a_renamed_enum_changes_no_data(db_driver, clear_database):
    old_enum = shade(**V1)
    new_enum = Enum("Hue", V1)
    old_models, old = declare(models(old_enum))
    saved = await write_one(old_models, "S", old_enum.GREEN, old_enum.BLUE)
    before = stored(db_driver)
    new_models, new = declare(models(new_enum))

    rename = PossibleRename(what="enum", old="Shade", new="Hue")
    changes = await migrate(old, new, confirmed=[rename])
    assert [c.kind for c in changes] == ["RenameEnum"]
    assert stored(db_driver) == before
    assert (await new_models.Statement.get(id=saved.id)).favourite is new_enum.GREEN


# ---------------------------------------------------------------------------
# Converting to and from an enum
# ---------------------------------------------------------------------------


def one_field(annotation):
    def declare_models():
        class Item(Entity):
            kind: annotation

        return ns(Item=Item)

    return declare_models


@no_type_check
async def test_a_string_becomes_an_enum_and_back(db_driver, clear_database):
    enum = Enum("Kind", {"BIG": "big", "SMALL": "small"})
    old_models, old = declare(one_field(str))
    good = await old_models.Item.Create(label="a", kind="big").save()
    bad = await old_models.Item.Create(label="b", kind="medium").save()
    new_models, new = declare(one_field(enum))

    # (one of them is not a member: that is said before anything changes)
    with pytest.raises(PanglossMigrationAnswerNeeded, match="cannot be converted"):
        await migrate(old, new)
    assert run(db_driver, "MATCH (i:Item) WHERE i.kind = 'medium' RETURN count(i) AS n") == [{"n": 1}]

    await migrate(old, new, answer=with_answers(AlterLiteralType={"on_failure": "default", "default": "small"}))
    assert (await new_models.Item.get(id=good.id)).kind is enum.BIG
    assert (await new_models.Item.get(id=bad.id)).kind is enum.SMALL

    # ... and back: the value is the text
    again_models, again = declare(one_field(str))
    await migrate(new, again)
    assert (await again_models.Item.get(id=good.id)).kind == "big"


@no_type_check
async def test_one_enum_becomes_another_by_the_names_of_the_members_or_a_mapping(db_driver, clear_database):
    old_enum = Enum("Kind", {"BIG": "b", "SMALL": "s"})
    new_enum = Enum("Size", {"BIG": "large", "TINY": "tiny"})
    old_models, old = declare(one_field(old_enum))
    big = await old_models.Item.Create(label="a", kind=old_enum.BIG).save()
    small = await old_models.Item.Create(label="b", kind=old_enum.SMALL).save()
    new_models, new = declare(one_field(new_enum))

    # (not a rename of the enum)
    declined = [PossibleRename(what="enum", old="Kind", new="Size")]
    # BIG is BIG (its value changes with it); SMALL has no member of that name
    with pytest.raises(PanglossMigrationAnswerNeeded, match="cannot be converted"):
        await migrate(old, new, declined=declined)

    await migrate(
        old, new, declined=declined, answer=with_answers(AlterLiteralType={"mapping": {"SMALL": "TINY"}})
    )
    assert (await new_models.Item.get(id=big.id)).kind is new_enum.BIG
    assert (await new_models.Item.get(id=small.id)).kind is new_enum.TINY
    assert run(db_driver, "MATCH (i:Item) RETURN i.kind AS k ORDER BY k") == [{"k": "large"}, {"k": "tiny"}]


@no_type_check
async def test_a_mapping_to_a_member_that_is_not_there_is_refused(db_driver, clear_database):
    old_enum = Enum("Kind", {"BIG": "b"})
    new_enum = Enum("Size", {"HUGE": "h"})
    old_models, old = declare(one_field(old_enum))
    await old_models.Item.Create(label="a", kind=old_enum.BIG).save()
    _, new = declare(one_field(new_enum))
    with pytest.raises(PanglossMigrationNotSupported, match="not between members"):
        await migrate(
            old,
            new,
            declined=[PossibleRename(what="enum", old="Kind", new="Size")],
            answer=with_answers(AlterLiteralType={"mapping": {"BIG": "NOPE"}}),
        )


@no_type_check
async def test_an_enum_of_numbers_is_stored_as_numbers(db_driver, clear_database):
    enum = Enum("Level", {"LOW": 1, "HIGH": 2})
    bigger = Enum("Level", {"LOW": 1, "HIGH": 20})
    old_models, old = declare(one_field(enum))
    saved = await old_models.Item.Create(label="a", kind=enum.HIGH).save()
    assert run(db_driver, "MATCH (i:Item) RETURN i.kind AS k") == [{"k": 2}]

    new_models, new = declare(one_field(bigger))
    await migrate(old, new)
    assert run(db_driver, "MATCH (i:Item) RETURN i.kind AS k") == [{"k": 20}]
    assert (await new_models.Item.get(id=saved.id)).kind is bigger.HIGH
