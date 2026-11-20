"""A field that names a wrapper takes the classes below it (implementation_docs/reified-relation-inheritance-plan.md),
as a field that names `Person` takes a `Saint`: a reified relation, a semantic space, a conjunction. Each is written,
read, read from the entity it reaches, updated and searched."""

from typing import no_type_check

import pytest
from pangloss_models import (
    Conjunction,
    Document,
    Entity,
    Match,
    ReifiedRelation,
    SemanticSpace,
    initialise,
)
from pydantic import ValidationError

pytestmark = pytest.mark.asyncio(loop_scope="session")


def ref(item):
    return {"type": item.type, "id": item.id}


def labels(found):
    return sorted(item.label for item in found.results)


def models():
    class Person(Entity):
        pass

    class Saint(Person):
        pass

    class Group(Entity):
        pass

    class InRole[T](ReifiedRelation[T]):
        role: str | None = None

    class Finer[T](InRole[T]):
        fine: int = 0

    class Finest[T](Finer[T]):
        finest: int = 0

    # (below the very use the field names)
    class JohnRole(InRole[Person]):
        john: int = 0

    # (not below it: of another use, and with a parameter the use does not settle)
    class GroupRole(InRole[Group]):
        pass

    class Both[A, B](InRole[A]):
        other: list[B] = []

    class Negative[T](SemanticSpace[T]):
        pass

    class Strongly[T](Negative[T]):
        pass

    class Pair[T](Conjunction):
        items: list[T]

    class Ordered[T](Pair[T]):
        order: int = 0

    class Doc(Document):
        who: list[InRole[Person]]
        # (written out as before: the same types, each once)
        written: list[InRole[Person] | Finer[Person]]
        not_who: list[Negative[Person]]
        pairs: list[Pair[Person]]

    initialise()
    return Person, Saint, Doc


def empty(**fields):
    return {"who": [], "written": [], "not_who": [], "pairs": [], **fields}


@no_type_check
async def test_a_field_takes_the_classes_below_the_reified_relation_it_names(
    clear_database,
):
    Person, Saint, Doc = models()
    john = await Person.Create(label="John").save()
    paul = await Saint.Create(label="Paul").save()

    def role(type_, person=john, **values):
        return {"type": type_, "target": [ref(person)], **values}

    assert {
        option.base_type.__name__ for option in Doc._meta.fields["who"].type_options
    } == {"InRole", "Finer", "Finest", "JohnRole"}
    assert {
        option.base_type.__name__ for option in Doc._meta.fields["written"].type_options
    } == {"InRole", "Finer", "Finest", "JohnRole"}

    doc = await Doc.Create(
        label="all four",
        **empty(
            who=[
                role("InRole", role="a"),
                role("Finer", role="b", fine=2),
                role("Finest", paul, role="c", fine=3, finest=4),
                role("JohnRole", role="d", john=5),
            ]
        ),
    ).save()
    await Doc.Create(label="plain", **empty(who=[role("InRole", role="a")])).save()
    await Doc.Create(
        label="written", **empty(written=[role("Finest", fine=1, finest=9)])
    ).save()

    read = await Doc.get(doc.id)
    assert [item.type for item in read.who] == ["InRole", "Finer", "Finest", "JohnRole"]
    assert (read.who[1].role, read.who[1].fine) == ("b", 2)
    assert (read.who[2].fine, read.who[2].finest) == (3, 4)
    assert read.who[2].target[0].type == "Saint"
    assert read.who[3].john == 5

    for other in ("GroupRole", "Both"):
        with pytest.raises(ValidationError):
            Doc.Create(label="no", **empty(who=[role(other)]))
    # (a value of the class above is not taken for one below: `fine` is not a field of an `InRole`)
    with pytest.raises(ValidationError):
        Doc.Create(label="no", **empty(who=[role("InRole", fine=2)]))

    # (the document is there once for each way it reaches John)
    back = await Person.get(john.id)
    assert sorted(d.label for d in back.who_reverse) == ["all four"] * 3 + ["plain"]
    assert [d.label for d in back.written_reverse] == ["written"]
    back = await Saint.get(paul.id)
    assert [d.label for d in back.who_reverse] == ["all four"]

    await Doc.Update(
        id=doc.id,
        label="two now",
        **empty(who=[role("Finer", fine=7), role("Finest", fine=8, finest=9)]),
    ).save()
    read = await Doc.get(doc.id)
    assert [(item.type, item.fine) for item in read.who] == [
        ("Finer", 7),
        ("Finest", 8),
    ]

    async def found(where, **match):
        return labels(await Doc.search(Match(where=where, **match)))

    assert await found({"who": {"is": str(john.id)}}) == ["plain", "two now"]
    assert await found({"who": {"through": ["InRole"]}}) == ["plain", "two now"]
    assert await found({"who": {"through": ["Finer"]}}) == ["two now"]
    assert await found({"who": {"via": [{"type": "Finest"}]}}) == ["two now"]
    step = {"type": "Finer", "where": {"fine": {"gte": 8}}}
    assert await found({"who": {"via": [step]}}) == ["two now"]
    assert await found({"who": {"through": [step]}}) == ["two now"]
    step = {"type": "Finer", "where": {"fine": {"gte": 9}}}
    assert await found({"who": {"via": [step]}}) == []
    assert await found({"$mentions": {"is": str(john.id)}}) == [
        "plain",
        "two now",
        "written",
    ]
    assert await found({"who": {"exists": True}}, exclude_wrappers=["Finer"]) == [
        "plain"
    ]
    people = await Person.search(
        Match(where={"$incoming": [{"type": "Doc", "field": "who", "via": [step]}]})
    )
    assert labels(people) == []
    step = {"type": "Finer", "where": {"fine": {"eq": 7}}}
    people = await Person.search(
        Match(where={"$incoming": [{"type": "Doc", "field": "who", "via": [step]}]})
    )
    assert labels(people) == ["John"]


