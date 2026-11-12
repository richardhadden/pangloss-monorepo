"""Undoing a merge of entities (implementation_docs/entity-identity.md, "Undoing a merge" and decisions 6, 21 and 25): what goes back,
what cannot be put back and is listed, what stays on the survivor, and when an undo is refused"""

import uuid
from typing import no_type_check

import pytest
from pangloss_models import PanglossMergeError, PanglossNotFoundError

from .helpers import count_nodes, run
from .merge_support import (
    declare,
    edges_to,
    make,
    merged_into,
    part,
    person,
    ref,
    version_of,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


@no_type_check
async def test_a_document_saved_since_the_merge_with_its_ids_still_goes_back(
    db_driver, clear_database
):
    m = declare()
    a, b = await person(m, "A"), await person(m, "B")
    factoid = await make(
        m.Factoid, "Factoid", statements=[part(m.Statement, "S", concerns=[ref(b)])]
    )
    result = await m.Person.merge(absorb=b.id, into=a.id)
    # (edited in the form, which sends back the ids it read: the nodes are the same nodes)
    read = await m.Factoid.get(factoid.id)
    await m.Factoid.Update(
        id=factoid.id,
        label="Factoid, edited",
        statements=[
            {
                **part(m.Statement, "S, edited", concerns=[ref(a)]),
                "id": read.statements[0].id,
            }
        ],
    ).save()

    undone = await m.Person.unmerge(result.merge.id)

    assert (undone.restored, undone.unmatched) == (1, [])
    after = await m.Factoid.get(factoid.id)
    assert (after.label, after.statements[0].label) == ("Factoid, edited", "S, edited")
    assert [p.id for p in after.statements[0].concerns] == [b.id]


@no_type_check
async def test_what_cannot_be_put_back_is_listed_and_not_guessed(
    db_driver, clear_database
):
    m = declare()
    a, b, c = await person(m, "A"), await person(m, "B"), await person(m, "C")
    untouched = await make(m.Mention, "Untouched", of=ref(b))
    repointed = await make(m.Mention, "Pointed elsewhere", of=ref(b))
    deleted = await make(m.Mention, "Deleted", of=ref(b))
    rewritten = await make(
        m.Factoid, "Rewritten", statements=[part(m.Statement, "S", concerns=[ref(b)])]
    )
    removed = await make(
        m.Factoid,
        "Statement removed",
        statements=[
            part(m.Statement, "Stays", concerns=[ref(c)]),
            part(m.Statement, "Goes", concerns=[ref(b)]),
        ],
    )
    result = await m.Person.merge(absorb=b.id, into=a.id)

    await m.Mention.Update(
        id=repointed.id, label="Pointed elsewhere", of=ref(c), others=[]
    ).save()
    await m.Mention.delete(deleted.id)
    # (saved by a script that does not send the ids of what is nested: the statement is a new node)
    await m.Factoid.Update(
        id=rewritten.id,
        label="Rewritten",
        statements=[part(m.Statement, "S", concerns=[ref(a)])],
    ).save()
    kept_statement = (await m.Factoid.get(removed.id)).statements[0]
    await m.Factoid.Update(
        id=removed.id,
        label="Statement removed",
        statements=[
            {**part(m.Statement, "Stays", concerns=[ref(c)]), "id": kept_statement.id}
        ],
    ).save()

    undone = await m.Person.unmerge(result.merge.id)

    assert undone.restored == 1
    assert (await m.Mention.get(untouched.id)).of.id == b.id
    assert sorted(
        (u["reason"], u["source_type"], u["field"], uuid.UUID(u["head"]))
        for u in undone.unmatched
    ) == sorted(
        [
            ("changed", "Mention", "of", repointed.id),
            ("deleted", "Mention", "of", deleted.id),
            ("gone", "Statement", "concerns", rewritten.id),
            ("gone", "Statement", "concerns", removed.id),
        ]
    )
    # nothing was guessed: each is as its last edit left it
    assert (await m.Mention.get(repointed.id)).of.id == c.id
    assert [
        p.id for p in (await m.Factoid.get(rewritten.id)).statements[0].concerns
    ] == [a.id]
    assert version_of(db_driver, repointed.id) == 3
    assert version_of(db_driver, untouched.id) == 3
    await m.Mention.undelete(deleted.id)
    assert (await m.Mention.get(deleted.id)).of.id == a.id
    # the rewritten factoid is one of those written since the merge, to look at by hand
    assert rewritten.id in {h.id for h in undone.made_since}


@no_type_check
async def test_what_was_written_to_the_survivor_since_the_merge_stays_on_it_and_is_listed(
    db_driver, clear_database
):
    m = declare()
    a, b = await person(m, "A"), await person(m, "B")
    of_a_before = await make(m.Mention, "Of A, before", of=ref(a))
    of_b_before = await make(m.Mention, "Of B, before", of=ref(b))
    result = await m.Person.merge(absorb=b.id, into=a.id)
    since_as_a = await make(m.Mention, "Since, naming A", of=ref(a))
    since_as_b = await make(m.Mention, "Since, naming B", of=ref(b))
    await m.Mention.Update(
        id=of_a_before.id, label="Of A, before (edited since)", of=ref(a), others=[]
    ).save()

    undone = await m.Person.unmerge(result.merge.id)

    # which of them were meant for the absorbed entity cannot be told: all stay, and all are listed
    assert [(h.id, h.label) for h in undone.made_since] == [
        (of_a_before.id, "Of A, before (edited since)"),
        (since_as_a.id, "Since, naming A"),
        (since_as_b.id, "Since, naming B"),
    ]
    assert (await m.Mention.get(since_as_b.id)).of.id == a.id
    assert (await m.Mention.get(of_b_before.id)).of.id == b.id
    assert undone.restored == 1


@no_type_check
async def test_the_fields_of_a_survivor_that_changed_since_are_not_put_back_but_given(
    db_driver, clear_database
):
    m = declare()
    a, b = await person(m, "A", born=1800), await person(m, "B", died=1870)
    await make(m.Mention, "Of B", of=ref(b))
    result = await m.Person.merge(absorb=b.id, into=a.id)
    await m.Person.Update(
        id=a.id, label="A, corrected", born=1799, died=1870, aliases=["B"], knows=[]
    ).save()

    undone = await m.Person.unmerge(result.merge.id)

    assert not undone.fields_restored
    assert "changed since the merge" in undone.draft_reason
    assert (
        undone.draft_type,
        undone.draft["label"],
        undone.draft["born"],
        undone.draft["died"],
    ) == (
        "Person",
        "A",
        1800,
        None,
    )
    # the survivor is as its last edit left it; the references and the mark are undone all the same
    survivor = await m.Person.get(a.id)
    assert (survivor.label, survivor.born, survivor.died, survivor.meta.version) == (
        "A, corrected",
        1799,
        1870,
        3,
    )
    assert merged_into(db_driver, b.id) is None
    assert undone.restored == 1


@no_type_check
async def test_a_merge_is_undone_while_a_later_one_into_the_same_survivor_stands(
    db_driver, clear_database
):
    m = declare()
    a, b, c = await person(m, "A"), await person(m, "B"), await person(m, "C")
    of_b = await make(m.Mention, "Of B", of=ref(b))
    of_c = await make(m.Mention, "Of C", of=ref(c))
    first = await m.Person.merge(absorb=b.id, into=a.id)
    second = await m.Person.merge(absorb=c.id, into=a.id)

    undone = await m.Person.unmerge(first.merge.id)

    # B's references are B's again and C's are still the survivor's; the survivor's fields are for a person to sort
    assert (await m.Mention.get(of_b.id)).of.id == b.id
    assert (await m.Mention.get(of_c.id)).of.id == a.id
    assert not undone.fields_restored and undone.draft["aliases"] == []
    assert (await m.Person.get(a.id)).aliases == ["B", "C"]
    assert (merged_into(db_driver, b.id), merged_into(db_driver, c.id)) == (
        None,
        str(a.id),
    )

    # the survivor has not changed since the second merge, so that one's undo puts its fields back as they were
    # before it: with what the first merge gave it, which was for a person to sort out
    again = await m.Person.unmerge(second.merge.id)
    assert (await m.Mention.get(of_c.id)).of.id == c.id
    assert again.fields_restored
    assert (await m.Person.get(a.id)).aliases == ["B"]


@no_type_check
async def test_a_reference_two_merges_made_one_is_two_again_when_both_are_undone(
    db_driver, clear_database
):
    m = declare()
    a, b, c, d = [await person(m, name) for name in "ABCD"]
    rated = await make(
        m.Rated,
        "Rates B, D and C",
        rated=[
            {**ref(b), "edge_properties": {"certainty": 1}},
            {**ref(d), "edge_properties": {"certainty": 2}},
            {**ref(c), "edge_properties": {"certainty": 3}},
        ],
    )
    first = await m.Person.merge(absorb=b.id, into=a.id)
    # (the document now names the survivor, so the second merge drops C's place in the list)
    second = await m.Person.merge(absorb=c.id, into=a.id)
    assert [h.id for h in second.collapsed] == [rated.id]

    def read(view):
        return [(p.id, p.edge_properties.certainty) for p in view.rated]

    assert read(await m.Rated.get(rated.id)) == [(a.id, 1), (d.id, 2)]

    await m.Person.unmerge(first.merge.id)
    # the survivor is still named, as C, which the second merge made it: with C's own properties, in C's place
    assert read(await m.Rated.get(rated.id)) == [(b.id, 1), (d.id, 2), (a.id, 3)]

    await m.Person.unmerge(second.merge.id)
    assert read(await m.Rated.get(rated.id)) == [(b.id, 1), (d.id, 2), (c.id, 3)]
    assert edges_to(db_driver, a.id) == []


@no_type_check
async def test_in_a_chain_the_latest_merge_is_undone_first(db_driver, clear_database):
    m = declare()
    a, b, d = await person(m, "A"), await person(m, "B"), await person(m, "D")
    of_b = await make(m.Mention, "Of B", of=ref(b))
    of_a = await make(m.Mention, "Of A", of=ref(a))
    inner = await m.Person.merge(absorb=b.id, into=a.id)
    outer = await m.Person.merge(absorb=a.id, into=d.id)
    assert (await m.Mention.get(of_b.id)).of.id == d.id

    with pytest.raises(
        PanglossMergeError, match=f"merged into {d.id} since: undo that merge first"
    ):
        await m.Person.unmerge(inner.merge.id)
    assert merged_into(db_driver, b.id) == str(a.id)

    await m.Person.unmerge(outer.merge.id)
    assert (await m.Mention.get(of_b.id)).of.id == a.id
    await m.Person.unmerge(inner.merge.id)
    assert (await m.Mention.get(of_b.id)).of.id == b.id
    assert (await m.Mention.get(of_a.id)).of.id == a.id
    assert [merged_into(db_driver, e.id) for e in (a, b, d)] == [None, None, None]


@no_type_check
async def test_a_merge_is_undone_once(db_driver, clear_database):
    m = declare()
    a, b = await person(m, "A"), await person(m, "B")
    result = await m.Person.merge(absorb=b.id, into=a.id)
    await m.Person.unmerge(result.merge.id)

    with pytest.raises(PanglossMergeError, match="is undone"):
        await m.Person.unmerge(result.merge.id)
    with pytest.raises(PanglossNotFoundError):
        await m.Person.unmerge(uuid.uuid7())
    # and the pair can be merged again, as a merge of its own
    again = await m.Person.merge(absorb=b.id, into=a.id)
    assert again.merge.id != result.merge.id
    assert count_nodes(db_driver, "PGMerge") == 2


@no_type_check
async def test_a_dry_run_of_an_undo_says_what_it_would_do_and_writes_nothing(
    db_driver, clear_database
):
    m = declare()
    a, b, c = await person(m, "A"), await person(m, "B"), await person(m, "C")
    stays = await make(m.Mention, "Goes back", of=ref(b))
    changed = await make(m.Mention, "Changed", of=ref(b))
    result = await m.Person.merge(absorb=b.id, into=a.id)
    await m.Mention.Update(id=changed.id, label="Changed", of=ref(c), others=[]).save()

    would = await m.Person.unmerge(result.merge.id, dry_run=True)

    assert (
        would.restored,
        [u["reason"] for u in would.unmatched],
        would.fields_restored,
    ) == (1, ["changed"], True)
    assert merged_into(db_driver, b.id) == str(a.id)
    assert (await m.Mention.get(stays.id)).of.id == a.id
    assert (await m.Person.merges(a.id))[0].state == "done"
    assert version_of(db_driver, stays.id) == 2
    assert (await m.Person.get(a.id)).aliases == ["B"]

    done = await m.Person.unmerge(result.merge.id)
    assert (done.restored, len(done.unmatched)) == (would.restored, 1)


@no_type_check
async def test_an_undo_after_a_migration_has_to_be_confirmed(db_driver, clear_database):
    m = declare()
    a, b = await person(m, "A"), await person(m, "B")
    mention = await make(m.Mention, "Of B", of=ref(b))
    result = await m.Person.merge(absorb=b.id, into=a.id)
    # (a migration applied since: the moves the merge recorded may name fields that have changed)
    run(
        db_driver,
        "CREATE (:PGMigration {app: 'project', name: '0009_renamefield', status: 'applied'})",
    )

    with pytest.raises(PanglossMergeError, match="migrated since the merge"):
        await m.Person.unmerge(result.merge.id)
    assert merged_into(db_driver, b.id) == str(a.id)
    # what could still be put back can be seen first
    would = await m.Person.unmerge(result.merge.id, dry_run=True, confirm_migrated=True)
    assert (would.restored, would.unmatched) == (1, [])

    undone = await m.Person.unmerge(result.merge.id, confirm_migrated=True)
    assert undone.restored == 1
    assert (await m.Mention.get(mention.id)).of.id == b.id
    run(db_driver, "MATCH (m:PGMigration {app: 'project'}) DELETE m")


@no_type_check
async def test_a_dropped_reference_is_not_put_back_into_a_list_that_no_longer_names_the_survivor(
    db_driver, clear_database
):
    m = declare()
    a, b, c = await person(m, "A"), await person(m, "B"), await person(m, "C")
    group = await make(m.Group, "Group", members=[ref(a), ref(b)])
    result = await m.Person.merge(absorb=b.id, into=a.id)
    await m.Group.Update(id=group.id, label="Group", members=[ref(c)]).save()

    undone = await m.Person.unmerge(result.merge.id)

    assert [(u["reason"], u["field"]) for u in undone.unmatched] == [
        ("changed", "members")
    ]
    assert [p.id for p in (await m.Group.get(group.id)).members] == [c.id]


@no_type_check
async def test_an_undo_gives_back_the_class_the_survivor_had_or_says_why_not(
    db_driver, clear_database
):
    m = declare()
    a = await person(m, "A person")
    b = await make(m.Poet, "A poet", works=["Odes"])
    result = await m.Person.merge(absorb=b.id, into=a.id)
    # (since the merge something refers to the survivor as the poet it became)
    poem = await make(m.Poem, "A later poem", by=ref(a, "Poet"))

    undone = await m.Person.unmerge(result.merge.id)

    # it cannot be a plain person again while a poem is by it: the references still go back, and the rest is said
    assert not undone.fields_restored
    assert "Poem" in undone.draft_reason and undone.draft_type == "Person"
    assert (await m.Person.get(a.id)).type == "Poet"
    assert merged_into(db_driver, b.id) is None
    assert (await m.Poem.get(poem.id)).by.id == a.id
    assert [h.id for h in undone.made_since] == [poem.id]
