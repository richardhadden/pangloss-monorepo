"""`SameEntity[T]` of `pangloss-library`: a statement that two entities are one (implementation_docs/entity-identity.md,
part 2). It is written and read like any statement, is found from each entity it names, says what a semantic space
round it says, and still names both after the two are merged (its relation is an `IdentityClaim()`)."""

import importlib
from types import SimpleNamespace
from typing import Annotated, no_type_check

import pytest
from annotated_types import MaxLen, MinLen
from pangloss_models import (
    Document,
    Entity,
    SemanticSpace,
    export_models,
    initialise,
)
from pydantic import ValidationError

pytestmark = pytest.mark.asyncio(loop_scope="session")


def models():
    # (the registry was reset, and a module is only run once: the library's models are declared again)
    import pangloss_library.models
    from pangloss_library.identity import IdentityClaim

    importlib.reload(pangloss_library.models)
    SameEntity = pangloss_library.models.SameEntity

    class Person(Entity):
        pass

    class Place(Entity):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    # (a project's own statement of identity, with the marker and without the library's class)
    class Alias(Document):
        entities: Annotated[list[Person], MinLen(2), MaxLen(2), IdentityClaim()]

    class Factoid(Document):
        statements: list[
            SameEntity[Person] | Negative[SameEntity[Person]]  # ty: ignore[invalid-type-form]
        ]

    initialise()
    return SimpleNamespace(
        Person=Person, Place=Place, Factoid=Factoid, Alias=Alias, SameEntity=SameEntity
    )


def ref(id) -> dict:
    return {"type": "Person", "id": id}


def same(label: str, *ids, **more) -> dict:
    return {
        "type": "SameEntity",
        "label": label,
        "target": [ref(id) for id in ids],
        **more,
    }


async def people(m, *names: str) -> list:
    return [(await m.Person.Create(label=name).save()).id for name in names]


@no_type_check
async def test_a_claim_is_written_and_read_with_its_two_entities_and_its_argument(
    clear_database,
):
    m = models()
    a, b = await people(m, "A", "B")
    made = await m.Factoid.Create(
        label="Charter",
        statements=[same("A is B", a, b, argument="The same seal")],
    ).save(detail=True)
    [claim] = made.statements
    assert (claim.type, claim.label, claim.argument) == (
        "SameEntity",
        "A is B",
        "The same seal",
    )
    assert [entity.id for entity in claim.target] == [a, b]
    # (the argument may be left out)
    plain = await m.Factoid.Create(
        label="Roll", statements=[same("A is B", a, b)]
    ).save(detail=True)
    assert plain.statements[0].argument is None


@no_type_check
async def test_a_claim_names_exactly_two_entities_of_the_class_it_is_of(clear_database):
    m = models()
    a, b, c = await people(m, "A", "B", "C")
    for ids in ([a], [a, b, c]):
        with pytest.raises(ValidationError):
            m.Factoid.Create(label="F", statements=[same("Wrong", *ids)])
    rome = (await m.Place.Create(label="Rome").save()).id
    with pytest.raises(ValidationError):
        m.Factoid.Create(
            label="F",
            statements=[
                {
                    "type": "SameEntity",
                    "label": "A is Rome",
                    "target": [ref(a), {"type": "Place", "id": rome}],
                }
            ],
        )


@no_type_check
async def test_a_claim_is_found_from_each_entity_it_names_with_the_other_and_its_space(
    clear_database,
):
    m = models()
    a, b, c = await people(m, "A", "B", "C")
    await m.Factoid.Create(
        label="Charter",
        statements=[
            same("A is B", a, b),
            {"type": "Negative", "contents": [same("A is not C", a, c)]},
        ],
    ).save()
    for id, expected in (
        (a, {"A is B", "A is not C"}),
        (b, {"A is B"}),
        (c, {"A is not C"}),
    ):
        read = (await m.Person.get(id)).model_dump(by_alias=True, mode="json")
        # (each is the document at the top, with the chain down to the statement: what the interface reads)
        found = {}
        for holder in read["statementsReverse"]:
            assert (holder["type"], holder["label"]) == ("Factoid", "Charter")
            [inner] = holder["statements"]
            spaces = []
            while inner["type"] != "SameEntity":
                spaces.append(inner["type"])
                [inner] = inner["contents"]
            found[inner["label"]] = (
                spaces,
                [entity["id"] for entity in inner["target"]],
            )
        assert set(found) == expected
        if "A is not C" in found:
            assert found["A is not C"] == (["Negative"], [str(a), str(c)])
        if "A is B" in found:
            assert found["A is B"] == ([], [str(a), str(b)])


