"""History and merged entities (`pangloss-history`; implementation_docs/entity-identity.md, risk 1): what is recorded of a merge,
and the restores a merge that stands refuses"""

from typing import no_type_check

import pytest
from pangloss_history import PanglossRestoreError, api, listener
from pangloss_history.restore import merged_problems, restore
from pangloss_models.merging import noting_resolved

from .merge_support import declare, make, merged_into, person, ref
from .test_history_restore import history  # noqa: F401

pytestmark = pytest.mark.asyncio(loop_scope="session")


def drain():
    listener.get_recorder().drain()


async def edit(m, entity, **changes):
    current = await m.Person.get_for_edit(entity.id)
    return await m.Person.Update(
        **{**current.model_dump(exclude={"meta"}), **changes}
    ).save()


@no_type_check
async def test_a_merge_and_its_undoing_are_recorded_for_both_entities(
    db_driver,
    clear_database,
    history,  # noqa: F811
):
    m = declare()
    store = history()
    a = await person(m, "John Smith")
    b = await person(m, "Jon Smyth")
    mention = await make(m.Mention, "Of B", of=ref(b))
    merge = (await m.Person.merge(absorb=b.id, into=a.id)).merge
    await m.Person.unmerge(merge.id)
    drain()

    # the survivor: the fields the merge gave it are a version, and so are those the undo put back
    of_a = store.versions(a.id)
    assert [(r.version, r.op) for r in of_a] == [
        (1, "create"),
        (2, "update"),
        (3, "update"),
    ]
    assert store.get(a.id, 2).data()["aliases"] == ["Jon Smyth"]
    assert store.get(a.id, 3).data()["aliases"] == []
    assert merge.survivor_version == 2
    # the absorbed entity: marked and unmarked, at the version it had, with no content
    assert [(r.version, r.op) for r in store.versions(b.id)] == [
        (1, "create"),
        (1, "merge"),
        (1, "unmerge"),
    ]
    assert store.get(b.id, 1).data()["label"] == "Jon Smyth"
    # the document that was moved, and moved back: a version each time
    assert [(r.version, r.op) for r in store.versions(mention.id)] == [
        (1, "create"),
        (2, "update"),
        (3, "update"),
    ]
    assert store.get(mention.id, 2).data()["of"]["id"] == str(a.id)
    assert store.get(mention.id, 3).data()["of"]["id"] == str(b.id)


@no_type_check
async def test_the_absorbed_entity_is_not_restored_while_the_merge_stands(
    db_driver,
    clear_database,
    history,  # noqa: F811
):
    m = declare()
    store = history()
    a = await person(m, "A")
    b = await person(m, "B", born=1800)
    await edit(m, b, born=1801)
    merge = (await m.Person.merge(absorb=b.id, into=a.id)).merge
    drain()

    with pytest.raises(PanglossRestoreError) as refused:
        await restore(store, m.Person, b.id, 1)
    assert [p["kind"] for p in refused.value.problems] == ["merged"]
    assert refused.value.problems[0]["merge"] == str(merge.id)
    assert "undo the merge" in str(refused.value)
    # nothing was written: it is merged still, and as it was
    assert merged_into(db_driver, b.id) == str(a.id)
    assert (await m.Person.get(b.id, follow_merge=False)).born == 1801
    # (its version is its own, not the survivor's, where the history of it is read)
    assert await api.current_version(m.Person, b.id) == 2
    assert await api.current_version(m.Person, a.id) == 2

    await m.Person.unmerge(merge.id)
    drain()
    assert await merged_problems(m.Person, b.id, 1) == []
    assert await restore(store, m.Person, b.id, 1) == 3
    assert (await m.Person.get(b.id)).born == 1800


