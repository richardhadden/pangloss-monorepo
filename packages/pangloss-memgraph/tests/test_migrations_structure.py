"""Changes that put a node on an edge or take one away, and move values into nodes: migrated,
they are what the new models write (the nodes, the edges, and what context each is in)"""

import json
import re
from types import SimpleNamespace as ns
from typing import no_type_check

import pytest
from pangloss_models.exceptions import PanglossMigrationAnswerNeeded
from pangloss_models.meta_kit.migrations import PossibleRename
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.embedded import Embedded
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.reified_relation import ReifiedRelation
from pangloss_models.model_bases.semantic_space import SemanticSpace

from .helpers import run
from .migration_support import declare, migrate, with_answers
from .test_migrations_relations import signature

pytestmark = pytest.mark.asyncio(loop_scope="session")


def contexts(db_driver, head_id) -> list[str]:
    """For each node of a document below its head: its type, the semantic spaces it is in and
    its context labels, without ids"""
    rows = run(
        db_driver,
        """
        MATCH (n) WHERE n.head_node_id = $id
        RETURN n.type AS type, n.label AS label,
               n.meta.semantic_spaces AS spaces, n.meta.context_labels AS labels
        """,
        id=str(head_id),
    )
    return sorted(
        re.sub(r'"id": "[^"]+"', '"id": "…"', json.dumps(row, sort_keys=True))
        for row in rows
    )


# ---------------------------------------------------------------------------
# Semantic spaces
# ---------------------------------------------------------------------------


def space_models(wrapped: bool):
    def declare_models():
        class Action(Document):
            pass

        class Statement(Document):
            action: Action

        class Negative[T](SemanticSpace[T]):
            pass

        class Factoid(Document):
            if wrapped:
                statements: list[Negative[Statement] | Statement]
            else:
                statements: list[Statement]

        return ns(Action=Action, Statement=Statement, Factoid=Factoid)

    return declare_models


def space_payload(wrapped: bool) -> list:
    def statement(label):
        return {
            "type": "Statement",
            "label": label,
            "action": {"type": "Action", "label": f"A of {label}"},
        }

    if wrapped:
        return [
            {"type": "Negative", "contents": [statement("One")]},
            {"type": "Negative", "contents": [statement("Two")]},
        ]
    return [statement("One"), statement("Two")]


@no_type_check
async def test_a_relation_is_wrapped_in_a_semantic_space(db_driver, clear_database):
    """`statements: list[Statement]` becomes `list[Negative[Statement]]`: a space on each edge,
    and everything below in it, with the context the models give"""
    old_models, old = declare(space_models(wrapped=False))
    factoid = await old_models.Factoid.Create(
        label="F", statements=space_payload(False)
    ).save()
    new_models, new = declare(space_models(wrapped=True))

    # (`Negative[Statement] | Statement` is wider, so the old edges are only a wrapped option:
    # the relation is wrapped to be only `Negative[Statement]`)
    def only_negative():
        class Action(Document):
            pass

        class Statement(Document):
            action: Action

        class Negative[T](SemanticSpace[T]):
            pass

        class Factoid(Document):
            statements: list[Negative[Statement]]

        return ns(Action=Action, Statement=Statement, Factoid=Factoid)

    new_models, new = declare(only_negative)
    await migrate(old, new)

    read = await new_models.Factoid.get(id=factoid.id)
    assert sorted(s.contents[0].label for s in read.statements) == ["One", "Two"]
    assert {s.type for s in read.statements} == {"Negative"}

    native = await new_models.Factoid.Create(
        label="F", statements=space_payload(True)
    ).save()
    assert signature(db_driver, factoid.id) == signature(db_driver, native.id)
    assert contexts(db_driver, factoid.id) == contexts(db_driver, native.id)
    assert any('"Negative"' in row for row in contexts(db_driver, factoid.id))


