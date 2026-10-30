"""Structured search through semantic spaces, conjunctions and reified relations, and over a whole document"""

from typing import no_type_check

import pytest
from pangloss_models import initialise
from pangloss_models.exceptions import PanglossSearchError
from pangloss_models.model_bases.conjunction import Conjunction
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.reified_relation import ReifiedRelation
from pangloss_models.model_bases.semantic_space import SemanticSpace
from pangloss_models.search import Match

pytestmark = pytest.mark.asyncio(loop_scope="session")


def models():
    class Negative[T](SemanticSpace[T]):
        pass

    class Hypothetical[T](SemanticSpace[T]):
        pass

    class Causes[A, B](Conjunction):
        cause: A
        result: B

    class Proxy[T](ReifiedRelation[T]):
        certainty: int

    class Person(Entity):
        pass

    class Statement(Document):
        about: list[Person | Negative[Person]]
        identified: list[Proxy[Person]]

    class Factoid(Document):
        statements: list[
            Statement
            | Negative[Statement | Hypothetical[Statement]]
            | Causes[Statement, Statement]
        ]

    initialise()
    return Person, Statement, Factoid


def where(**conditions):
    return Match(where=conditions)  # type: ignore[arg-type]


def labels(found):
    return sorted(item.label for item in found.results)


def statement(label, *about, negative=(), certainty=None, who=None):
    made = {
        "type": "Statement",
        "label": label,
        "about": [{"type": "Person", "id": p.id} for p in about]
        + (
            [
                {
                    "type": "Negative",
                    "contents": [{"type": "Person", "id": p.id} for p in negative],
                }
            ]
            if negative
            else []
        ),
    }
    made["identified"] = (
        []
        if who is None
        else [
            {
                "type": "Proxy",
                "certainty": certainty,
                "target": [{"type": "Person", "id": who.id}],
            }
        ]
    )
    return made


@no_type_check
async def make(clear_database):
    Person, Statement, Factoid = models()
    john = await Person.Create(label="John").save()
    jane = await Person.Create(label="Jane").save()
    kate = await Person.Create(label="Kate").save()

    async def factoid(label, *statements):
        return await Factoid.Create(label=label, statements=list(statements)).save()

    return Person, Statement, Factoid, john, jane, kate, factoid


@no_type_check
async def test_a_relation_sees_through_semantic_spaces_and_can_be_made_to_pass_through_them(
    clear_database,
):
    Person, Statement, Factoid, john, jane, kate, factoid = await make(clear_database)
    await factoid(
        "F",
        statement("direct", john),
        statement("negated", jane, negative=[john]),
        statement("only negated", negative=[kate]),
        statement("none"),
    )

    # (the statements are not head documents: so they are looked for from the factoid)
    async def factoids(**condition):
        return labels(
            await Factoid.search(
                where(
                    statements={
                        "type": "Statement",
                        "where": {"about": condition},
                    }
                )
            )
        )

    assert await factoids(**{"is": str(john.id)}) == ["F"]
    assert await factoids(**{"is": str(kate.id)}) == ["F"]
    # only what is inside a Negative
    assert await factoids(**{"is": str(john.id), "through": ["Negative"]}) == ["F"]
    assert await factoids(**{"is": str(jane.id), "through": ["Negative"]}) == []
    assert await factoids(**{"is": str(jane.id)}) == ["F"]


