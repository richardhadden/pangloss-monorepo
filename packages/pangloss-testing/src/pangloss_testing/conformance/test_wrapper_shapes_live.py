"""Shapes of wrappers that once failed: a generic wrapper with a relation of its own through another wrapper
(`office: Negative[RoleType] | None`), and a class with no parameters below a use of a wrapper
(`class JohnRole(InRole[Person])`). Each is written, read, read from the entity it reaches, updated and searched."""

from typing import no_type_check

import pytest
from pangloss_models import (
    Document,
    Entity,
    Match,
    ReifiedRelation,
    SemanticSpace,
    initialise,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


def ref(item):
    return {"type": item.type, "id": item.id}


def labels(found):
    return sorted(item.label for item in found.results)


@no_type_check
async def test_a_wrapper_with_a_relation_of_its_own_through_another_wrapper(
    clear_database,
):
    class RoleType(Entity):
        pass

    class Person(Entity):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    class Sure[T](ReifiedRelation[T]):
        how: int = 0

    class InOffice[T](ReifiedRelation[T]):
        office: Negative[RoleType] | None = None
        ranks: list[Sure[RoleType]] = []

    class Doc(Document):
        who: list[InOffice[Person]]

    initialise()
    john = await Person.Create(label="John").save()
    baker = await RoleType.Create(label="baker").save()
    miller = await RoleType.Create(label="miller").save()

    def in_office(person, office=None, ranks=()):
        made = {
            "type": "InOffice",
            "target": [ref(person)],
            "ranks": [
                {"type": "Sure", "how": how, "target": [ref(rank)]}
                for rank, how in ranks
            ],
        }
        if office is not None:
            made["office"] = {"type": "Negative", "contents": [ref(office)]}
        return made

    doc = await Doc.Create(
        label="not a baker",
        who=[in_office(john, baker, [(miller, 7)])],
    ).save()
    await Doc.Create(label="no office", who=[in_office(john)]).save()

    read = await Doc.get(doc.id)
    (who,) = read.who
    assert who.type == "InOffice" and who.target[0].label == "John"
    assert who.office.type == "Negative"
    assert [c.label for c in who.office.contents] == ["baker"]
    assert [(r.how, r.target[0].label) for r in who.ranks] == [(7, "miller")]

    # (the entity the relation reaches reads the document back; so does the one the wrapper's own relation reaches)
    back = await Person.get(john.id)
    assert sorted(d.label for d in back.who_reverse) == ["no office", "not a baker"]
    await RoleType.get(baker.id)
    await RoleType.get(miller.id)

    # (written again with other values)
    edit = await Doc.get_for_edit(doc.id) if hasattr(Doc, "get_for_edit") else read
    await Doc.Update(
        id=doc.id,
        label="not a miller",
        who=[in_office(john, miller, [(baker, 3), (miller, 9)])],
    ).save()
    read = await Doc.get(doc.id)
    assert [c.label for c in read.who[0].office.contents] == ["miller"]
    assert [(r.how, r.target[0].label) for r in read.who[0].ranks] == [
        (3, "baker"),
        (9, "miller"),
    ]
    assert edit is not None

    assert labels(await Doc.search(Match(where={"who": {"is": str(john.id)}}))) == [
        "no office",
        "not a miller",
    ]
    assert labels(
        await Doc.search(Match(where={"$mentions": {"is": str(baker.id)}}))
    ) == ["not a miller"]


@no_type_check
async def test_a_class_with_no_parameters_below_a_use_of_a_wrapper(clear_database):
    class Person(Entity):
        pass

    class InRole[T](ReifiedRelation[T]):
        role: str | None = None

    class JohnRole(InRole[Person]):
        extra: int = 0

    class Doc(Document):
        john: list[JohnRole]
        either: list[Person | InRole[Person] | JohnRole]

    initialise()
    john = await Person.Create(label="John").save()
    jane = await Person.Create(label="Jane").save()

    def role(type_, person, **values):
        return {"type": type_, "target": [ref(person)], **values}

    doc = await Doc.Create(
        label="john as scribe",
        john=[role("JohnRole", john, role="scribe", extra=2)],
        either=[],
    ).save()
    await Doc.Create(
        label="mixed",
        john=[],
        either=[
            ref(jane),
            role("InRole", john, role="notary"),
            role("JohnRole", jane, role="scribe", extra=5),
        ],
    ).save()

    read = await Doc.get(doc.id)
    (held,) = read.john
    assert (held.type, held.role, held.extra) == ("JohnRole", "scribe", 2)
    assert held.target[0].label == "John"
    mixed = (await Doc.search(Match(where={"label": {"eq": "mixed"}}))).results[0]
    mixed = await Doc.get(mixed.id)
    assert [item.type for item in mixed.either] == ["Person", "InRole", "JohnRole"]
    assert mixed.either[2].extra == 5

    back = await Person.get(john.id)
    assert [d.label for d in back.john_reverse] == ["john as scribe"]
    assert [d.label for d in back.either_reverse] == ["mixed"]

    await Doc.Update(
        id=doc.id,
        label="john as notary",
        john=[role("JohnRole", john, role="notary", extra=3)],
        either=[],
    ).save()
    read = await Doc.get(doc.id)
    assert (read.john[0].role, read.john[0].extra) == ("notary", 3)

    async def found(where):
        return labels(await Doc.search(Match(where=where)))

    assert await found({"john": {"is": str(john.id)}}) == ["john as notary"]
    assert await found({"john": {"exists": True}}) == ["john as notary"]
    step = {"type": "JohnRole", "where": {"extra": {"gte": 3}}}
    assert await found({"john": {"through": [step]}}) == ["john as notary"]
    assert await found({"john": {"via": [step]}}) == ["john as notary"]
    assert await found({"either": {"via": [step]}}) == ["mixed"]
    # (a `JohnRole` is an `InRole`: asked for by the class above it, both are found)
    scribe = {"type": "InRole", "where": {"role": {"eq": "scribe"}}}
    assert await found({"either": {"is": str(jane.id), "via": [scribe]}}) == ["mixed"]
    assert await found({"$mentions": {"is": str(john.id)}}) == [
        "john as notary",
        "mixed",
    ]


@no_type_check
async def test_a_wrapper_is_found_by_its_class_or_one_above_it(clear_database):
    """(a node of a wrapper has the label of its own class, not of the wrapper its class is a kind of: asked for by
    the class above, in `through`, in a step or in `via`, the classes below it are looked for too)"""

    class Person(Entity):
        pass

    class InRole[T](ReifiedRelation[T]):
        role: str | None = None

    class Finer[T](InRole[T]):
        fine: int = 0

    class Negative[T](SemanticSpace[T]):
        pass

    class Strongly[T](Negative[T]):
        pass

    class Doc(Document):
        who: list[Person | InRole[Person] | Finer[Person]]
        not_who: list[Negative[Person] | Strongly[Person]]

    initialise()
    john = await Person.Create(label="John").save()

    def role(type_, **values):
        return {"type": type_, "target": [ref(john)], **values}

    def space(type_):
        return {"type": type_, "contents": [ref(john)]}

    await Doc.Create(label="in role", who=[role("InRole", role="a")], not_who=[]).save()
    await Doc.Create(
        label="finer", who=[role("Finer", role="a", fine=2)], not_who=[]
    ).save()
    await Doc.Create(label="direct", who=[ref(john)], not_who=[]).save()
    await Doc.Create(label="negative", who=[], not_who=[space("Negative")]).save()
    await Doc.Create(label="strongly", who=[], not_who=[space("Strongly")]).save()

    async def found(where, **match):
        return labels(await Doc.search(Match(where=where, **match)))

    both = ["finer", "in role"]
    assert await found({"who": {"through": ["InRole"]}}) == both
    assert await found({"who": {"through": ["Finer"]}}) == ["finer"]
    step = {"type": "InRole", "where": {"role": {"eq": "a"}}}
    assert await found({"who": {"through": [step]}}) == both
    assert await found({"who": {"via": [step]}}) == both
    assert await found({"who": {"via": [{"type": "InRole"}]}}) == both
    assert await found({"who": {"via": [{"type": "Finer"}]}}) == ["finer"]
    assert await found({"$mentions": {"is": str(john.id), "via": [step]}}) == both
    assert await found({"not_who": {"through": ["Negative"]}}) == [
        "negative",
        "strongly",
    ]
    assert await found({"not_who": {"via": [{"type": "Strongly"}]}}) == ["strongly"]
    # (and what refers to the entity)
    people = await Person.search(
        Match(
            where={
                "$incoming": [
                    {"type": "Doc", "field": "who", "through": ["InRole"]},
                    {"type": "Doc", "field": "who", "via": [{"type": "InRole"}]},
                ]
            }
        )
    )
    assert labels(people) == ["John"]
    # (left out of a search, the classes below go with it, as before)
    assert await found({"who": {"exists": True}}, exclude_wrappers=["InRole"]) == [
        "direct"
    ]
