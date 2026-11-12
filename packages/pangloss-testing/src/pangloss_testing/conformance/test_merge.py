"""Merging two entities (`Entity.merge`; implementation_docs/entity-identity.md, part 1): what a merge does, what it refuses, and what
it records"""

from typing import no_type_check

import pytest
from pangloss_models import (
    PanglossMergeError,
    PanglossMergeTooLargeError,
    PanglossNotFoundError,
    PanglossVersionConflictError,
    PanglossWriteError,
    hooks,
)
from pydantic import AnyHttpUrl

from .helpers import count_nodes, run

from .merge_support import (
    declare,
    edges_to,
    every_kind,
    make,
    merged_into,
    moves_of,
    person,
    ref,
    reverse_edges_from,
    version_of,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


@no_type_check
async def test_a_merge_moves_what_refers_to_the_absorbed_entity_and_keeps_it_marked(
    db_driver, clear_database
):
    m = declare()
    a = await person(m, "John Smith", born=1800)
    b = await person(m, "Jon Smyth", died=1870)
    of_a = await make(m.Mention, "Of A", of=ref(a))
    of_b = await make(m.Mention, "Of B", of=ref(b), others=[ref(b)])

    result = await m.Person.merge(absorb=b.id, into=a.id)

    assert result.merge.state == "done"
    assert (result.merge.survivor, result.merge.absorbed) == (a.id, b.id)
    assert (result.merge.heads, result.merge.moved, result.merge.dropped) == (1, 2, 0)
    # everything that referred to B refers to A, by forward and reverse edges
    assert edges_to(db_driver, b.id) == []
    assert reverse_edges_from(db_driver, b.id) == []
    assert edges_to(db_driver, a.id) == [
        ("Mention", "of", 0),
        ("Mention", "of", 0),
        ("Mention", "others", 0),
    ]
    assert (await m.Mention.get(of_b.id)).of.id == a.id
    # B is kept as it was, and marked
    assert merged_into(db_driver, b.id) == str(a.id)
    kept = await m.Person.get(b.id, follow_merge=False)
    assert (kept.label, kept.died, kept.meta.merged_into) == ("Jon Smyth", 1870, a.id)
    # A has its own fields, B's where it had none, and B's label where the class says
    survivor = await m.Person.get(a.id)
    assert (survivor.label, survivor.born, survivor.died) == ("John Smith", 1800, 1870)
    assert survivor.aliases == ["Jon Smyth"]
    assert {i.id for i in survivor.of_reverse} == {of_a.id, of_b.id}
    # each head that changed has a new version; the one that did not has not
    assert version_of(db_driver, of_b.id) == 2
    assert version_of(db_driver, of_a.id) == 1
    assert version_of(db_driver, a.id) == 2
    assert version_of(db_driver, b.id) == 1
    assert [
        (r["source"], r["field"], r["reverse"])
        for r in moves_of(db_driver, result.merge.id)
    ] == [
        ("Mention", "of", "of_reverse"),
        ("Mention", "others", "others_reverse"),
    ]


@no_type_check
async def test_a_merge_can_be_undone(db_driver, clear_database):
    m = declare()
    a = await person(m, "John Smith", born=1800)
    b = await person(m, "Jon Smyth", died=1870)
    of_b = await make(m.Mention, "Of B", of=ref(b), others=[ref(b)])
    result = await m.Person.merge(absorb=b.id, into=a.id)

    undone = await m.Person.unmerge(result.merge.id)

    assert undone.merge.state == "undone"
    assert (undone.restored, undone.heads, undone.unmatched) == (2, 1, [])
    assert undone.fields_restored
    assert edges_to(db_driver, a.id) == []
    assert edges_to(db_driver, b.id) == [("Mention", "of", 0), ("Mention", "others", 0)]
    assert merged_into(db_driver, b.id) is None
    survivor = await m.Person.get(a.id)
    assert (survivor.died, survivor.aliases) == (None, [])
    assert (await m.Person.get(b.id)).id == b.id
    assert (await m.Mention.get(of_b.id)).of.id == b.id
    assert version_of(db_driver, of_b.id) == 3


@no_type_check
async def test_an_entity_is_not_merged_into_itself_nor_one_that_is_gone(
    db_driver, clear_database
):
    m = declare()
    a = await person(m, "A")
    b = await person(m, "B")
    with pytest.raises(PanglossMergeError, match="itself"):
        await m.Person.merge(absorb=a.id, into=a.id)
    await m.Person.delete(b.id)
    with pytest.raises(PanglossMergeError, match="deleted"):
        await m.Person.merge(absorb=b.id, into=a.id)
    with pytest.raises(PanglossMergeError, match="deleted"):
        await m.Person.merge(absorb=a.id, into=b.id)


@no_type_check
async def test_nothing_was_written_by_a_merge_that_is_refused(
    db_driver, clear_database
):
    """(what the tests of a refusal look at afterwards)"""
    m = declare()
    a, b = await person(m, "A"), await person(m, "B")
    with pytest.raises(PanglossMergeError):
        await m.Person.merge(absorb=b.id, into=b.id)
    assert_untouched(db_driver, a, b)


def assert_untouched(db_driver, *entities) -> None:
    """No merge is recorded, nothing is marked, and the entities are at their first version"""
    assert count_nodes(db_driver, "PGMerge") == 0
    assert count_nodes(db_driver, "PGMergeMove") == 0
    for entity in entities:
        assert merged_into(db_driver, entity.id) is None
        assert version_of(db_driver, entity.id) == 1


# --- every kind of relation ------------------------------------------------------------------------------------------


@no_type_check
async def test_a_merge_moves_every_kind_of_relation_and_an_undo_puts_each_back(
    db_driver, clear_database
):
    m = declare()
    a = await person(m, "Survivor")
    b = await person(m, "Absorbed")
    other = await person(m, "Another")
    made = await every_kind(m, b, other)
    before = edges_to(db_driver, b.id)
    before_reverse = reverse_edges_from(db_driver, b.id)
    properties_before = run(
        db_driver,
        "MATCH (:Rated)-[e:rated]->(p:Person) RETURN p.label AS who, e.certainty AS certainty, e.pg_position AS at "
        "ORDER BY at",
    )
    # (a plain edge; a list; edge properties; a reified relation; a semantic space; both sides of a conjunction; an
    # embedded object; a field stored under two names; nested statements, one in a semantic space; an entity's own
    # relation, and another entity's)
    assert before == [
        ("Both", "first", 0),
        ("Both", "second", 0),
        ("Group", "members", 1),
        ("Identification", "target", 0),
        ("Mention", "of", 0),
        ("Mention", "others", 1),
        ("Negative", "contents", 0),
        ("Order", "concerns", 0),
        ("Order", "concerns", 0),
        ("Order", "given_by", 0),
        ("Order", "given_by", 0),
        ("Person", "knows", 0),
        ("Rated", "rated", 1),
        ("Residence", "host", 0),
        ("Statement", "concerns", 1),
    ]

    result = await m.Person.merge(absorb=b.id, into=a.id)

    assert edges_to(db_driver, b.id) == []
    assert reverse_edges_from(db_driver, b.id) == []
    assert edges_to(db_driver, a.id) == before
    assert reverse_edges_from(db_driver, a.id) == before_reverse
    assert result.merge.moved == len(before)
    # (the mention, the rating, the wrapped document, the order, the factoid, the group, and the other person)
    assert result.merge.heads == 7
    assert (result.collapsed, result.both, result.kept) == ([], [], 0)
    # the properties of an edge, and its place in its list, went with it
    assert run(
        db_driver,
        "MATCH (:Rated)-[e:rated]->(p:Person) RETURN p.label AS who, e.certainty AS certainty, e.pg_position AS at "
        "ORDER BY at",
    ) == [
        {**row, "who": "Survivor" if row["who"] == "Absorbed" else row["who"]}
        for row in properties_before
    ]
    reverse = run(
        db_driver,
        "MATCH (p:Person {id: $id})-[e:rated_reverse]->(:Rated) RETURN e.certainty AS certainty, e.reverse AS reverse, "
        "e.pg_position AS at",
        id=str(a.id),
    )
    assert reverse == [{"certainty": 7, "reverse": True, "at": None}]
    # the survivor's page has all of it, and every document reads as it should
    survivor = await m.Person.get(a.id)
    assert {i.id for i in survivor.of_reverse} == {made["mention"].id}
    assert {i.id for i in survivor.rated_reverse} == {made["rated"].id}
    assert {i.id for i in survivor.identified_reverse} == {made["wrapped"].id}
    assert {i.id for i in survivor.members_reverse} == {made["group"].id}
    assert {i.id for i in survivor.knows_reverse} == {other.id}
    wrapped = await m.Wrapped.get(made["wrapped"].id)
    assert wrapped.identified[0].target[0].id == a.id
    assert wrapped.denied[0].contents[0].id == a.id
    assert (wrapped.paired[0].first.id, wrapped.paired[0].second.id) == (a.id, a.id)
    assert wrapped.stayed.host.id == a.id
    factoid = await m.Factoid.get(made["factoid"].id)
    assert [p.id for p in factoid.statements[0].concerns] == [other.id, a.id]
    assert factoid.statements[1].contents[0].given_by.id == a.id
    # every move is recorded, each with the node that holds the node it was from (for one below a head)
    moves = moves_of(db_driver, result.merge.id)
    assert len(moves) == len(before)
    below = [
        move for move in moves if move["all"]["pg_head"] != move["all"]["pg_source"]
    ]
    assert {move["source"] for move in below} == {
        "Both",
        "Identification",
        "Negative",
        "Order",
        "Residence",
        "Statement",
    }
    assert all(move["holder"] for move in below)
    assert not any(move["holder"] for move in moves if move not in below)
    assert not any(move["dropped"] or move["late"] for move in moves)

    undone = await m.Person.unmerge(result.merge.id)

    assert (undone.restored, undone.unmatched) == (len(before), [])
    assert edges_to(db_driver, a.id) == []
    assert reverse_edges_from(db_driver, a.id) == []
    assert edges_to(db_driver, b.id) == before
    assert reverse_edges_from(db_driver, b.id) == before_reverse
    assert (
        run(
            db_driver,
            "MATCH (:Rated)-[e:rated]->(p:Person) RETURN p.label AS who, e.certainty AS certainty, e.pg_position AS at "
            "ORDER BY at",
        )
        == properties_before
    )
    absorbed = await m.Person.get(b.id)
    assert absorbed.meta.merged_into is None
    assert {i.id for i in absorbed.of_reverse} == {made["mention"].id}
    assert (await m.Wrapped.get(made["wrapped"].id)).stayed.host.id == b.id


@no_type_check
async def test_a_relation_marked_keep_on_merge_stays_on_the_absorbed_entity(
    db_driver, clear_database
):
    m = declare()
    a, b = await person(m, "John"), await person(m, "Jon")
    same = await make(
        m.SameAs, "John is Jon", entities=[ref(a), ref(b)], argument="the same father"
    )

    result = await m.Person.merge(absorb=b.id, into=a.id)

    assert result.kept == 1
    assert (result.merge.moved, result.merge.heads, result.collapsed) == (0, 0, [])
    assert edges_to(db_driver, b.id) == [("SameAs", "entities", 1)]
    # the statement still names both, the second as an entity that was merged into the first
    read = await m.SameAs.get(same.id)
    assert [(e.id, e.merged_into) for e in read.entities] == [
        (a.id, None),
        (b.id, a.id),
    ]
    assert version_of(db_driver, same.id) == 1
    # and it can be saved again as it was read: the absorbed entity is not made the survivor (it would say that A is A)
    await m.SameAs.Update(
        id=same.id, label="John is Jon", entities=[ref(a), ref(b)], argument="edited"
    ).save()
    assert [e.id for e in (await m.SameAs.get(same.id)).entities] == [a.id, b.id]
    assert edges_to(db_driver, b.id) == [("SameAs", "entities", 1)]
    # an undo has nothing to put back, and leaves the statement alone
    undone = await m.Person.unmerge(result.merge.id)
    assert (undone.restored, undone.unmatched) == (0, [])
    assert [e.merged_into for e in (await m.SameAs.get(same.id)).entities] == [
        None,
        None,
    ]


@no_type_check
async def test_a_list_that_named_both_names_the_survivor_once_and_is_listed(
    db_driver, clear_database
):
    m = declare()
    a, b, c = await person(m, "A"), await person(m, "B"), await person(m, "C")
    rated = await make(
        m.Rated,
        "Rated three",
        rated=[
            {**ref(c), "edge_properties": {"certainty": 1}},
            {**ref(b), "edge_properties": {"certainty": 2}},
            {**ref(a), "edge_properties": {"certainty": 3}},
        ],
    )

    result = await m.Person.merge(absorb=b.id, into=a.id)

    assert [(h.id, h.type, h.label) for h in result.collapsed] == [
        (rated.id, "Rated", "Rated three")
    ]
    assert (result.merge.moved, result.merge.dropped, result.merge.heads) == (0, 1, 1)
    # the survivor's own edge is the one kept
    assert [
        (p.id, p.edge_properties.certainty) for p in (await m.Rated.get(rated.id)).rated
    ] == [
        (c.id, 1),
        (a.id, 3),
    ]
    assert version_of(db_driver, rated.id) == 2
    assert [move["dropped"] for move in moves_of(db_driver, result.merge.id)] == [True]

    await m.Person.unmerge(result.merge.id)

    # the dropped reference is back in its place, with its own properties
    assert [
        (p.id, p.edge_properties.certainty) for p in (await m.Rated.get(rated.id)).rated
    ] == [
        (c.id, 1),
        (b.id, 2),
        (a.id, 3),
    ]
    assert reverse_edges_from(db_driver, b.id) == [("Rated", "rated_reverse")]


@no_type_check
async def test_a_document_that_named_the_two_in_different_fields_is_moved_and_listed(
    db_driver, clear_database
):
    m = declare()
    a, b = await person(m, "A"), await person(m, "B")
    marriage = await make(m.Marriage, "A marries B", husband=ref(a), wife=ref(b))
    apart = await make(m.Mention, "Only B", of=ref(b))

    result = await m.Person.merge(absorb=b.id, into=a.id)

    assert [h.id for h in result.both] == [marriage.id]
    assert result.collapsed == []
    read = await m.Marriage.get(marriage.id)
    assert (read.husband.id, read.wife.id) == (a.id, a.id)
    assert (await m.Mention.get(apart.id)).of.id == a.id


@no_type_check
async def test_a_merge_that_would_leave_a_document_invalid_is_refused_naming_it(
    db_driver, clear_database
):
    m = declare()
    a, b, c = await person(m, "A"), await person(m, "B"), await person(m, "C")
    two = await make(m.Witnessed, "Two witnesses", witnesses=[ref(a), ref(b)])
    await make(m.Witnessed, "Three witnesses", witnesses=[ref(a), ref(b), ref(c)])
    await make(m.Mention, "Of B", of=ref(b))

    with pytest.raises(PanglossMergeError, match="Two witnesses") as refused:
        await m.Person.merge(absorb=b.id, into=a.id)

    assert str(two.id) in str(refused.value)
    assert "Three witnesses" not in str(refused.value)
    # nothing moved, though the check is made on the documents as the merge left them
    assert_untouched(db_driver, a, b)
    assert version_of(db_driver, two.id) == 1
    assert len(edges_to(db_driver, b.id)) == 3
    assert [w.id for w in (await m.Witnessed.get(two.id)).witnesses] == [a.id, b.id]


@no_type_check
async def test_the_survivor_never_refers_to_itself_and_the_absorbed_entity_is_left_as_it_was(
    db_driver, clear_database
):
    m = declare()
    c = await person(m, "C")
    a = await person(m, "A")
    b = await person(m, "B", knows=[ref(a), ref(c)])
    await m.Person.Update(id=a.id, label="A", knows=[ref(b), ref(c)]).save()

    result = await m.Person.merge(absorb=b.id, into=a.id)

    # the survivor knows neither itself nor the one it absorbed (C once, though both knew C)
    assert [p.id for p in (await m.Person.get(a.id)).knows] == [c.id]
    # the absorbed entity's own relations are as they were, and are not counted as moved
    assert [p.id for p in (await m.Person.get(b.id, follow_merge=False)).knows] == [
        a.id,
        c.id,
    ]
    assert (result.merge.moved, result.merge.heads) == (0, 0)
    # C is known by the survivor, and not listed as known by the entity that is merged
    assert [p.id for p in (await m.Person.get(c.id)).knows_reverse] == [a.id]

    await m.Person.unmerge(result.merge.id)
    assert [p.id for p in (await m.Person.get(a.id)).knows] == [b.id, c.id]
    assert {p.id for p in (await m.Person.get(c.id)).knows_reverse} == {a.id, b.id}


@no_type_check
async def test_the_urls_of_the_absorbed_entity_become_the_survivors(
    db_driver, clear_database
):
    m = declare()
    a = await m.Person.Create(
        label="A", knows=[], urls=["https://example.org/a"]
    ).save()
    b = await m.Person.Create(
        label="B", knows=[], urls=["https://example.org/b", "https://example.org/b2"]
    ).save()

    result = await m.Person.merge(absorb=b.id, into=a.id)

    assert (await m.Person.get(AnyHttpUrl("https://example.org/b"))).id == a.id
    assert sorted(str(u) for u in (await m.Person.get(a.id)).urls) == [
        "https://example.org/a",
        "https://example.org/b",
        "https://example.org/b2",
    ]
    assert (await m.Person.get(b.id, follow_merge=False)).urls == []

    await m.Person.unmerge(result.merge.id)

    assert (await m.Person.get(AnyHttpUrl("https://example.org/b2"))).id == b.id
    assert [str(u) for u in (await m.Person.get(a.id)).urls] == [
        "https://example.org/a"
    ]
    assert count_nodes(db_driver, "PGUrl") == 3


@no_type_check
async def test_a_merge_decided_on_versions_that_have_changed_is_refused(
    db_driver, clear_database
):
    m = declare()
    a, b = await person(m, "A"), await person(m, "B")
    await m.Person.Update(id=b.id, label="B, edited", knows=[]).save()

    with pytest.raises(PanglossVersionConflictError) as stale:
        await m.Person.merge(absorb=b.id, into=a.id, version_into=1, version_absorb=1)
    assert stale.value.current_version == 2
    with pytest.raises(PanglossVersionConflictError):
        await m.Person.merge(absorb=a.id, into=b.id, version_into=1, version_absorb=1)
    assert count_nodes(db_driver, "PGMerge") == 0

    result = await m.Person.merge(
        absorb=b.id, into=a.id, version_into=1, version_absorb=2
    )
    assert result.merge.state == "done"


@no_type_check
async def test_an_entity_that_is_merged_is_not_merged_again(db_driver, clear_database):
    m = declare()
    a, b, c = await person(m, "A"), await person(m, "B"), await person(m, "C")
    await m.Person.merge(absorb=b.id, into=a.id)

    with pytest.raises(PanglossMergeError, match=f"merged into {a.id}"):
        await m.Person.merge(absorb=b.id, into=c.id)
    with pytest.raises(PanglossMergeError, match=f"merged into {a.id}"):
        await m.Person.merge(absorb=c.id, into=b.id)
    with pytest.raises(PanglossMergeError, match=f"merged into {a.id}"):
        await m.Person.merge(absorb=b.id, into=a.id)
    assert count_nodes(db_driver, "PGMerge") == 1
    assert merged_into(db_driver, c.id) is None


@no_type_check
async def test_a_merge_is_of_entities_of_the_class_it_is_asked_of(
    db_driver, clear_database
):
    m = declare()
    a = await person(m, "A")
    group = await make(m.Group, "G")
    mention = await make(m.Mention, "Of A", of=ref(a))
    with pytest.raises(PanglossNotFoundError):
        await m.Person.merge(absorb=group.id, into=a.id)
    with pytest.raises(PanglossNotFoundError):
        await m.Person.merge(absorb=mention.id, into=a.id)
    with pytest.raises(PanglossNotFoundError):
        await m.Group.merge(absorb=group.id, into=a.id)


@no_type_check
async def test_documents_that_are_deleted_are_moved_too(db_driver, clear_database):
    m = declare()
    a, b = await person(m, "A"), await person(m, "B")
    gone = await make(m.Mention, "Deleted", of=ref(b))
    await m.Mention.delete(gone.id)

    result = await m.Person.merge(absorb=b.id, into=a.id)

    assert result.merge.heads == 1
    await m.Mention.undelete(gone.id)
    assert (await m.Mention.get(gone.id)).of.id == a.id


# --- when the classes differ ------------------------------------------------------------------------------------------


@no_type_check
async def test_the_survivor_takes_the_narrower_class_and_keeps_its_id(
    db_driver, clear_database
):
    m = declare()
    a = await person(m, "A person", born=1800)
    b = await make(m.Poet, "A poet", works=["Odes"])
    of_a = await make(m.Mention, "Of A", of=ref(a))
    poem = await make(m.Poem, "A poem", by=ref(b, "Poet"))
    events = []
    hooks.after_write.append(events.append)
    try:
        result = await m.Person.merge(absorb=b.id, into=a.id)
    finally:
        hooks.after_write.remove(events.append)

    assert (result.merge.survivor_type, result.merge.survivor_type_before) == (
        "Poet",
        "Person",
    )
    survivor = await m.Person.get(a.id)
    assert (survivor.type, survivor.id, survivor.born, survivor.works) == (
        "Poet",
        a.id,
        1800,
        ["Odes"],
    )
    # what took a person takes the poet it has become, and what took only a poet has it
    assert (await m.Mention.get(of_a.id)).of.type == "Poet"
    assert (await m.Poem.get(poem.id)).by.id == a.id
    assert [
        e.changed_class_from for e in events if e.op == "update" and e.id == a.id
    ] == [m.Person]

    undone = await m.Person.unmerge(result.merge.id)

    assert undone.fields_restored
    restored = await m.Person.get(a.id)
    assert (restored.type, restored.born) == ("Person", 1800)
    assert not hasattr(restored, "works")
    assert (await m.Poem.get(poem.id)).by.id == b.id
    assert (await m.Poet.get(b.id)).works == ["Odes"]


@no_type_check
async def test_the_wider_class_may_be_chosen_unless_a_relation_cannot_hold_it(
    db_driver, clear_database
):
    m = declare()
    a = await person(m, "A person")
    b = await make(m.Poet, "A poet", works=["Odes"])
    poem = await make(m.Poem, "A poem", by=ref(b, "Poet"))

    with pytest.raises(PanglossMergeError, match="Poem") as refused:
        await m.Person.merge(absorb=b.id, into=a.id, as_class=m.Person)
    assert str(poem.id) in str(refused.value)
    assert_untouched(db_driver, a, b)
    assert (await m.Poem.get(poem.id)).by.id == b.id

    # the other way about, it is the survivor's own references that are looked at
    with pytest.raises(PanglossWriteError, match="Poem"):
        await m.Person.merge(absorb=a.id, into=b.id, as_class=m.Person)
    assert_untouched(db_driver, a, b)

    await m.Poem.delete(poem.id)
    await make(m.Mention, "Of the poet", of=ref(b))
    result = await m.Person.merge(absorb=b.id, into=a.id, as_class=m.Person)
    survivor = await m.Person.get(a.id)
    assert (survivor.type, result.merge.survivor_type) == ("Person", "Person")
    assert not hasattr(survivor, "works")
    # (what the wider class does not hold is still on the absorbed entity)
    assert (await m.Poet.get(b.id, follow_merge=False)).works == ["Odes"]


@no_type_check
async def test_siblings_are_merged_as_a_class_that_is_both_and_strangers_are_not(
    db_driver, clear_database
):
    m = declare()
    poet = await make(m.Poet, "A poet", works=["Odes"])
    soldier = await make(m.Soldier, "A soldier", rank="captain")
    group = await make(m.Group, "A group")
    poem = await make(m.Poem, "A poem", by=ref(poet, "Poet"))

    with pytest.raises(PanglossMergeError, match="neither is a kind of the other"):
        await m.Entity.merge(absorb=group.id, into=poet.id)
    with pytest.raises(PanglossMergeError, match="cannot be a Person"):
        await m.Person.merge(absorb=soldier.id, into=poet.id, as_class=m.Person)
    assert_untouched(db_driver, poet, soldier, group)

    result = await m.Person.merge(absorb=poet.id, into=soldier.id)

    assert result.merge.survivor_type == "PoetSoldier"
    survivor = await m.Person.get(soldier.id)
    assert (survivor.type, survivor.rank, survivor.works) == (
        "PoetSoldier",
        "captain",
        ["Odes"],
    )
    assert (await m.Poem.get(poem.id)).by.id == soldier.id


# --- large merges -----------------------------------------------------------------------------------------------------


@pytest.fixture
def limit_of_three(monkeypatch):
    from pangloss_cypher import merge

    monkeypatch.setattr(merge, "merge_limit", lambda: 3)


@no_type_check
async def test_a_merge_over_the_limit_is_refused_unless_asked_for_as_large(
    db_driver, clear_database, limit_of_three
):
    m = declare()
    a, b = await person(m, "A"), await person(m, "B")
    mentions = [await make(m.Mention, f"Mention {i}", of=ref(b)) for i in range(8)]

    with pytest.raises(PanglossMergeTooLargeError) as refused:
        await m.Person.merge(absorb=b.id, into=a.id)
    assert (refused.value.heads, refused.value.limit) == (8, 3)
    assert_untouched(db_driver, a, b)

    for mention in mentions[3:]:
        await m.Mention.delete(mention.id)
    preview = await m.Person.merge_preview(absorb=b.id, into=a.id)
    assert (preview.heads, preview.large, preview.possible) == (8, True, True)

    result = await m.Person.merge(absorb=b.id, into=a.id, allow_large=True)

    assert (result.merge.state, result.merge.heads, result.merge.moved) == (
        "done",
        8,
        8,
    )
    assert edges_to(db_driver, b.id) == []
    assert len(moves_of(db_driver, result.merge.id)) == 8
    assert all(version_of(db_driver, mention.id) == 2 for mention in mentions)

    undone = await m.Person.unmerge(result.merge.id)
    # (those of deleted documents are not put back)
    assert (undone.restored, len(undone.unmatched)) == (3, 5)
    assert {u["reason"] for u in undone.unmatched} == {"deleted"}


@no_type_check
async def test_a_large_merge_that_stops_part_of_the_way_is_gone_on_with(
    db_driver, clear_database, limit_of_three, monkeypatch
):
    from pangloss_cypher import merge

    m = declare()
    a, b = await person(m, "A"), await person(m, "B")
    mentions = [await make(m.Mention, f"Mention {i}", of=ref(b)) for i in range(8)]
    batch = merge._batch_transaction
    calls = []

    async def failing(*args, **kwargs):
        calls.append(args)
        if len(calls) == 2:
            raise PanglossWriteError("the database went away")
        return await batch(*args, **kwargs)

    monkeypatch.setattr(merge, "_batch_transaction", failing)
    with pytest.raises(PanglossWriteError, match="went away"):
        await m.Person.merge(absorb=b.id, into=a.id, allow_large=True)

    # half merged: the absorbed entity is marked, and the first batch is on the survivor
    [running] = await m.Person.merges(b.id)
    assert (running.state, running.heads) == ("running", 3)
    assert merged_into(db_driver, b.id) == str(a.id)
    assert (len(edges_to(db_driver, a.id)), len(edges_to(db_driver, b.id))) == (3, 5)
    # a write that names the absorbed entity meanwhile is already resolved
    during = await make(m.Mention, "During", of=ref(b))
    assert (await m.Mention.get(during.id)).of.id == a.id

    monkeypatch.setattr(merge, "_batch_transaction", batch)
    result = await m.Person.merge(absorb=b.id, into=a.id, allow_large=True)

    assert (result.merge.id, result.merge.state, result.merge.heads) == (
        running.id,
        "done",
        8,
    )
    assert edges_to(db_driver, b.id) == []
    assert len(edges_to(db_driver, a.id)) == 9
    assert count_nodes(db_driver, "PGMerge") == 1
    assert all(version_of(db_driver, mention.id) == 2 for mention in mentions)


@no_type_check
async def test_a_large_merge_that_stopped_can_be_taken_back(
    db_driver, clear_database, limit_of_three, monkeypatch
):
    from pangloss_cypher import merge

    m = declare()
    a, b = await person(m, "A"), await person(m, "B")
    for i in range(7):
        await make(m.Mention, f"Mention {i}", of=ref(b))
    batch = merge._batch_transaction
    calls = []

    async def failing(*args, **kwargs):
        calls.append(args)
        if len(calls) == 3:
            raise PanglossWriteError("stopped")
        return await batch(*args, **kwargs)

    monkeypatch.setattr(merge, "_batch_transaction", failing)
    with pytest.raises(PanglossWriteError):
        await m.Person.merge(absorb=b.id, into=a.id, allow_large=True)
    [running] = await m.Person.merges(a.id)
    assert running.state == "running"

    undone = await m.Person.unmerge(running.id)

    assert (undone.restored, undone.unmatched, undone.merge.state) == (6, [], "undone")
    assert edges_to(db_driver, a.id) == []
    assert len(edges_to(db_driver, b.id)) == 7
    assert merged_into(db_driver, b.id) is None


@no_type_check
async def test_a_large_merge_is_refused_before_any_batch_if_it_would_leave_a_document_invalid(
    db_driver, clear_database, limit_of_three
):
    m = declare()
    a, b = await person(m, "A"), await person(m, "B")
    for i in range(6):
        await make(m.Mention, f"Mention {i}", of=ref(b))
    two = await make(m.Witnessed, "Two witnesses", witnesses=[ref(a), ref(b)])

    with pytest.raises(PanglossMergeError, match="Two witnesses"):
        await m.Person.merge(absorb=b.id, into=a.id, allow_large=True)

    assert_untouched(db_driver, a, b)
    assert version_of(db_driver, two.id) == 1
    assert len(edges_to(db_driver, b.id)) == 7


# --- what is recorded, and what is told ----------------------------------------------------------------------------------


@no_type_check
async def test_a_merge_tells_the_listeners_of_each_write(db_driver, clear_database):
    m = declare()
    a, b = await person(m, "A"), await person(m, "B")
    mention = await make(m.Mention, "Of B", of=ref(b))
    events = []
    pending = []
    hooks.after_write.append(events.append)
    hooks.pending_work.append(lambda model: ["test-work"])
    try:
        result = await m.Person.merge(absorb=b.id, into=a.id)
        merged = [(e.op, e.model.__name__, e.id, e.version) for e in events]
        pending = sorted(
            r["head"]
            for r in run(
                db_driver,
                "MATCH (p:PGPending {kind: 'test-work'}) RETURN p.head_id AS head",
            )
        )
        notes = {e.merge for e in events if e.merge is not None}
        events.clear()
        await m.Person.unmerge(result.merge.id)
        unmerged = [(e.op, e.model.__name__, e.id, e.version) for e in events]
        undone_notes = {e.merge.undone for e in events if e.merge is not None}
    finally:
        hooks.after_write.remove(events.append)
        hooks.pending_work.pop()

    # the survivor's update (with what it holds now), the absorbed entity's merge, and an update of each head
    assert merged == [
        ("update", "Person", a.id, 2),
        ("merge", "Person", b.id, 1),
        ("update", "Mention", mention.id, 2),
    ]
    assert [(n.id, n.survivor, n.absorbed, n.undone) for n in notes] == [
        (result.merge.id, a.id, b.id, False)
    ]
    # both entities and the head are left for the installed apps to work on (derived facts are worked out again)
    assert pending == sorted(str(i) for i in (a.id, b.id, mention.id))
    assert unmerged == [
        ("update", "Person", a.id, 3),
        ("unmerge", "Person", b.id, 1),
        ("update", "Mention", mention.id, 3),
    ]
    assert undone_notes == {True}


@no_type_check
async def test_an_installed_app_can_refuse_a_merge(db_driver, clear_database):
    m = declare()
    a, b = await person(m, "A"), await person(m, "Protected")
    asked = []

    async def refuse(request):
        asked.append((request.survivor.id, request.absorbed.id, request.result_model))
        if request.absorbed.label == "Protected":
            raise PanglossMergeError("Protected is not to be merged away")

    hooks.before_merge.append(refuse)
    try:
        with pytest.raises(PanglossMergeError, match="not to be merged away"):
            await m.Person.merge(absorb=b.id, into=a.id)
        preview = await m.Person.merge_preview(absorb=b.id, into=a.id)
        merged = await m.Person.merge(absorb=a.id, into=b.id)
    finally:
        hooks.before_merge.remove(refuse)

    assert preview.refused == ["Protected is not to be merged away"]
    assert asked[0] == (a.id, b.id, m.Person)
    assert merged.merge.survivor == b.id


@no_type_check
async def test_the_merges_of_an_entity_are_listed_latest_first(
    db_driver, clear_database
):
    m = declare()
    a, b, c = await person(m, "A"), await person(m, "B"), await person(m, "C")
    first = await m.Person.merge(absorb=b.id, into=a.id)
    await m.Person.unmerge(first.merge.id)
    second = await m.Person.merge(absorb=b.id, into=a.id)
    third = await m.Person.merge(absorb=c.id, into=a.id)

    of_a = await m.Person.merges(a.id)
    assert [(r.id, r.state) for r in of_a] == [
        (third.merge.id, "done"),
        (second.merge.id, "done"),
        (first.merge.id, "undone"),
    ]
    assert of_a[0].by and of_a[0].when is not None
    assert (of_a[2].undone_by, of_a[0].absorbed_label, of_a[0].absorbed_type) == (
        of_a[0].by,
        "C",
        "Person",
    )
    assert [r.id for r in await m.Person.merges(c.id)] == [third.merge.id]


# --- the fields of the survivor -------------------------------------------------------------------------------------------


@no_type_check
async def test_the_survivor_has_the_values_given(db_driver, clear_database):
    m = declare()
    c = await person(m, "C")
    a = await m.Person.Create(
        label="A", born=1800, knows=[], urls=["https://example.org/a"]
    ).save()
    b = await m.Person.Create(
        label="B",
        born=1801,
        aliases=["Bee"],
        knows=[ref(c)],
        urls=["https://example.org/b"],
    ).save()

    result = await m.Person.merge(
        absorb=b.id,
        into=a.id,
        # (a reference to either of the two is left out; the URLs are those of both whatever is given)
        values={
            "label": "A or B",
            "born": 1801,
            "aliases": ["Bee"],
            "knows": [ref(a), ref(b), ref(c)],
            "urls": [],
        },
    )

    survivor = await m.Person.get(a.id)
    assert (survivor.label, survivor.born, survivor.aliases) == (
        "A or B",
        1801,
        ["Bee"],
    )
    assert [p.id for p in survivor.knows] == [c.id]
    assert len(survivor.urls) == 2
    assert result.merge.state == "done"

    with pytest.raises(PanglossMergeError, match="not those of a Person"):
        await m.Person.merge(
            absorb=c.id,
            into=a.id,
            values={"label": "A", "born": "not a year", "knows": []},
        )
    assert merged_into(db_driver, c.id) is None


# --- the preview ----------------------------------------------------------------------------------------------------------


@no_type_check
async def test_a_preview_says_what_a_merge_would_do_and_writes_nothing(
    db_driver, clear_database
):
    m = declare()
    a, b, c = (
        await person(m, "A", born=1800),
        await person(m, "B", died=1870),
        await person(m, "C"),
    )
    await make(m.Mention, "Of A", of=ref(a))
    await make(m.Mention, "Of B", of=ref(b))
    await make(m.Group, "Has B", members=[ref(b)])
    listed = await make(
        m.Rated,
        "Rates both",
        rated=[
            {**ref(a), "edge_properties": {"certainty": 1}},
            {**ref(b), "edge_properties": {"certainty": 2}},
        ],
    )
    marriage = await make(m.Marriage, "Married", husband=ref(a), wife=ref(b))
    await make(m.SameAs, "Same", entities=[ref(a), ref(b)])
    nodes = run(db_driver, "MATCH (n) RETURN count(n) AS nodes")[0]["nodes"]
    edges = run(db_driver, "MATCH ()-[e]->() RETURN count(e) AS edges")[0]["edges"]

    preview = await m.Person.merge_preview(absorb=b.id, into=a.id)

    assert preview.possible and not preview.large
    assert (preview.survivor, preview.absorbed, preview.survivor_type) == (
        a.id,
        b.id,
        "Person",
    )
    assert (preview.heads, preview.kept) == (4, 1)
    assert preview.refer_to_absorbed == {
        "Group": 1,
        "Marriage": 1,
        "Mention": 1,
        "Rated": 1,
        "SameAs": 1,
    }
    assert preview.refer_to_survivor == {
        "Marriage": 1,
        "Mention": 1,
        "Rated": 1,
        "SameAs": 1,
    }
    assert [h.id for h in preview.collapsed] == [listed.id]
    assert [h.id for h in preview.both] == [marriage.id]
    assert (
        preview.values["born"],
        preview.values["died"],
        preview.values["aliases"],
    ) == (1800, 1870, ["B"])
    # nothing was written
    assert run(db_driver, "MATCH (n) RETURN count(n) AS nodes")[0]["nodes"] == nodes
    assert (
        run(db_driver, "MATCH ()-[e]->() RETURN count(e) AS edges")[0]["edges"] == edges
    )
    assert_untouched(db_driver, a, b)
    assert version_of(db_driver, listed.id) == 1

    # and what it says is why not, when the merge cannot be made
    await make(m.Witnessed, "Two witnesses", witnesses=[ref(a), ref(b)])
    refused = await m.Person.merge_preview(absorb=b.id, into=a.id)
    assert not refused.possible and "Two witnesses" in refused.refused[0]
    assert (await m.Person.merge_preview(absorb=c.id, into=c.id)).refused == [
        "An entity cannot be merged into itself"
    ]
    assert_untouched(db_driver, a, b, c)


# --- nothing half done -----------------------------------------------------------------------------------------------------


@no_type_check
async def test_a_merge_that_fails_part_of_the_way_leaves_nothing(
    db_driver, clear_database, monkeypatch
):
    from pangloss_cypher import merge

    m = declare()
    a, b = await person(m, "A", born=1800), await person(m, "B", died=1870)
    made = await every_kind(m, b, a)
    before = edges_to(db_driver, b.id)
    versions = {key: version_of(db_driver, item.id) for key, item in made.items()}

    async def fail(*args, **kwargs):
        raise PanglossWriteError("the last step failed")

    # (after the absorbed entity is marked, the survivor written, the moves recorded and the edges moved)
    monkeypatch.setattr(merge, "_check_nothing_left", fail)
    with pytest.raises(PanglossWriteError, match="last step"):
        await m.Person.merge(absorb=b.id, into=a.id)

    assert count_nodes(db_driver, "PGMerge") == 0
    assert count_nodes(db_driver, "PGMergeMove") == 0
    assert merged_into(db_driver, b.id) is None
    assert edges_to(db_driver, b.id) == before
    assert (await m.Person.get(a.id)).died is None
    assert {
        key: version_of(db_driver, item.id) for key, item in made.items()
    } == versions


@no_type_check
async def test_a_reference_the_merge_does_not_know_how_to_move_stops_it(
    db_driver, clear_database
):
    m = declare()
    a, b = await person(m, "A"), await person(m, "B")
    mention = await make(m.Mention, "Of B", of=ref(b))
    # (an edge that is not a field of the class it is from: written around the models)
    run(
        db_driver,
        "MATCH (d:Mention {id: $d}), (b:Person {id: $b}) CREATE (d)-[:made_up]->(b)",
        d=str(mention.id),
        b=str(b.id),
    )

    with pytest.raises(PanglossMergeError, match="made_up"):
        await m.Person.merge(absorb=b.id, into=a.id)

    assert_untouched(db_driver, a, b)
    assert (await m.Mention.get(mention.id)).of.id == b.id
    assert not (await m.Person.merge_preview(absorb=b.id, into=a.id)).possible