@no_type_check
async def test_the_statements_inside_spaces_and_conjunctions_are_found_at_any_depth(
    clear_database,
):
    Person, Statement, Factoid, john, jane, kate, factoid = await make(clear_database)
    await factoid("plain", statement("a", john))
    await factoid(
        "negated",
        {"type": "Negative", "contents": [statement("b", john)]},
    )
    await factoid(
        "deep",
        {
            "type": "Negative",
            "contents": [{"type": "Hypothetical", "contents": [statement("c", jane)]}],
        },
    )
    await factoid(
        "causal",
        {
            "type": "Causes",
            "cause": statement("d", kate),
            "result": statement("e", john),
        },
    )

    async def found(**condition):
        return labels(
            await Factoid.search(
                where(statements={"type": "Statement", "where": condition})
            )
        )

    assert await found(label={"eq": "c"}) == ["deep"]
    assert await found(label={"eq": "d"}) == ["causal"]
    assert await found(about={"is": str(john.id)}) == ["causal", "negated", "plain"]
    # a statement that is in a space, or in both of two
    assert await found(**{"$spaces": ["Negative"]}) == ["deep", "negated"]
    assert await found(**{"$spaces": ["Negative", "Hypothetical"]}) == ["deep"]
    assert await found(**{"$spaces": ["Hypothetical"], "label": {"eq": "b"}}) == []

    # a relation can be required to go through a space, or a conjunction
    async def through(*names):
        return labels(
            await Factoid.search(
                where(statements={"exists": True, "through": list(names)})
            )
        )

    assert await through("Negative") == ["deep", "negated"]
    assert await through("Negative", "Hypothetical") == ["deep"]
    assert await through("Causes") == ["causal"]


@no_type_check
async def test_a_reified_relation_is_seen_through_too(clear_database):
    Person, Statement, Factoid, john, jane, kate, factoid = await make(clear_database)
    await factoid("F", statement("a", john, certainty=2, who=jane))
    await factoid("G", statement("b", john, certainty=1, who=kate))

    async def found(**condition):
        return labels(
            await Factoid.search(
                where(
                    statements={"type": "Statement", "where": {"identified": condition}}
                )
            )
        )

    assert await found(**{"is": str(jane.id)}) == ["F"]
    assert await found(**{"is": str(kate.id), "through": ["Proxy"]}) == ["G"]
    assert await found(**{"is": str(kate.id), "through": ["Negative"]}) == []


@no_type_check
async def test_somewhere_finds_a_document_anywhere_inside_and_mentions_a_reference_anywhere(
    clear_database,
):
    Person, Statement, Factoid, john, jane, kate, factoid = await make(clear_database)
    await factoid("plain", statement("a", john))
    await factoid(
        "deep",
        {
            "type": "Negative",
            "contents": [
                {
                    "type": "Hypothetical",
                    "contents": [statement("c", jane, negative=[kate])],
                }
            ],
        },
    )
    await factoid("empty")

    async def somewhere(*patterns):
        return labels(await Factoid.search(where(**{"$somewhere": list(patterns)})))

    async def mentions(**condition):
        return labels(await Factoid.search(where(**{"$mentions": condition})))

    assert await somewhere({"type": "Statement"}) == ["deep", "plain"]
    assert await somewhere({"type": "Statement", "where": {"label": {"eq": "c"}}}) == [
        "deep"
    ]
    # (two patterns: a statement of each kind)
    assert (
        await somewhere(
            {"type": "Statement", "where": {"label": {"eq": "c"}}},
            {"type": "Statement", "where": {"label": {"eq": "a"}}},
        )
        == []
    )
    assert await somewhere(
        {"type": "Statement", "where": {"$spaces": ["Hypothetical"]}}
    ) == ["deep"]

    assert await mentions(**{"is": str(jane.id)}) == ["deep"]
    assert await mentions(**{"is": str(john.id)}) == ["plain"]
    assert await mentions(is_any=[str(john.id), str(jane.id)]) == [
        "deep",
        "plain",
    ]
    assert await mentions(**{"is": str(kate.id), "through": ["Negative"]}) == ["deep"]
    assert await mentions(**{"is": str(jane.id), "through": ["Negative"]}) == []
    assert await mentions(type="Person", where={"label": {"starts_with": "ka"}}) == [
        "deep"
    ]
    # (in a Negative inside a Negative that is not there: nothing)
    assert await mentions(**{"is": str(kate.id), "through": ["Causes"]}) == []
    # (two of them in one search, each looking in a list of its own: the documents that have either)
    either = Factoid.search(
        where(
            **{
                "$any_of": [
                    {"$mentions": {"is": str(john.id)}},
                    {"$mentions": {"is": str(kate.id), "through": ["Negative"]}},
                ]
            }
        )
    )
    assert labels(await either) == ["deep", "plain"]


