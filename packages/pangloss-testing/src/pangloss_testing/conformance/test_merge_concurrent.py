"""Merges of entities and other writes at the same moment (implementation_docs/entity-identity.md, decision 24 and "Measured before
building", 1 and 3).

What must hold however the writes fall: no reference is left on an absorbed entity (but those a merge keeps there);
no write is lost; an entity is merged into one other at most, and never round in a circle. On Memgraph a write that
races a merge is refused and run again, and then finds the entity merged. On Neo4j it is not stopped, and may leave
its reference on the absorbed entity after the merge has committed: the merge's second pass moves it."""

import asyncio
from typing import no_type_check

import neo4j
import pytest
from pangloss_core import storage_of
from pangloss_models import (
    PanglossMergeBusyError,
    PanglossMergeError,
    PanglossReadOnlyError,
    PanglossVersionConflictError,
    PanglossWriteError,
)

from .helpers import count_nodes, run
from .merge_support import (
    declare,
    edges_to,
    make,
    merged_into,
    moves_of,
    person,
    ref,
    version_of,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")

WRITERS = 12


async def outcome(awaitable):
    """What it gave, or what it raised"""
    try:
        return await awaitable
    except Exception as error:
        return error


@no_type_check
async def test_writes_that_name_an_entity_while_it_is_merged_end_on_its_survivor(
    db_driver, clear_database
):
    m = declare()
    a, b = await person(m, "A"), await person(m, "B")
    for i in range(5):
        await make(m.Mention, f"Before {i}", of=ref(b))

    results = await asyncio.gather(
        *[
            outcome(make(m.Mention, f"During {i}", of=ref(b), others=[ref(b)]))
            for i in range(WRITERS // 2)
        ],
        outcome(m.Person.merge(absorb=b.id, into=a.id)),
        *[
            outcome(make(m.Group, f"Group {i}", members=[ref(a), ref(b)]))
            for i in range(WRITERS // 2)
        ],
    )

    failed = [r for r in results if isinstance(r, Exception)]
    assert failed == []
    merge = (await m.Person.merges(a.id))[0]
    # (on a database that does not stop a write that was open when the merge committed: the pass that is made again
    # after a while, here at once)
    await storage_of().operations.merge_second_pass(merge.id)

    assert edges_to(db_driver, b.id) == []
    # every write is there, and each names the survivor
    assert (await m.Mention.list(page_size=100)).count == 5 + WRITERS // 2
    assert (await m.Group.list(page_size=100)).count == WRITERS // 2
    survivor = await m.Person.get(a.id)
    assert len(survivor.of_reverse) == 5 + WRITERS // 2
    assert len(survivor.members_reverse) == WRITERS // 2
    # a group that named both names the survivor once, whichever of the write and the merge came first
    for group in survivor.members_reverse:
        assert [p.id for p in (await m.Group.get(group.id)).members] == [a.id]
    # and an undo knows of every reference that the merge, or its later pass, moved
    undone = await m.Person.unmerge(merge.id)
    assert undone.unmatched == []
    assert merged_into(db_driver, b.id) is None


@no_type_check
async def test_updates_of_the_documents_a_merge_moves_are_not_lost_nor_left_behind(
    db_driver, clear_database
):
    m = declare()
    a, b, c = await person(m, "A"), await person(m, "B"), await person(m, "C")
    mentions = [
        await make(m.Mention, f"Mention {i}", of=ref(b)) for i in range(WRITERS)
    ]

    async def edit(mention, i):
        # (a form that was opened before the merge: it names the absorbed entity, and the version it read)
        return await m.Mention.Update(
            id=mention.id, label=f"Edited {i}", of=ref(b), others=[ref(c)]
        ).save(expected_version=1)

    results = await asyncio.gather(
        *[
            outcome(edit(mention, i))
            for i, mention in enumerate(mentions[: WRITERS // 2])
        ],
        outcome(m.Person.merge(absorb=b.id, into=a.id)),
        *[
            outcome(edit(mention, i))
            for i, mention in enumerate(mentions[WRITERS // 2 :], WRITERS // 2)
        ],
    )

    merged = results[WRITERS // 2]
    assert not isinstance(merged, Exception), merged
    await storage_of().operations.merge_second_pass(merged.merge.id)
    edits = results[: WRITERS // 2] + results[WRITERS // 2 + 1 :]
    # an edit either went in, or was refused because the merge had written the document first: never anything else
    assert all(
        not isinstance(r, Exception) or isinstance(r, PanglossVersionConflictError)
        for r in edits
    ), edits
    assert edges_to(db_driver, b.id) == []
    for i, (mention, result) in enumerate(zip(mentions, edits, strict=True)):
        read = await m.Mention.get(mention.id)
        assert read.of.id == a.id
        if isinstance(result, Exception):
            # refused: it is as the merge left it, at the version the merge made
            assert (read.label, read.others, read.meta.version) == (
                f"Mention {i}",
                [],
                2,
            )
        else:
            assert (read.label, [p.id for p in read.others]) == (f"Edited {i}", [c.id])
            assert read.meta.version in (2, 3)


@no_type_check
async def test_two_merges_of_the_same_pair_at_once_make_one_merge(
    db_driver, clear_database
):
    m = declare()
    a, b = await person(m, "A"), await person(m, "B")
    for i in range(4):
        await make(m.Mention, f"Mention {i}", of=ref(b))

    results = await asyncio.gather(
        *[outcome(m.Person.merge(absorb=b.id, into=a.id)) for _ in range(4)]
    )

    done = [r for r in results if not isinstance(r, Exception)]
    refused = [r for r in results if isinstance(r, Exception)]
    assert len(done) == 1, results
    assert all(isinstance(r, PanglossMergeError) for r in refused), refused
    assert count_nodes(db_driver, "PGMerge") == 1
    assert len(moves_of(db_driver, done[0].merge.id)) == 4
    # the survivor was written once, and the absorbed entity's label is among its names once
    survivor = await m.Person.get(a.id)
    assert (survivor.meta.version, survivor.aliases) == (2, ["B"])
    assert all(
        row["version"] == 2
        for row in run(
            db_driver,
            "MATCH (n:Mention) RETURN size([(n)<-[:is_update_of]-(u:PGUpdate) | u]) + 1 AS version",
        )
    )


@no_type_check
async def test_two_entities_merged_into_each_other_at_once_do_not_make_a_circle(
    db_driver, clear_database
):
    m = declare()
    a, b = await person(m, "A"), await person(m, "B")
    await make(m.Mention, "Of A", of=ref(a))
    await make(m.Mention, "Of B", of=ref(b))

    results = await asyncio.gather(
        outcome(m.Person.merge(absorb=b.id, into=a.id)),
        outcome(m.Person.merge(absorb=a.id, into=b.id)),
    )

    done = [r for r in results if not isinstance(r, Exception)]
    assert len(done) == 1, results
    marks = [merged_into(db_driver, a.id), merged_into(db_driver, b.id)]
    assert marks.count(None) == 1
    survivor = done[0].merge.survivor
    # both ids lead to the one that survived, and everything refers to it
    assert (await m.Person.get(a.id)).id == (await m.Person.get(b.id)).id == survivor
    assert len((await m.Person.get(survivor)).of_reverse) == 2
    assert count_nodes(db_driver, "PGMerge") == 1


@no_type_check
async def test_several_entities_merged_into_one_at_once_are_all_merged(
    db_driver, clear_database
):
    m = declare()
    a = await person(m, "A")
    others = [await person(m, f"Other {i}", died=1800 + i) for i in range(5)]
    for other in others:
        await make(m.Mention, f"Of {other.label}", of=ref(other))

    results = await asyncio.gather(
        *[outcome(m.Person.merge(absorb=other.id, into=a.id)) for other in others]
    )

    # (each is decided on no version: one that finds the survivor changed under it is worked out again)
    assert [r for r in results if isinstance(r, Exception)] == []
    survivor = await m.Person.get(a.id)
    assert sorted(survivor.aliases) == [f"Other {i}" for i in range(5)]
    assert survivor.meta.version == 6
    assert len(survivor.of_reverse) == 5
    assert all(merged_into(db_driver, other.id) == str(a.id) for other in others)
    # the survivor's fields were worked out from it as it was each time: no name was lost to another merge
    assert survivor.died in {1800 + i for i in range(5)}


@no_type_check
async def test_a_merge_and_an_edit_of_the_survivor_at_once_lose_neither(
    db_driver, clear_database
):
    m = declare()
    a, b = await person(m, "A"), await person(m, "B")

    async def edit():
        return await m.Person.Update(id=a.id, label="A", born=1750, knows=[]).save()

    merged, edited = await asyncio.gather(
        outcome(m.Person.merge(absorb=b.id, into=a.id)), outcome(edit())
    )

    assert not isinstance(merged, Exception), merged
    survivor = await m.Person.get(a.id)
    if isinstance(edited, Exception):
        assert isinstance(edited, PanglossWriteError)
    else:
        # the edit was made before the merge or after it: if before, the merge was worked out again from what it
        # left; if after, the edit (which gave no aliases) is the later word
        assert survivor.born == 1750
    assert survivor.meta.version == (2 if isinstance(edited, Exception) else 3)
    assert merged_into(db_driver, b.id) == str(a.id)


@no_type_check
async def test_two_undos_at_once_undo_once(db_driver, clear_database):
    m = declare()
    a, b = await person(m, "A"), await person(m, "B")
    mention = await make(m.Mention, "Of B", of=ref(b))
    result = await m.Person.merge(absorb=b.id, into=a.id)

    results = await asyncio.gather(
        *[outcome(m.Person.unmerge(result.merge.id)) for _ in range(3)]
    )

    done = [r for r in results if not isinstance(r, Exception)]
    assert len(done) == 1, results
    assert all(
        isinstance(r, PanglossMergeError) for r in results if isinstance(r, Exception)
    )
    assert (await m.Mention.get(mention.id)).of.id == b.id
    # (the merge wrote it once and the one undo once)
    assert version_of(db_driver, mention.id) == 3
    assert (await m.Person.get(a.id)).meta.version == 3


@no_type_check
async def test_a_reference_left_on_the_absorbed_entity_is_moved_by_the_second_pass_and_undone_with_the_merge(
    db_driver, clear_database
):
    m = declare()
    a, b = await person(m, "A"), await person(m, "B")
    before = await make(m.Mention, "Before", of=ref(b))
    late = await make(m.Mention, "Late", of=ref(a))
    result = await m.Person.merge(absorb=b.id, into=a.id)
    assert result.late == 0
    # (what a write that was open when the merge committed leaves, on a database that does not stop it; or a write
    # made around the models, which does not resolve merged ids)
    run(
        db_driver,
        """
        MATCH (d:Mention {id: $d})-[old:of]->(a:Person {id: $a}), (a)-[old_reverse:of_reverse]->(d), (b:Person {id: $b})
        DELETE old, old_reverse
        CREATE (d)-[:of {pg_position: 0}]->(b)
        CREATE (b)-[:of_reverse {reverse: true}]->(d)
        """,
        d=str(late.id),
        a=str(a.id),
        b=str(b.id),
    )
    assert edges_to(db_driver, b.id) == [("Mention", "of", 0)]

    written = await storage_of().operations.merge_second_pass(result.merge.id)

    assert written == 1
    assert edges_to(db_driver, b.id) == []
    assert (await m.Mention.get(late.id)).of.id == a.id
    assert version_of(db_driver, late.id) == 2
    assert sorted(move["late"] for move in moves_of(db_driver, result.merge.id)) == [
        False,
        True,
    ]
    assert (await m.Person.merges(a.id))[0].moved == 2
    # a second pass with nothing to do does nothing
    assert await storage_of().operations.merge_second_pass(result.merge.id) == 0
    assert version_of(db_driver, late.id) == 2

    undone = await m.Person.unmerge(result.merge.id)
    assert undone.restored == 2
    assert (await m.Mention.get(late.id)).of.id == b.id
    assert (await m.Mention.get(before.id)).of.id == b.id
    # and once the merge is undone, the pass leaves what is on the entity alone
    assert await storage_of().operations.merge_second_pass(result.merge.id) == 0
    assert (await m.Mention.get(late.id)).of.id == b.id


@no_type_check
async def test_the_second_pass_is_made_again_after_a_while_where_the_database_needs_it(
    db_driver, clear_database, monkeypatch
):
    from pangloss_cypher import merge

    m = declare()
    a, b = await person(m, "A"), await person(m, "B")
    late = await make(m.Mention, "Late", of=ref(a))
    monkeypatch.setattr(merge, "SECOND_PASS_DELAY", 0.4)

    await m.Person.merge(absorb=b.id, into=a.id)
    run(
        db_driver,
        """
        MATCH (d:Mention {id: $d})-[old:of]->(a:Person {id: $a}), (a)-[old_reverse:of_reverse]->(d), (b:Person {id: $b})
        DELETE old, old_reverse
        CREATE (d)-[:of {pg_position: 0}]->(b)
        CREATE (b)-[:of_reverse {reverse: true}]->(d)
        """,
        d=str(late.id),
        a=str(a.id),
        b=str(b.id),
    )
    assert len(merge._second_passes) == 1

    await merge.settle_second_passes()

    assert edges_to(db_driver, b.id) == []
    assert (await m.Mention.get(late.id)).of.id == a.id
    assert merge._second_passes == set()


@no_type_check
async def test_the_delay_of_the_second_pass_is_the_databases_unless_the_settings_say(
    monkeypatch,
):
    from pangloss_cypher import merge
    from pangloss_cypher.transactions import current, dialect

    monkeypatch.setattr(merge, "SECOND_PASS_DELAY", None)
    # (Memgraph refuses the write that races a merge; Neo4j does not, and so looks again)
    assert merge.second_pass_delay() == dialect().merge_second_pass_delay
    assert dialect().merge_second_pass_delay == (
        5.0 if dialect().name == "neo4j" else 0.0
    )
    monkeypatch.setattr(
        current().settings, "MERGE_SECOND_PASS_SECONDS", 2, raising=False
    )
    assert merge.second_pass_delay() == 2.0


@no_type_check
async def test_a_merge_that_keeps_giving_way_stops_and_says_so(
    db_driver, clear_database, monkeypatch
):
    from pangloss_cypher import merge

    m = declare()
    a, b = await person(m, "A"), await person(m, "B")
    await make(m.Mention, "Of B", of=ref(b))

    async def conflicting(*args, **kwargs):
        # (what the driver raises when it has tried a transaction again for as long as it is allowed to)
        raise neo4j.exceptions.TransientError("Cannot resolve conflicting transactions")

    monkeypatch.setattr(merge, "_merge_transaction", conflicting)
    monkeypatch.setattr(
        neo4j.exceptions.TransientError, "is_retryable", lambda self: True
    )
    with pytest.raises(PanglossMergeBusyError, match="gave way"):
        await m.Person.merge(absorb=b.id, into=a.id)

    assert merged_into(db_driver, b.id) is None
    assert count_nodes(db_driver, "PGMerge") == 0
    assert len(edges_to(db_driver, b.id)) == 1


@no_type_check
async def test_nothing_is_merged_or_unmerged_while_the_database_is_migrated(
    db_driver, clear_database
):
    m = declare()
    a, b, c = await person(m, "A"), await person(m, "B"), await person(m, "C")
    result = await m.Person.merge(absorb=c.id, into=a.id)
    run(db_driver, "CREATE (:PGMigrationLock {id: 'lock', who: 'a migration'})")
    try:
        with pytest.raises(PanglossReadOnlyError):
            await m.Person.merge(absorb=b.id, into=a.id)
        with pytest.raises(PanglossReadOnlyError):
            await m.Person.unmerge(result.merge.id)
    finally:
        run(db_driver, "MATCH (l:PGMigrationLock) DELETE l")
    assert merged_into(db_driver, b.id) is None
    assert merged_into(db_driver, c.id) == str(a.id)