@no_type_check
async def test_a_merge_of_the_two_leaves_the_claim_naming_both_and_an_undo_changes_nothing_of_it(
    clear_database,
):
    m = models()
    a, b, c = await people(m, "A", "B", "C")
    factoid = await m.Factoid.Create(
        label="Charter",
        statements=[
            same("A is B", a, b),
            {"type": "Negative", "contents": [same("B is not C", b, c)]},
        ],
    ).save()
    alias = await m.Alias.Create(label="A alias B", entities=[ref(a), ref(b)]).save()

    preview = await m.Person.merge_preview(absorb=b, into=a)
    assert preview.possible
    # (nothing moves: every reference to B is a claim of identity, which stays; and nothing names "both" to collapse)
    assert preview.kept == 3 and preview.collapsed == []
    result = await m.Person.merge(absorb=b, into=a)
    assert result.merge.moved == 0 and result.kept == 3

    async def named():
        read = await m.Factoid.get(factoid.id)
        first, second = read.statements
        return (
            [(entity.id, entity.merged_into) for entity in first.target],
            [(entity.id, entity.merged_into) for entity in second.contents[0].target],
            [
                (entity.id, entity.merged_into)
                for entity in (await m.Alias.get(alias.id)).entities
            ],
        )

    assert await named() == (
        [(a, None), (b, a)],
        [(b, a), (c, None)],
        [(a, None), (b, a)],
    )
    # The claims are still found from the survivor and from the others they name
    survivor = (await m.Person.get(a)).model_dump(by_alias=True, mode="json")
    assert [
        holder["statements"][0]["label"] for holder in survivor["statementsReverse"]
    ] == ["A is B"]
    assert [each["label"] for each in survivor["entitiesReverse"]] == ["A alias B"]

    # A later save of the document does not make the claim say "A is A" (decision 16)
    edit = (await m.Factoid.get(factoid.id)).model_dump(mode="json")
    await m.Factoid.Update(
        **{
            "id": factoid.id,
            "label": "Charter, corrected",
            "statements": [
                {
                    "type": "SameEntity",
                    "id": edit["statements"][0]["id"],
                    "label": "A is B",
                    "target": [ref(a), ref(b)],
                },
                {
                    "type": "Negative",
                    "id": edit["statements"][1]["id"],
                    "contents": [
                        {
                            "type": "SameEntity",
                            "id": edit["statements"][1]["contents"][0]["id"],
                            "label": "B is not C",
                            "target": [ref(b), ref(c)],
                        }
                    ],
                },
            ],
        }
    ).save()
    assert (await named())[:2] == ([(a, None), (b, a)], [(b, a), (c, None)])

    await m.Person.unmerge(result.merge.id)
    assert await named() == (
        [(a, None), (b, None)],
        [(b, None), (c, None)],
        [(a, None), (b, None)],
    )


@no_type_check
async def test_the_export_says_which_relations_claim_identity(clear_database):
    m = models()
    exported = export_models()["models"]

    def markers(model: str, field: str):
        [found] = [each for each in exported[model]["fields"] if each["name"] == field]
        return found.get("markers")

    claim = [{"name": "IdentityClaim", "keepOnMerge": True, "identityClaim": True}]
    assert markers("SameEntity", "target") == claim
    assert markers("Alias", "entities") == claim
    # (a relation that is marked with nothing says nothing: its export is as it was)
    assert "markers" not in next(
        each for each in exported["Factoid"]["fields"] if each["name"] == "statements"
    )
    # (and where the interface looks for the claims about a person: its own reverse field, or what holds the statement)
    incoming = {
        each["name"]: each["sources"] for each in exported["Person"]["incoming"]
    }
    assert incoming["entities_reverse"] == [
        {"model": "Alias", "field": "entities", "viaReified": False}
    ]
    assert {"model": "Factoid", "field": "statements", "viaReified": True} in incoming[
        "statements_reverse"
    ]
    assert m.SameEntity.__name__ == "SameEntity"
