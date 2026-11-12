"""Writing where entities have been merged (implementation_docs/entity-identity.md, risk 3 and decisions 3, 16, 19 and 25): a write
that names an absorbed entity is made to its survivor, in every way a write can name one; a write addressed to the
absorbed entity itself is refused"""

from typing import no_type_check

import pytest
from pangloss_core import storage_of
from pangloss_models import (
    PanglossMergedError,
    PanglossMergeError,
    PanglossReferenceError,
    create_heads,
)
from pangloss_models.merging import noting_resolved
from pydantic import AnyHttpUrl

from .merge_support import declare, edges_to, make, part, person, ref

pytestmark = pytest.mark.asyncio(loop_scope="session")

URL = "https://example.org/people/b"


async def merged_pair(m):
    a = await person(m, "A")
    b = await m.Person.Create(label="B", knows=[], urls=[URL]).save()
    result = await m.Person.merge(absorb=b.id, into=a.id)
    return a, b, result


@no_type_check
async def test_a_new_document_that_names_an_absorbed_entity_names_its_survivor(
    db_driver, clear_database
):
    m = declare()
    a, b, _ = await merged_pair(m)

    with noting_resolved() as resolved:
        mention = await make(m.Mention, "Names B", of=ref(b), others=[ref(b)])

    read = await m.Mention.get(mention.id)
    assert (read.of.id, [p.id for p in read.others]) == (a.id, [a.id])
    assert edges_to(db_driver, b.id) == []
    # and the write says so, to whoever asks
    assert resolved == [(str(b.id), str(a.id))]


@no_type_check
async def test_every_kind_of_relation_written_to_an_absorbed_entity_goes_to_its_survivor(
    db_driver, clear_database
):
    from .merge_support import every_kind

    m = declare()
    a, b, _ = await merged_pair(m)
    other = await person(m, "Other")

    await every_kind(m, b, other)

    assert edges_to(db_driver, b.id) == []
    assert len(edges_to(db_driver, a.id)) == 15


@no_type_check
async def test_an_absorbed_entity_named_by_its_url_is_its_survivor(
    db_driver, clear_database
):
    m = declare()
    a, b, _ = await merged_pair(m)

    mention = await make(
        m.Mention, "By URL", of={"type": "Person", "id": AnyHttpUrl(URL)}
    )

    assert (await m.Mention.get(mention.id)).of.id == a.id
    assert edges_to(db_driver, b.id) == []


@no_type_check
async def test_an_entity_written_in_a_document_by_the_id_of_an_absorbed_one_is_its_survivor(
    db_driver, clear_database
):
    m = declare()
    a, b, _ = await merged_pair(m)
    people = await m.Person.list()

    by_id = await make(
        m.Mention,
        "Inline by id",
        of={
            "type": "Person",
            "id": b.id,
            "label": "B",
            "create_new": True,
            "knows": [],
        },
    )
    by_url = await make(
        m.Mention,
        "Inline by URL",
        of={
            "type": "Person",
            "id": AnyHttpUrl(URL),
            "label": "B",
            "create_new": True,
            "knows": [],
        },
    )

    assert (await m.Mention.get(by_id.id)).of.id == a.id
    assert (await m.Mention.get(by_url.id)).of.id == a.id
    # no entity was made, and the survivor is as it was
    assert (await m.Person.list()).count == people.count
    assert (await m.Person.get(a.id)).label == "A"
    assert edges_to(db_driver, b.id) == []


@no_type_check
async def test_an_update_that_sends_an_absorbed_entity_back_names_its_survivor_once(
    db_driver, clear_database
):
    m = declare()
    a = await person(m, "A")
    b = await person(m, "B")
    c = await person(m, "C")
    rated = await make(
        m.Rated, "Rated", rated=[{**ref(c), "edge_properties": {"certainty": 1}}]
    )
    factoid = await make(
        m.Factoid, "Factoid", statements=[part(m.Statement, "S", concerns=[ref(c)])]
    )
    await m.Person.merge(absorb=b.id, into=a.id)

    # (a form that was open before the merge, or a script with the old id)
    await m.Rated.Update(
        id=rated.id,
        label="Rated",
        rated=[
            {**ref(b), "edge_properties": {"certainty": 5}},
            {**ref(c), "edge_properties": {"certainty": 1}},
            {**ref(a), "edge_properties": {"certainty": 9}},
        ],
    ).save()
    statement_id = (await m.Factoid.get(factoid.id)).statements[0].id
    await m.Factoid.Update(
        id=factoid.id,
        label="Factoid",
        statements=[
            {**part(m.Statement, "S", concerns=[ref(b), ref(c)]), "id": statement_id}
        ],
    ).save()

    # a list that is given both has the survivor once: the one it was given as itself
    assert [
        (p.id, p.edge_properties.certainty) for p in (await m.Rated.get(rated.id)).rated
    ] == [
        (c.id, 1),
        (a.id, 9),
    ]
    assert [p.id for p in (await m.Factoid.get(factoid.id)).statements[0].concerns] == [
        a.id,
        c.id,
    ]
    assert edges_to(db_driver, b.id) == []


