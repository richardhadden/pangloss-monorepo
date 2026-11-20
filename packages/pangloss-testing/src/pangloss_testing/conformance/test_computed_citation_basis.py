"""What the server computed for a node that cites a document (`Computed()`, `Cites[T]`): an update keeps it while the
node says the same, and what the write itself sets on a citation (`cited_version`, `cited_hash`, `cited_label`) is not
what the node says, nor what a read works out of what is cited (`target_label`, `target_state`, ...). So after the cited document changes, the citing document saved as it was read starts what was
computed again once (its citation is marked `changed_since_cited`), and not again on the next save as read
(implementation_docs/matches-criteria.md, "Shared descriptions")"""

from typing import Annotated, no_type_check

import pytest
from pangloss_core import storage_of
from pangloss_models import (
    Cites,
    Computed,
    ComputedWrite,
    Document,
    Entity,
    ReifiedRelation,
    initialise,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


def models():
    class Person(Entity):
        pass

    class Note(Document):
        text: str

    class Guess[T](ReifiedRelation[T]):
        after: Cites[Note] | None = None
        target: Annotated[list[T], Computed()] = []
        count: Annotated[int, Computed()] = 0

    class Act(Document):
        by: list[Guess[Person]]

    initialise()
    return Person, Note, Act


async def counted(Act, act_id) -> int:
    return (await Act.get(act_id)).by[0].count


async def saved_as_read(Act, act_id) -> None:
    read = await Act.get(act_id)
    await Act.Update(**read.model_dump()).save(expected_version=read.meta.version)


@no_type_check
async def test_what_was_computed_for_a_citing_node_is_kept_by_saves_as_read_once_the_mark_is_there(
    clear_database,
):
    Person, Note, Act = models()
    note = await Note.Create(label="A note", text="first").save()
    act = await Act.Create(
        label="An act",
        by=[{"type": "Guess", "after": {"type": "Note", "id": note.id}}],
    ).save(detail=True)
    guess_id = act.by[0].id

    async def compute():
        read = await Act.get(act.id)
        await storage_of().operations.set_computed_batch(
            [ComputedWrite(guess_id, {"count": 3}, read.meta.version)]
        )

    await compute()
    await saved_as_read(Act, act.id)
    assert await counted(Act, act.id) == 3

    # the cited note changes: the citation is marked, so the node says another thing
    await Note.Update(id=note.id, label="A note", text="second").save(
        acknowledge_citations=True
    )
    await saved_as_read(Act, act.id)
    assert await counted(Act, act.id) == 0
    await compute()
    # (the write set the citation's version and hash anew: still the same node, saying the same)
    await saved_as_read(Act, act.id)
    assert await counted(Act, act.id) == 3
    await saved_as_read(Act, act.id)
    assert await counted(Act, act.id) == 3
