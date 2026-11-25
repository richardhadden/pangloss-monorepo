"""A migration works out the path of stored nodes, and the semantic spaces made from it, with the same algorithm
the models use for an instance they write (`pangloss_models.context.propagate_context`), each looking
at its nodes in its own way. So for a document the models wrote, working them out again from the stored
nodes must change nothing: this checks the two views (what a relation holds, what an entity is, what
counts as context) agree."""

from types import SimpleNamespace as ns
from typing import no_type_check

import pytest
from pangloss_models import Document, Entity, SemanticSpace
from pangloss_cypher.migrations.operations import (
    recompute_contexts,
)

from .helpers import run
from .migration_support import declare
from pangloss_testing.under_test.database import current

pytestmark = pytest.mark.asyncio(loop_scope="session")


@no_type_check
def models():
    class Person(Entity):
        pass

    class Note(Document):
        text: str

    class Statement(Document):
        person: Person
        note: Note
        also: list[Note]

    class Negative[T](SemanticSpace[T]):
        pass

    class Doubt[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Statement | Negative[Statement] | Doubt[Negative[Statement]]]
        summary: Note

    return ns(Person=Person, Note=Note, Statement=Statement, Factoid=Factoid)


def meta_of_all(db_driver, head_id) -> list[tuple]:
    rows = run(
        db_driver,
        """
        MATCH (n) WHERE n.head_node_id = $id
        RETURN n.id AS id, n.type AS type, n.meta.semantic_spaces AS spaces, n.meta.path AS path
        """,
        id=str(head_id),
    )
    return sorted(
        (r["id"], r["type"], tuple(r["spaces"] or ()), r["path"]) for r in rows
    )


@no_type_check
async def test_working_contexts_out_again_changes_nothing_for_what_the_models_wrote(
    db_driver, clear_database
):
    made, state = declare(models)
    person = await made.Person.Create(label="Ann").save()
    reference = {"type": "Person", "id": person.id}

    note = {"type": "Note", "label": "n", "text": "t"}

    def statement(label, **extra):
        return {
            "type": "Statement",
            "label": label,
            "person": reference,
            "note": note,
            "also": [],
            **extra,
        }

    factoid = await made.Factoid.Create(
        label="F",
        summary=note,
        statements=[
            statement("Outside", also=[note, note]),
            {"type": "Negative", "contents": [statement("Inside", also=[note])]},
            {
                "type": "Doubt",
                "contents": [
                    {
                        "type": "Negative",
                        "contents": [statement("Deep", also=[note, note])],
                    }
                ],
            },
        ],
    ).save()

    before = meta_of_all(db_driver, factoid.id)
    assert len(before) > 8
    # (the cases are there: something in a space, in two, in a document below the head, and in none)
    assert any(len(row[2]) == 2 for row in before)
    assert any(
        [entry["kind"] for entry in row[3]] == ["document", "document"]
        for row in before
    )
    assert any(row[2] == () for row in before)
    # (and every node below the head has its path, from the head down)
    assert all(row[3] and row[3][0]["id"] == str(factoid.id) for row in before)

    database = current()
    async with database.driver.session(
        database=database.settings.DATABASE.DATABASE_NAME
    ) as session:

        async def work(tx):
            await recompute_contexts(tx, [str(factoid.id)], state)

        await session.execute_write(work)

    assert meta_of_all(db_driver, factoid.id) == before


@pytest.mark.stored_by_hand
@no_type_check
async def test_working_contexts_out_again_takes_the_older_context_labels_away(
    db_driver, clear_database
):
    """A node stored before the path holds `meta.context_labels` (on Neo4j `meta.context_labels#json`, with
    `meta.context_label_types` beside it). Given here by hand to a node the models wrote: working the contexts out
    again takes it away, and leaves the path and the spaces as they were"""
    from .helpers import assert_paths_true, memgraph_meta

    made, state = declare(models)
    person = await made.Person.Create(label="Ann").save()
    factoid = await made.Factoid.Create(
        label="F",
        summary={"type": "Note", "label": "n", "text": "t"},
        statements=[
            {
                "type": "Negative",
                "contents": [
                    {
                        "type": "Statement",
                        "label": "Inside",
                        "person": {"type": "Person", "id": person.id},
                        "note": {"type": "Note", "label": "n", "text": "t"},
                        "also": [],
                    }
                ],
            }
        ],
    ).save()
    before = meta_of_all(db_driver, factoid.id)
    [inside] = run(db_driver, "MATCH (s:Statement) RETURN s.id AS id")
    old = [
        {"type": "Negative", "contents": [{"type": "Statement", "id": inside["id"]}]}
    ]

    if "meta.path#json" in memgraph_meta("n.meta.path AS path"):
        import json

        db_driver.execute_query(
            "MATCH (n {id: $id}) SET n.`meta.context_labels#json` = $labels, "
            "n.`meta.context_label_types` = ['Negative']",
            id=inside["id"],
            labels=json.dumps(old),
        )
    else:
        # (the meta as it was stored before the path: who made it, the spaces, the labels; the path given too, so
        # that what is compared below is the same)
        [row] = run(
            db_driver,
            "MATCH (n {id: $id}) RETURN n.meta.semantic_spaces AS spaces, n.meta.path AS path",
            id=inside["id"],
        )
        db_driver.execute_query(
            "MATCH (n {id: $id}) SET n.meta = $meta",
            id=inside["id"],
            meta={
                "created_by": "x",
                "semantic_spaces": row["spaces"],
                "path": row["path"],
                "context_labels": old,
            },
        )

    def held(node_id) -> set[str]:
        [row] = run(
            db_driver,
            "MATCH (n {id: $id}) RETURN keys(n) AS keys, n.meta AS meta, "
            "n.meta.context_labels AS labels",
            id=node_id,
        )
        return {
            key
            for key in set(row["keys"]) | set(row["meta"] or {})
            if "context_label" in key
        } | ({"labels"} if row["labels"] is not None else set())

    assert held(inside["id"])

    database = current()
    async with database.driver.session(
        database=database.settings.DATABASE.DATABASE_NAME
    ) as session:

        async def work(tx):
            await recompute_contexts(tx, [str(factoid.id)], state)

        await session.execute_write(work)

    assert held(inside["id"]) == set()
    assert meta_of_all(db_driver, factoid.id) == before
    assert_paths_true(db_driver)
