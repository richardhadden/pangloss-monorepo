"""A migration works out the semantic spaces and context labels of stored nodes with the same algorithm
the models use for an instance they write (`pangloss_models.context.propagate_context`), each looking
at its nodes in its own way. So for a document the models wrote, working them out again from the stored
nodes must change nothing: this checks the two views (what a relation holds, what an entity is, what
counts as context) agree."""

from types import SimpleNamespace as ns
from typing import no_type_check

import pytest
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.semantic_space import SemanticSpace
from pangloss_neo4j.databases.neo4j.database import Database
from pangloss_neo4j.databases.neo4j.migrations.operations import (
    recompute_contexts,
)

from .helpers import run
from .migration_support import declare

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
        RETURN n.id AS id, n.type AS type, n.meta.semantic_spaces AS spaces,
               n.meta.context_labels AS labels
        """,
        id=str(head_id),
    )
    return sorted(
        (r["id"], r["type"], tuple(r["spaces"] or ()), repr(r["labels"])) for r in rows
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
    # (the cases are there: something in a space, in two, in a root context, and in none)
    assert any(len(row[2]) == 2 for row in before)
    assert any("#rootcontext" in row[3] for row in before)
    assert any(row[2] == () for row in before)

    database = Database.default
    async with database.driver.session(
        database=database.settings.DATABASE.DATABASE_NAME
    ) as session:

        async def work(tx):
            await recompute_contexts(tx, [str(factoid.id)], state)

        await session.execute_write(work)

    assert meta_of_all(db_driver, factoid.id) == before
