"""Reading where entities have been merged (implementation_docs/entity-identity.md, "Reading a merged entity"): the id of an absorbed
entity gives its survivor; lists, searches and what is offered while typing leave the absorbed entity out, and find the
survivor by its label"""

from typing import no_type_check

import pytest
from pangloss_core import storage_of
from pangloss_models import PanglossEntityInUseError, Rel
from pangloss_models.autocomplete import search_everything
from pydantic import AnyHttpUrl

from .merge_support import declare, make, person, ref

pytestmark = pytest.mark.asyncio(loop_scope="session")


def labels(found):
    return [item.label for item in found.results]


@no_type_check
async def test_the_id_of_an_absorbed_entity_gives_its_survivor(
    db_driver, clear_database
):
    m = declare()
    a = await person(m, "John Smith", born=1800)
    b = await m.Person.Create(
        label="Jon Smyth", knows=[], urls=["https://example.org/smyth"]
    ).save()
    mention = await make(m.Mention, "Of B", of=ref(b))
    await m.Person.merge(absorb=b.id, into=a.id)

    by_id = await m.Person.get(b.id)
    assert (by_id.id, by_id.label, by_id.meta.merged_from, by_id.meta.merged_into) == (
        a.id,
        "John Smith",
        [b.id],
        None,
    )
    assert [i.id for i in by_id.of_reverse] == [mention.id]
    assert (await m.Person.get(AnyHttpUrl("https://example.org/smyth"))).id == a.id
    edit = await m.Person.get_for_edit(b.id)
    assert (edit.id, edit.meta.merged_from) == (a.id, [b.id])
    # the survivor read by its own id says nothing of it
    assert (await m.Person.get(a.id)).meta.merged_from is None
    # and the absorbed entity can still be read as itself, as it was
    itself = await m.Person.get(b.id, follow_merge=False)
    assert (
        itself.id,
        itself.label,
        itself.meta.merged_into,
        itself.meta.merged_from,
    ) == (
        b.id,
        "Jon Smyth",
        a.id,
        None,
    )
    assert itself.of_reverse == []
    assert (await m.Person.get_for_edit(b.id, follow_merge=False)).label == "Jon Smyth"


@no_type_check
async def test_a_chain_of_merges_is_followed_to_its_end(db_driver, clear_database):
    m = declare()
    a, b, x = await person(m, "A"), await person(m, "B"), await person(m, "X")
    await m.Person.merge(absorb=x.id, into=b.id)
    await m.Person.merge(absorb=b.id, into=a.id)

    found = await m.Person.get(x.id)
    assert (found.id, found.meta.merged_from) == (a.id, [x.id, b.id])
    assert (await m.Person.get(b.id)).meta.merged_from == [b.id]
    assert (await m.Person.get(x.id, follow_merge=False)).meta.merged_into == b.id
    # both labels went on to the survivor as other names
    assert sorted(found.aliases) == ["B", "X"]


@no_type_check
async def test_a_read_by_a_class_the_survivor_is_not_gives_the_survivor_as_it_is(
    db_driver, clear_database
):
    m = declare()
    a = await person(m, "A person")
    b = await make(m.Poet, "A poet", works=["Odes"])
    await m.Person.merge(absorb=b.id, into=a.id, as_class=m.Person)

    found = await m.Poet.get(b.id)
    assert (found.id, found.type, found.meta.merged_from) == (a.id, "Person", [b.id])
    assert type(found) is m.Person.HeadView
    # an id that was never of the class asked for is still nothing
    assert await m.Group.get(b.id) is None
    assert await m.Poet.get(a.id) is None


@no_type_check
async def test_lists_and_searches_leave_the_absorbed_entity_out(
    db_driver, clear_database
):
    m = declare()
    a = await person(m, "John Smith")
    b = await person(m, "Jon Smyth")
    c = await person(m, "Kate Jones", knows=[ref(b)])
    await make(m.Mention, "Of B", of=ref(b))
    before = await m.Person.list()
    assert before.count == 3

    result = await m.Person.merge(absorb=b.id, into=a.id)

    assert sorted(labels(await m.Person.list())) == ["John Smith", "Kate Jones"]
    assert (await m.Person.list()).count == 2
    assert labels(await m.Person.list(search_terms="smyth")) == []
    assert labels(await m.Person.list(search_terms="smith")) == ["John Smith"]
    assert labels(await m.Person.list(search_terms="smyth", deep_search=True)) == []
    assert sorted(labels(await m.Person.search())) == ["John Smith", "Kate Jones"]
    assert (
        labels(await m.Person.search(m.Person.Where(label={"contains": "smyth"}))) == []
    )
    assert labels(await search_everything("smyth")) == []
    assert sorted(labels(await search_everything("", types=[m.Person]))) == [
        "John Smith",
        "Kate Jones",
    ]
    # what is counted as referring to an entity is what is listed as referring to it
    used = await m.Person.list(use_counts=True)
    assert used.use_counts == {str(a.id): 2, str(c.id): 0}
    assert sorted(labels(await m.Person.list(used_only=True))) == ["John Smith"]
    # a document that names the survivor is found by a search for it, and by none for the one absorbed
    assert labels(await m.Mention.search(m.Mention.Where(of=Rel(is_=a.id)))) == ["Of B"]
    assert labels(await m.Mention.search(m.Mention.Where(of=Rel(is_=b.id)))) == []

    await m.Person.unmerge(result.merge.id)
    assert sorted(labels(await m.Person.list())) == [
        "John Smith",
        "Jon Smyth",
        "Kate Jones",
    ]
    assert labels(await m.Person.list(search_terms="smyth")) == ["Jon Smyth"]
    assert labels(await m.Mention.search(m.Mention.Where(of=Rel(is_=b.id)))) == ["Of B"]