@no_type_check
async def test_a_field_takes_the_classes_below_the_space_and_the_conjunction_it_names(
    clear_database,
):
    Person, _, Doc = models()
    john = await Person.Create(label="John").save()
    jane = await Person.Create(label="Jane").save()

    def space(type_):
        return {"type": type_, "contents": [ref(john)]}

    def pair(type_, **values):
        return {"type": type_, "items": [ref(john), ref(jane)], **values}

    doc = await Doc.Create(
        label="both",
        **empty(
            not_who=[space("Negative"), space("Strongly")],
            pairs=[pair("Pair"), pair("Ordered", order=2)],
        ),
    ).save()
    await Doc.Create(label="above", **empty(not_who=[space("Negative")])).save()

    read = await Doc.get(doc.id)
    assert [item.type for item in read.not_who] == ["Negative", "Strongly"]
    assert [item.type for item in read.pairs] == ["Pair", "Ordered"]
    assert read.pairs[1].order == 2
    assert [item.label for item in read.pairs[1].items] == ["John", "Jane"]

    back = await Person.get(jane.id)
    assert [d.label for d in back.pairs_reverse] == ["both", "both"]
    back = await Person.get(john.id)
    assert sorted(d.label for d in back.not_who_reverse) == ["above", "both", "both"]

    await Doc.Update(
        id=doc.id,
        label="below",
        **empty(not_who=[space("Strongly")], pairs=[pair("Ordered", order=5)]),
    ).save()
    read = await Doc.get(doc.id)
    assert [item.type for item in read.not_who] == ["Strongly"]
    assert [(item.type, item.order) for item in read.pairs] == [("Ordered", 5)]

    async def found(where):
        return labels(await Doc.search(Match(where=where)))

    assert await found({"not_who": {"through": ["Negative"]}}) == ["above", "below"]
    assert await found({"not_who": {"via": [{"type": "Strongly"}]}}) == ["below"]
    assert await found({"pairs": {"is": str(jane.id)}}) == ["below"]
    step = {"type": "Ordered", "where": {"order": {"eq": 5}}}
    assert await found({"pairs": {"via": [step]}}) == ["below"]
    assert await found({"pairs": {"through": ["Pair"]}}) == ["below"]