@no_type_check
async def test_a_relation_is_taken_out_of_a_semantic_space(db_driver, clear_database):
    def wrapped():
        class Action(Document):
            pass

        class Statement(Document):
            action: Action

        class Negative[T](SemanticSpace[T]):
            pass

        class Factoid(Document):
            statements: list[Negative[Statement]]

        return ns(Action=Action, Statement=Statement, Factoid=Factoid)

    old_models, old = declare(wrapped)
    factoid = await old_models.Factoid.Create(
        label="F", statements=space_payload(True)
    ).save()
    new_models, new = declare(space_models(wrapped=False))

    # (the new models allow only a statement)
    def plain():
        class Action(Document):
            pass

        class Statement(Document):
            action: Action

        class Factoid(Document):
            statements: list[Statement]

        return ns(Action=Action, Statement=Statement, Factoid=Factoid)

    new_models, new = declare(plain)
    await migrate(old, new, declined=[])

    assert run(db_driver, "MATCH (n:Negative) RETURN count(n) AS n") == [{"n": 0}]
    read = await new_models.Factoid.get(id=factoid.id)
    assert sorted(s.label for s in read.statements) == ["One", "Two"]
    native = await new_models.Factoid.Create(
        label="F", statements=space_payload(False)
    ).save()
    assert signature(db_driver, factoid.id) == signature(db_driver, native.id)
    assert contexts(db_driver, factoid.id) == contexts(db_driver, native.id)


@no_type_check
async def test_a_renamed_document_is_renamed_in_the_context_of_what_it_holds(
    db_driver, clear_database
):
    def v1():
        class Action(Document):
            pass

        class Statement(Document):
            action: Action

        class Factoid(Document):
            statements: list[Statement]

        return ns(Action=Action, Statement=Statement, Factoid=Factoid)

    def v2():
        class Action(Document):
            pass

        class Claim(Document):
            action: Action

        class Factoid(Document):
            statements: list[Claim]

        return ns(Action=Action, Claim=Claim, Factoid=Factoid)

    old_models, old = declare(v1)
    factoid = await old_models.Factoid.Create(
        label="F",
        statements=[
            {
                "type": "Statement",
                "label": "One",
                "action": {"type": "Action", "label": "A"},
            }
        ],
    ).save()
    new_models, new = declare(v2)
    await migrate(
        old, new, confirmed=[PossibleRename(what="model", old="Statement", new="Claim")]
    )

    native = await new_models.Factoid.Create(
        label="F",
        statements=[
            {
                "type": "Claim",
                "label": "One",
                "action": {"type": "Action", "label": "A"},
            }
        ],
    ).save()
    assert contexts(db_driver, factoid.id) == contexts(db_driver, native.id)
    assert "Claim" in " ".join(contexts(db_driver, factoid.id))
    assert "Statement" not in " ".join(contexts(db_driver, factoid.id))


# ---------------------------------------------------------------------------
# One wrapper for another
# ---------------------------------------------------------------------------


def wrapper_models(second: bool):
    def declare_models():
        class Person(Entity):
            pass

        if second:

            class ProxyFor[T](ReifiedRelation[T]):
                certainty: int
                note: str | None

            class Statement(Document):
                person: ProxyFor[Person]

        else:

            class IdentifiedAs[T](ReifiedRelation[T]):
                certainty: int
                old_note: str | None

            class Statement(Document):
                person: IdentifiedAs[Person]

        return ns(Person=Person, Statement=Statement)

    return declare_models


@no_type_check
async def test_one_wrapper_becomes_another(db_driver, clear_database):
    old_models, old = declare(wrapper_models(second=False))
    person = await old_models.Person.Create(label="Ann").save()
    statement = await old_models.Statement.Create(
        label="S",
        person={
            "type": "IdentifiedAs",
            "certainty": 4,
            "old_note": "x",
            "target": [{"type": "Person", "id": person.id}],
        },
    ).save()
    new_models, new = declare(wrapper_models(second=True))

    # (IdentifiedAs and ProxyFor are alike, but it is not a rename: the old stays until it is deleted)
    not_a_rename = PossibleRename(what="model", old="IdentifiedAs", new="ProxyFor")
    await migrate(old, new, declined=[not_a_rename])

    read = await new_models.Statement.get(id=statement.id)
    assert read.person.type == "ProxyFor"
    assert read.person.certainty == 4
    assert read.person.target[0].id == person.id
    assert run(db_driver, "MATCH (r:IdentifiedAs) RETURN count(r) AS n") == [{"n": 0}]
    props = run(db_driver, "MATCH (r:ProxyFor) RETURN keys(r) AS keys")[0]["keys"]
    assert "old_note" not in props

    native = await new_models.Statement.Create(
        label="S",
        person={
            "type": "ProxyFor",
            "certainty": 4,
            "target": [{"type": "Person", "id": person.id}],
        },
    ).save()
    assert signature(db_driver, statement.id) == signature(db_driver, native.id)
    assert contexts(db_driver, statement.id) == contexts(db_driver, native.id)