@no_type_check
async def test_typing_the_label_of_an_absorbed_entity_offers_its_survivor(
    db_driver, clear_database
):
    m = declare()
    a = await person(m, "John Smith")
    b = await person(m, "Jon Smyth")
    x = await person(m, "Johannes Schmidt")
    other = await person(m, "Jon Snow")
    await m.Person.merge(absorb=x.id, into=b.id)
    await m.Person.merge(absorb=b.id, into=a.id)

    def offered(found):
        return [(item.id, item.label, item.merged_label) for item in found.results]

    # the spelling someone used once finds the entity it was merged into, and says by which name
    assert offered(await m.Person.autocomplete("smyth")) == [
        (a.id, "John Smith", "Jon Smyth")
    ]
    # through a chain of merges too
    assert offered(await m.Person.autocomplete("schmidt")) == [
        (a.id, "John Smith", "Johannes Schmidt")
    ]
    # its own label finds it as itself
    assert offered(await m.Person.autocomplete("smith")) == [(a.id, "John Smith", None)]
    # an entity found by its own label and by one merged into it is offered once, as itself
    assert offered(await m.Person.autocomplete("jo")) == [
        (a.id, "John Smith", None),
        (other.id, "Jon Snow", None),
    ]
    assert (await m.Person.autocomplete("jon")).count == 2
    # before anything is typed, the absorbed entities are not among what is offered
    assert sorted(labels(await m.Person.autocomplete(""))) == ["John Smith", "Jon Snow"]


@no_type_check
async def test_what_is_offered_is_the_survivor_if_it_is_of_a_type_asked_for_and_there(
    db_driver, clear_database
):
    m = declare()
    a = await person(m, "A person")
    b = await make(m.Poet, "Homer", works=["Odes"])
    group = await make(m.Group, "Homeric circle")
    await m.Person.merge(absorb=b.id, into=a.id, as_class=m.Person)

    # the survivor is a person and not a poet: a field that takes only poets is not offered it
    assert labels(await m.Poet.autocomplete("homer")) == []
    assert labels(await m.Person.autocomplete("homer")) == ["A person"]
    assert labels(await m.Entity.autocomplete("homer", types=[m.Group])) == [
        "Homeric circle"
    ]
    assert sorted(
        labels(await m.Entity.autocomplete("homer", types=[m.Group, m.Person]))
    ) == [
        "A person",
        "Homeric circle",
    ]
    # a survivor that is deleted is not offered, by any name
    await m.Person.delete(a.id)
    assert labels(await m.Person.autocomplete("homer")) == []
    assert labels(await m.Person.autocomplete("person")) == []
    assert group.id


@no_type_check
async def test_what_an_absorbed_entity_refers_to_still_counts_as_used(
    db_driver, clear_database
):
    """(so that an undo does not bring back an entity that refers to deleted ones: decision 25)"""
    m = declare()
    a = await person(m, "A")
    c = await person(m, "C")
    b = await person(m, "B", knows=[ref(c)])
    result = await m.Person.merge(
        absorb=b.id, into=a.id, values={"label": "A", "knows": []}
    )

    # C's page does not show the absorbed entity as knowing it
    assert (await m.Person.get(c.id)).knows_reverse == []
    # but C cannot be deleted while the absorbed entity names it
    with pytest.raises(PanglossEntityInUseError):
        await m.Person.delete(c.id)
    check = await storage_of().operations.check_deletable(m.Person, c.id)
    assert not check.deletable

    await m.Person.unmerge(result.merge.id)
    assert [p.id for p in (await m.Person.get(c.id)).knows_reverse] == [b.id]
