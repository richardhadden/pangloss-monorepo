"""What is left on entities that were merged, as `pangloss check-data` finds and moves it (implementation_docs/entity-identity.md,
risk 3): a reference that a write made around the models, which do not let one be made"""

from typing import no_type_check

import pytest
from pangloss_core import storage_of

from .helpers import run
from .merge_support import declare, edges_to, make, moves_of, person, ref

pytestmark = pytest.mark.asyncio(loop_scope="session")


def ops():
    return storage_of().operations


def point_at(db_driver, document, field: str, old, new) -> None:
    """Re-point a document's relation from one entity to another by Cypher: what a write around the models does"""
    run(
        db_driver,
        f"""
        MATCH (d:PGIndexableNode {{id: $d}})-[edge:{field}]->(:Entity {{id: $old}})-[back:{field}_reverse]->(d)
        MATCH (new:Entity {{id: $new}})
        DELETE edge, back
        CREATE (d)-[:{field} {{pg_position: 0}}]->(new)
        CREATE (new)-[:{field}_reverse {{reverse: true}}]->(d)
        """,
        d=str(document.id),
        old=str(old.id),
        new=str(new.id),
    )


@no_type_check
async def test_nothing_is_found_where_merges_left_nothing(db_driver, clear_database):
    m = declare()
    a, b, c = await person(m, "A"), await person(m, "B"), await person(m, "C")
    await make(m.Mention, "Of B", of=ref(b))
    # (a relation a merge leaves where it is, and the absorbed entity's own relations, are not stray)
    await make(m.SameAs, "B is C", entities=[ref(b), ref(c)])
    edit = await m.Person.get_for_edit(b.id)
    await m.Person.Update(
        **{**edit.model_dump(exclude={"meta"}), "knows": [ref(c)]}
    ).save()
    assert await ops().stray_references() == []
    await m.Person.merge(absorb=b.id, into=a.id)
    await m.Person.merge(absorb=c.id, into=a.id)
    assert edges_to(db_driver, b.id) == [("SameAs", "entities", 0)]
    assert await ops().stray_references() == []
    assert await ops().move_stray_references() == 0
    assert await ops().unfinished_merges() == []


@no_type_check
async def test_a_reference_written_around_the_models_is_found_and_moved(
    db_driver, clear_database
):
    m = declare()
    a, b = await person(m, "A"), await person(m, "B")
    late = await make(m.Mention, "Late", of=ref(a))
    merge = (await m.Person.merge(absorb=b.id, into=a.id)).merge
    point_at(db_driver, late, "of", a, b)

    strays = await ops().stray_references()
    assert len(strays) == 1
    stray = strays[0]
    assert (stray.absorbed, stray.survivor, stray.merge) == (b.id, a.id, merge.id)
    assert (stray.head, stray.head_type) == (late.id, "Mention")
    assert (stray.source_type, stray.field, stray.absorbed_label) == (
        "Mention",
        "of",
        "B",
    )
    # (it shows: a merged entity is not hidden where something still points at it)
    assert (await m.Mention.get(late.id)).of.merged_into == a.id

    assert await ops().move_stray_references() == 1
    assert await ops().stray_references() == []
    assert (await m.Mention.get(late.id)).of.id == a.id
    # recorded with the merge, so an undo puts it back with the rest
    assert [move["late"] for move in moves_of(db_driver, merge.id)] == [True]


@no_type_check
async def test_what_is_on_an_entity_merged_twice_over_ends_on_the_last_survivor(
    db_driver, clear_database
):
    m = declare()
    a, b, d = await person(m, "A"), await person(m, "B"), await person(m, "D")
    on_b = await make(m.Mention, "On B", of=ref(a))
    on_a = await make(m.Mention, "On A", of=ref(d))
    await m.Person.merge(absorb=b.id, into=a.id)
    await m.Person.merge(absorb=a.id, into=d.id)
    point_at(db_driver, on_b, "of", d, b)
    point_at(db_driver, on_a, "of", d, a)

    assert sorted(s.absorbed_label for s in await ops().stray_references()) == [
        "A",
        "B",
    ]
    # (B's goes to A by B's merge, and from A to D by A's)
    assert await ops().move_stray_references() == 3
    assert await ops().stray_references() == []
    assert (await m.Mention.get(on_b.id)).of.id == d.id
    assert (await m.Mention.get(on_a.id)).of.id == d.id


@no_type_check
async def test_a_mark_with_no_merge_behind_it_is_reported_and_left(
    db_driver, clear_database
):
    m = declare()
    a, b = await person(m, "A"), await person(m, "B")
    mention = await make(m.Mention, "Of B", of=ref(b))
    # (no operation of Pangloss leaves this: a mark set by hand)
    run(
        db_driver, "MATCH (b {id: $b}) SET b.merged_into = $a", a=str(a.id), b=str(b.id)
    )
    strays = await ops().stray_references()
    assert [(s.head, s.merge) for s in strays] == [(mention.id, None)]
    assert await ops().move_stray_references() == 0
    assert len(await ops().stray_references()) == 1


@no_type_check
async def test_a_large_merge_that_stopped_is_reported_as_unfinished(
    db_driver, clear_database, monkeypatch
):
    from pangloss_core import settings as core_settings

    m = declare()
    a, b = await person(m, "A"), await person(m, "B")
    for index in range(4):
        await make(m.Mention, f"Of B {index}", of=ref(b))
    monkeypatch.setattr(core_settings.SETTINGS, "MERGE_LIMIT", 2)
    from pangloss_cypher import merge as merging

    batches = merging._batches

    async def stop(merge_id, limit):
        raise RuntimeError("the server stopped")

    monkeypatch.setattr(merging, "_batches", stop)
    with pytest.raises(RuntimeError):
        await m.Person.merge(absorb=b.id, into=a.id, allow_large=True)
    unfinished = await ops().unfinished_merges()
    assert [(x.state, x.survivor, x.absorbed) for x in unfinished] == [
        ("running", a.id, b.id)
    ]
    # (its references are not stray: the merge is to be gone on with, or undone)
    monkeypatch.setattr(merging, "_batches", batches)
    await m.Person.merge(absorb=b.id, into=a.id, allow_large=True)
    assert await ops().unfinished_merges() == []
    assert await ops().stray_references() == []