@no_type_check
async def test_a_relation_that_keeps_what_it_names_is_written_as_given(
    db_driver, clear_database
):
    m = declare()
    a, b, _ = await merged_pair(m)

    with noting_resolved() as resolved:
        same = await make(m.SameAs, "A is B", entities=[ref(a), ref(b)])

    assert [e.id for e in (await m.SameAs.get(same.id)).entities] == [a.id, b.id]
    assert resolved == []
    assert edges_to(db_driver, b.id) == [("SameAs", "entities", 1)]


@no_type_check
async def test_a_chain_of_merges_is_resolved_to_its_end(db_driver, clear_database):
    m = declare()
    a, b, x = await person(m, "A"), await person(m, "B"), await person(m, "X")
    await m.Person.merge(absorb=x.id, into=b.id)
    await m.Person.merge(absorb=b.id, into=a.id)

    mention = await make(m.Mention, "Names X and B", of=ref(x), others=[ref(b), ref(x)])

    read = await m.Mention.get(mention.id)
    assert (read.of.id, [p.id for p in read.others]) == (a.id, [a.id])
    assert edges_to(db_driver, x.id) == edges_to(db_driver, b.id) == []


@no_type_check
async def test_several_heads_written_together_resolve_what_they_name(
    db_driver, clear_database
):
    m = declare()
    a, b, _ = await merged_pair(m)

    group, mention = await create_heads(
        m.Group.Create(label="Group", members=[ref(b)]),
        m.Mention.Create(label="Mention", of=ref(b), others=[]),
    )

    assert [p.id for p in (await m.Group.get(group.id)).members] == [a.id]
    assert (await m.Mention.get(mention.id)).of.id == a.id
    assert edges_to(db_driver, b.id) == []


@no_type_check
async def test_a_survivor_of_another_class_is_checked_against_the_relation(
    db_driver, clear_database
):
    m = declare()
    a = await person(m, "A person")
    b = await make(m.Poet, "A poet", works=[])
    await m.Person.merge(absorb=b.id, into=a.id, as_class=m.Person)

    # (the absorbed entity was a poet; what it has become part of is not)
    with pytest.raises(PanglossReferenceError, match="not of an allowed type"):
        await make(m.Poem, "A poem", by=ref(b, "Poet"))
    assert edges_to(db_driver, b.id) == []


@no_type_check
async def test_a_write_addressed_to_an_absorbed_entity_is_refused_naming_its_survivor(
    db_driver, clear_database
):
    m = declare()
    a, b, _ = await merged_pair(m)

    with pytest.raises(PanglossMergedError) as update:
        await m.Person.Update(id=b.id, label="B, edited", knows=[]).save()
    assert (update.value.id, update.value.merged_into) == (b.id, a.id)
    with pytest.raises(PanglossMergedError):
        await m.Person.Update(id=b.id, label="B, edited", knows=[]).save(
            expected_version=1
        )
    with pytest.raises(PanglossMergedError) as delete:
        await m.Person.delete(b.id)
    assert delete.value.merged_into == a.id
    with pytest.raises(PanglossMergedError):
        await m.Person.undelete(b.id)
    with pytest.raises(PanglossMergedError):
        await m.Poet.Update(id=b.id, label="A poet now", knows=[], works=[]).save(
            changing_class_from=m.Person
        )
    check = await storage_of().operations.check_deletable(m.Person, b.id)
    assert not check.deletable and str(a.id) in check.reason

    # nothing of it changed
    itself = await m.Person.get(b.id, follow_merge=False)
    assert (itself.label, itself.type, itself.meta.version) == ("B", "Person", 1)


@no_type_check
async def test_a_survivor_can_be_deleted_and_the_merge_undone_once_it_is_back(
    db_driver, clear_database
):
    m = declare()
    a, b, result = await merged_pair(m)

    await m.Person.delete(a.id)

    # the absorbed entity's id now leads to a deleted entity
    assert await m.Person.get(b.id) is None
    with pytest.raises(PanglossReferenceError, match="has been deleted"):
        await make(m.Mention, "Names B", of=ref(b))
    with pytest.raises(PanglossMergeError, match="undelete it"):
        await m.Person.unmerge(result.merge.id)

    await m.Person.undelete(a.id)
    undone = await m.Person.unmerge(result.merge.id)
    assert undone.merge.state == "undone"
    assert (await m.Person.get(b.id)).id == b.id


@no_type_check
async def test_after_an_undo_the_absorbed_entity_is_written_to_as_before(
    db_driver, clear_database
):
    m = declare()
    a, b, result = await merged_pair(m)
    await m.Person.unmerge(result.merge.id)

    mention = await make(m.Mention, "Names B", of=ref(b))
    await m.Person.Update(id=b.id, label="B, edited", knows=[], urls=[URL]).save()

    assert (await m.Mention.get(mention.id)).of.id == b.id
    assert (await m.Person.get(AnyHttpUrl(URL))).label == "B, edited"
    assert a.id