@no_type_check
async def test_any_relation_of_a_node_and_its_label(clear_database):
    Person, Statement, Factoid, john, jane, kate, factoid = await make(clear_database)
    await factoid(
        "F",
        statement("about John", john),
        statement("about Jane, not Kate", jane, negative=[kate]),
    )

    async def found(**condition):
        return labels(
            await Factoid.search(
                where(statements={"type": "Statement", "where": {"$any": condition}})
            )
        )

    assert await found(**{"is": str(john.id)}) == ["F"]
    assert await found(**{"is": str(kate.id)}) == ["F"]
    assert await found(**{"is": str(kate.id), "through": ["Negative"]}) == ["F"]
    assert await found(**{"is": str(john.id), "through": ["Negative"]}) == []
    assert await found(type="Person", where={"label": {"eq": "Nobody"}}) == []
    # the label of the node itself
    assert await found(contains="not kate") == ["F"]
    assert await found(contains="zzz") == []


@no_type_check
async def test_what_is_not_possible_is_refused(clear_database):
    Person, Statement, Factoid, john, jane, kate, factoid = await make(clear_database)
    bad = (
        # (a head document is not inside a space; an entity is not part of a document)
        (Factoid, {"$spaces": ["Negative"]}),
        (
            Factoid,
            {"statements": {"type": "Statement", "where": {"$spaces": ["Nothing"]}}},
        ),
        (
            Factoid,
            {"statements": {"type": "Statement", "where": {"$spaces": ["Person"]}}},
        ),
        (Factoid, {"$somewhere": [{"type": "Person"}]}),
        (Factoid, {"$somewhere": [{"type": "Nothing"}]}),
        (Factoid, {"$somewhere": [{"label": {"eq": "x"}}]}),
        (Person, {"$somewhere": [{"type": "Statement"}]}),
        (Person, {"$mentions": {"is": str(john.id)}}),
        (Factoid, {"$mentions": {"exists": True}}),
        (Factoid, {"$mentions": {"contains": "x"}}),
        (Factoid, {"$any": {"exists": True}}),
        (Factoid, {"$any": {"type": "Nothing"}}),
        (Factoid, {"$any": {"where": {}}}),
        (Factoid, {"statements": {"through": ["Person"]}}),
        (Statement, {"label": {"through": ["Negative"]}}),
        (
            Factoid,
            {
                "statements": {
                    "type": "Statement",
                    "where": {"$somewhere": [{"type": "Statement"}]},
                }
            },
        ),
    )
    for model, condition in bad:
        with pytest.raises((PanglossSearchError, ValueError)):
            await model.search(where(**condition))


@no_type_check
async def test_documents_nested_as_deep_as_they_go_are_found_by_nesting_or_from_anywhere(
    clear_database,
):
    class Section(Document):
        heading: str
        sections: list[Section]

    class Book(Document):
        parts: list[Section]

    initialise()

    def section(depth, heading):
        if depth == 0:
            return {
                "type": "Section",
                "label": heading,
                "heading": heading,
                "sections": [],
            }
        return {
            "type": "Section",
            "label": f"level {depth}",
            "heading": f"level {depth}",
            "sections": [section(depth - 1, heading)],
        }

    await Book.Create(label="deep", parts=[section(8, "the bottom")]).save()
    await Book.Create(label="shallow", parts=[section(1, "the bottom")]).save()
    await Book.Create(label="other", parts=[section(8, "somewhere else")]).save()

    # from anywhere, whatever the depth
    found = await Book.search(
        where(
            **{
                "$somewhere": [
                    {"type": "Section", "where": {"heading": {"eq": "the bottom"}}}
                ]
            }
        )
    )
    assert labels(found) == ["deep", "shallow"]

    # and by naming every step: nine sections down
    pattern = {"heading": {"eq": "the bottom"}}
    for _ in range(8):
        pattern = {"sections": {"type": "Section", "where": pattern}}
    found = await Book.search(where(parts={"type": "Section", "where": pattern}))
    assert labels(found) == ["deep"]