@no_type_check
async def test_the_survivor_is_not_restored_to_a_version_from_before_the_merge(
    db_driver,
    clear_database,
    history,  # noqa: F811
):
    m = declare()
    store = history()
    a = await person(m, "A", born=1800)
    b = await person(m, "B")
    mention = await make(m.Mention, "Of B", of=ref(b))
    merge = (await m.Person.merge(absorb=b.id, into=a.id)).merge
    await edit(m, a, born=1805)
    drain()

    with pytest.raises(PanglossRestoreError) as refused:
        await restore(store, m.Person, a.id, 1)
    assert [p["kind"] for p in refused.value.problems] == ["merged"]
    assert "from before this Person absorbed B" in str(refused.value)
    assert (await m.Person.get(a.id)).meta.version == 3
    # a version the merge made, or a later one, is the survivor's own to put back
    assert await merged_problems(m.Person, a.id, 2) == []
    assert await restore(store, m.Person, a.id, 2) == 4
    now = await m.Person.get(a.id)
    assert (now.born, now.aliases) == (1800, ["B"])
    assert merged_into(db_driver, b.id) == str(a.id)
    assert (await m.Mention.get(mention.id)).of.id == a.id

    # and once the merge is undone, the versions from before it too
    await m.Person.unmerge(merge.id)
    drain()
    assert await restore(store, m.Person, a.id, 1) == 5
    assert (await m.Person.get(a.id)).aliases == []


@no_type_check
async def test_a_document_restored_to_a_version_that_named_a_merged_entity_names_the_survivor(
    db_driver,
    clear_database,
    history,  # noqa: F811
):
    m = declare()
    store = history()
    a, b, c = await person(m, "A"), await person(m, "B"), await person(m, "C")
    mention = await make(m.Mention, "A mention", of=ref(b), others=[ref(c)])
    current = await m.Mention.get(mention.id)
    await m.Mention.Update(
        **{**current.model_dump(exclude={"meta"}), "of": ref(c), "others": []}
    ).save()
    merge = (await m.Person.merge(absorb=b.id, into=a.id)).merge
    drain()

    # version 1 named B, which is merged now: it is written with A, and B is not brought back
    with noting_resolved() as resolved:
        assert await restore(store, m.Mention, mention.id, 1) == 3
    assert resolved == [(str(b.id), str(a.id))]
    now = await m.Mention.get(mention.id)
    assert now.of.id == a.id and [p.id for p in now.others] == [c.id]
    assert merged_into(db_driver, b.id) == str(a.id)
    assert (await m.Person.get(b.id)).id == a.id

    # after the undo it is A's still: made since the merge, and for a person to move
    undone = await m.Person.unmerge(merge.id)
    assert [h.id for h in undone.made_since] == [mention.id]
    assert (await m.Mention.get(mention.id)).of.id == a.id


@no_type_check
async def test_a_restore_does_not_resolve_a_relation_that_a_merge_leaves_where_it_is(
    db_driver,
    clear_database,
    history,  # noqa: F811
):
    m = declare()
    store = history()
    a, b, c = await person(m, "A"), await person(m, "B"), await person(m, "C")
    same = await make(m.SameAs, "A is B", entities=[ref(a), ref(b)], argument="one")
    current = await m.SameAs.get(same.id)
    await m.SameAs.Update(
        **{**current.model_dump(exclude={"meta"}), "argument": "two"}
    ).save()
    await m.Person.merge(absorb=b.id, into=a.id)
    drain()

    assert await restore(store, m.SameAs, same.id, 1) == 3
    now = await m.SameAs.get(same.id)
    # ("A is B" has not become "A is A")
    assert [p.id for p in now.entities] == [a.id, b.id] and now.argument == "one"
    assert c.id


@no_type_check
async def test_a_restore_that_names_an_entity_merged_into_a_deleted_one_is_a_problem(
    db_driver,
    clear_database,
    history,  # noqa: F811
):
    m = declare()
    store = history()
    a, b, c = await person(m, "A"), await person(m, "B"), await person(m, "C")
    mention = await make(m.Mention, "A mention", of=ref(b))
    current = await m.Mention.get(mention.id)
    await m.Mention.Update(
        **{**current.model_dump(exclude={"meta"}), "of": ref(c)}
    ).save()
    await m.Person.merge(absorb=b.id, into=a.id)
    await m.Person.delete(a.id)
    drain()

    with pytest.raises(PanglossRestoreError) as refused:
        await restore(store, m.Mention, mention.id, 1)
    assert [p["kind"] for p in refused.value.problems] == ["reference-missing"]
    assert "which has been deleted" in str(refused.value)
    assert (await m.Mention.get(mention.id)).of.id == c.id