# ---------------------------------------------------------------------------
# Literals in a node of their own
# ---------------------------------------------------------------------------


def date_models(embedded: bool):
    def declare_models():
        if embedded:

            class Date(Embedded):
                when: str
                precision: int

            class Statement(Document):
                date: Date
                text: str

        else:

            class Statement(Document):
                when: str
                precision: int
                text: str

        return ns(Statement=Statement)

    return declare_models


@no_type_check
async def test_literals_become_an_embedded_object_and_back(db_driver, clear_database):
    old_models, old = declare(date_models(embedded=False))
    head = await old_models.Statement.Create(
        label="S", when="800", precision=2, text="T"
    ).save()
    new_models, new = declare(date_models(embedded=True))

    await migrate(old, new)
    read = await new_models.Statement.get(id=head.id)
    assert (read.date.when, read.date.precision, read.text) == ("800", 2, "T")
    props = run(db_driver, "MATCH (s:Statement) RETURN keys(s) AS keys")[0]["keys"]
    assert "when" not in props and "precision" not in props

    native = await new_models.Statement.Create(
        label="S", date={"when": "800", "precision": 2}, text="T"
    ).save()
    assert signature(db_driver, head.id) == signature(db_driver, native.id)
    assert contexts(db_driver, head.id) == contexts(db_driver, native.id)

    # ... and back
    await migrate(new, old)
    again = await old_models.Statement.get(id=head.id)
    assert (again.when, again.precision, again.text) == ("800", 2, "T")
    assert run(
        db_driver,
        "MATCH (d:Date) WHERE d.head_node_id = $id RETURN count(d) AS n",
        id=str(head.id),
    ) == [{"n": 0}]


# ---------------------------------------------------------------------------
# An embedded object that is new
# ---------------------------------------------------------------------------


def new_embedded_models(embedded: bool, two: bool = False):
    def declare_models():
        class Date(Embedded):
            when: str
            precision: int

        class Instant(Embedded):
            at: str

        if embedded and two:

            class Statement(Document):
                date: Date | Instant
                text: str

        elif embedded:

            class Statement(Document):
                date: Date
                text: str

        else:

            class Statement(Document):
                text: str

        return ns(Statement=Statement, Date=Date)

    return declare_models


@no_type_check
async def test_a_new_embedded_object_is_made_for_each_node_that_exists(
    db_driver, clear_database
):
    old_models, old = declare(new_embedded_models(embedded=False))
    head = await old_models.Statement.Create(label="S", text="T").save()
    new_models, new = declare(new_embedded_models(embedded=True))

    # (what the embedded object requires is asked)
    with pytest.raises(
        PanglossMigrationAnswerNeeded, match="when, precision|precision, when"
    ):
        await migrate(old, new)

    answers = {"when": "unknown", "precision": 0}
    await migrate(old, new, answer=with_answers(AddField={"default": answers}))

    read = await new_models.Statement.get(id=head.id)
    assert (read.date.when, read.date.precision, read.text) == ("unknown", 0, "T")

    native = await new_models.Statement.Create(label="S", date=answers, text="T").save()
    assert signature(db_driver, head.id) == signature(db_driver, native.id)
    assert contexts(db_driver, head.id) == contexts(db_driver, native.id)

    # (repeating it makes no more: each already has one)
    await migrate(old, new, answer=with_answers(AddField={"default": answers}))
    assert run(
        db_driver,
        "MATCH (d:Date) WHERE d.head_node_id = $id RETURN count(d) AS n",
        id=str(head.id),
    ) == [{"n": 1}]


@no_type_check
async def test_a_new_embedded_object_that_could_be_of_several_kinds_is_not_guessed(
    db_driver, clear_database
):
    from pangloss_models.exceptions import PanglossMigrationNotSupported

    old_models, old = declare(new_embedded_models(embedded=False))
    await old_models.Statement.Create(label="S", text="T").save()
    _, new = declare(new_embedded_models(embedded=True, two=True))
    with pytest.raises(PanglossMigrationNotSupported, match="which one"):
        await migrate(
            old,
            new,
            answer=with_answers(
                AddField={"default": {"when": "x", "precision": 0, "at": "y"}}
            ),
        )
