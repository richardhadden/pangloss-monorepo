"""Reading through claims of identity (`pangloss_library.clusters`; implementation_docs/entity-identity.md, step 5):
the cluster of an entity, what joins it and what does not (a claim in a semantic space, in a deleted or unpublished
document, an edge of the same name that is no claim), what a merge does to it, its bounds, and the search key
`$same_as`."""

import asyncio
import importlib
from types import SimpleNamespace
from typing import Annotated, no_type_check
from uuid import uuid4

import pytest
from annotated_types import MaxLen, MinLen
from pangloss_api import create_app
from pangloss_core import settings as core_settings
from pangloss_models import (
    Document,
    Entity,
    Match,
    PanglossSearchError,
    Rel,
    SemanticSpace,
    initialise,
)
from pangloss_models.search import check_match, search_match
from pangloss_testing.live import run
from pangloss_users import see_unpublished

from .test_merge_api import api  # noqa: F401
from .test_sdk_contract import through_the_api  # noqa: F401

pytestmark = pytest.mark.asyncio(loop_scope="session")


def models():
    # (the registry was reset, and a module is only run once: the library's models are declared again)
    import pangloss_library.models
    from pangloss_library.identity import IdentityClaim

    importlib.reload(pangloss_library.models)
    SameEntity = pangloss_library.models.SameEntity

    class Person(Entity):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    class Hypothetical[T](SemanticSpace[T]):
        pass

    # (a project's own statement of identity, a head document)
    class Alias(Document):
        entities: Annotated[list[Person], MinLen(2), MaxLen(2), IdentityClaim()]

    # (a relation of the same name as `SameEntity.target` that claims nothing)
    class Mention(Document):
        target: list[Person]

    class Factoid(Document):
        statements: list[
            SameEntity[Person]  # ty: ignore[invalid-type-form]
            | Negative[SameEntity[Person]]  # ty: ignore[invalid-type-form]
            | Hypothetical[SameEntity[Person]]  # ty: ignore[invalid-type-form]
        ]

    initialise()
    return SimpleNamespace(Person=Person, Factoid=Factoid, Alias=Alias, Mention=Mention)


def ref(id) -> dict:
    return {"type": "Person", "id": id}


def same(a, b, label="same", **more) -> dict:
    return {"type": "SameEntity", "label": label, "target": [ref(a), ref(b)], **more}


def inside(space: str, statement: dict) -> dict:
    return {"type": space, "contents": [statement]}


async def people(m, names: str) -> list:
    return [(await m.Person.Create(label=name).save()).id for name in names]


async def factoid(m, *statements, label="Factoid"):
    return await m.Factoid.Create(label=label, statements=list(statements)).save()


async def alias(m, a, b, label="Alias"):
    return await m.Alias.Create(label=label, entities=[ref(a), ref(b)]).save()


def shape(found) -> dict:
    """The members of a cluster by label: how far, and through whom (labels)"""
    labels = {m.id: m.label for m in found.members}
    return {
        m.label: (m.distance, [labels[id] for id in m.through]) for m in found.members
    }


def between(found, claims) -> list[tuple]:
    labels = {m.id: m.label for m in found.members} | {
        found.entity.id: found.entity.label
    }
    return sorted(
        (c.label, tuple(sorted(labels[id] for id in c.between)), tuple(c.spaces))
        for c in claims
    )


@no_type_check
async def test_an_entity_nothing_is_said_of_is_a_cluster_of_one(clear_database):
    from pangloss_library.clusters import NoSuchEntity, cluster

    m = models()
    [a] = await people(m, "A")
    found = await cluster(a)
    assert (found.entity.id, found.entity.label, found.entity.type) == (
        str(a),
        "A",
        "Person",
    )
    assert found.members == [] and found.size == 1
    assert not found.large and not found.truncated
    assert found.claims == [] and found.in_spaces == []
    assert found.ids() == [str(a)]
    with pytest.raises(NoSuchEntity):
        await cluster(uuid4())
    # (a document is not an entity)
    document = await alias(m, a, (await people(m, "B"))[0])
    with pytest.raises(NoSuchEntity):
        await cluster(document.id)


@no_type_check
async def test_claims_in_different_documents_join_a_cluster_whole_or_one_step(
    clear_database,
):
    from pangloss_library.clusters import cluster

    m = models()
    a, b, c, d, e = await people(m, "ABCDE")
    await factoid(m, same(a, b, "A is B", argument="The same seal"), label="Charter")
    await alias(m, b, c, "B is C")
    await factoid(m, same(c, d, "C is D"), label="Roll")
    # (E is said to be nobody)

    found = await cluster(a)
    assert shape(found) == {"B": (1, []), "C": (2, ["B"]), "D": (3, ["B", "C"])}
    assert found.size == 4 and not found.truncated and not found.large
    assert between(found, found.claims) == [
        ("A is B", ("A", "B"), ()),
        ("B is C", ("B", "C"), ()),
        ("C is D", ("C", "D"), ()),
    ]
    by_label = {claim.label: claim for claim in found.claims}
    assert by_label["A is B"].argument == "The same seal"
    assert (by_label["A is B"].head.type, by_label["A is B"].head.label) == (
        "Factoid",
        "Charter",
    )
    assert by_label["A is B"].type == "SameEntity"
    # (a head document that is itself the claim)
    assert by_label["B is C"].head.id == by_label["B is C"].id
    assert by_label["B is C"].type == "Alias"

    # from the other end, the same cluster
    assert shape(await cluster(d)) == {
        "C": (1, []),
        "B": (2, ["C"]),
        "A": (3, ["C", "B"]),
    }
    # from the middle
    assert shape(await cluster(b)) == {"A": (1, []), "C": (1, []), "D": (2, ["C"])}

    # one step: what a statement says of the entity itself, and no more (which is not "truncated": it was asked for)
    one = await cluster(a, steps="one")
    assert shape(one) == {"B": (1, [])} and one.steps == "one" and not one.truncated
    assert between(one, one.claims) == [("A is B", ("A", "B"), ())]
    assert shape(await cluster(b, steps="one")) == {"A": (1, []), "C": (1, [])}
    assert (await cluster(e)).size == 1


@no_type_check
async def test_a_cycle_of_claims_and_two_claims_of_one_pair(clear_database):
    from pangloss_library.clusters import cluster

    m = models()
    a, b, c = await people(m, "ABC")
    await factoid(m, same(a, b, "one"), same(b, a, "two"), same(b, c, "three"))
    await alias(m, c, a, "four")
    found = await cluster(a)
    assert shape(found) == {"B": (1, []), "C": (1, [])}
    assert between(found, found.claims) == [
        ("four", ("A", "C"), ()),
        ("one", ("A", "B"), ()),
        ("three", ("B", "C"), ()),
        ("two", ("A", "B"), ()),
    ]


@no_type_check
async def test_a_claim_in_a_semantic_space_joins_nothing_and_is_given_when_between_members(
    clear_database,
):
    from pangloss_library.clusters import cluster

    m = models()
    a, b, c, d = await people(m, "ABCD")
    await factoid(
        m,
        same(a, b, "A is B"),
        same(b, c, "B is C"),
        inside("Negative", same(a, c, "A is not C")),
        inside("Hypothetical", same(a, d, "A may be D")),
        inside("Negative", same(b, d, "B is not D")),
    )
    found = await cluster(a)
    # (D is only said, in a space, to be the same: it is no member)
    assert shape(found) == {"B": (1, []), "C": (2, ["B"])}
    assert between(found, found.claims) == [
        ("A is B", ("A", "B"), ()),
        ("B is C", ("B", "C"), ()),
    ]
    # (what is said in a space of two members; of a member and another, nothing)
    assert between(found, found.in_spaces) == [
        ("A is not C", ("A", "C"), ("Negative",))
    ]

    # D is in no cluster but its own
    assert (await cluster(d)).size == 1
    # with one step, C is no member, so what is said of A and C is not of the cluster
    one = await cluster(a, steps="one")
    assert shape(one) == {"B": (1, [])} and one.in_spaces == []
    # ...but of B's own step it is, as A and C both are
    assert between(
        await cluster(b, steps="one"), (await cluster(b, steps="one")).in_spaces
    ) == [("A is not C", ("A", "C"), ("Negative",))]


@no_type_check
async def test_an_edge_of_the_same_name_that_is_no_claim_joins_nothing(clear_database):
    from pangloss_library.clusters import claim_fields, cluster

    m = models()
    a, b, c = await people(m, "ABC")
    await m.Mention.Create(label="Of A and B", target=[ref(a), ref(b)]).save()
    await alias(m, a, c)
    assert claim_fields() == {"SameEntity": {"target"}, "Alias": {"entities"}}
    assert shape(await cluster(a)) == {"C": (1, [])}
    assert (await cluster(b)).size == 1


@no_type_check
async def test_a_deleted_document_joins_nothing_until_it_is_undeleted(clear_database):
    from pangloss_library.clusters import cluster

    m = models()
    a, b, c = await people(m, "ABC")
    first = await factoid(m, same(a, b, "A is B"))
    await alias(m, b, c)
    assert shape(await cluster(a)) == {"B": (1, []), "C": (2, ["B"])}
    await m.Factoid.delete(first.id)
    assert (await cluster(a)).size == 1
    assert shape(await cluster(b)) == {"C": (1, [])}
    await m.Factoid.undelete(first.id)
    assert shape(await cluster(a)) == {"B": (1, []), "C": (2, ["B"])}


@no_type_check
async def test_a_claim_changed_by_an_update_is_read_as_it_is_now(clear_database):
    from pangloss_library.clusters import cluster

    m = models()
    a, b, c = await people(m, "ABC")
    made = await m.Factoid.Create(label="F", statements=[same(a, b, "A is B")]).save(
        detail=True
    )
    assert shape(await cluster(a)) == {"B": (1, [])}
    # the statement now names C, not B
    await m.Factoid.Update(
        id=made.id, label="F", statements=[same(a, c, "A is C")]
    ).save()
    assert shape(await cluster(a)) == {"C": (1, [])}
    assert (await cluster(b)).size == 1
    # ...and is then put in a space
    await m.Factoid.Update(
        id=made.id, label="F", statements=[inside("Negative", same(a, c, "A is not C"))]
    ).save()
    assert (await cluster(a)).size == 1


@no_type_check
async def test_an_unpublished_document_joins_only_for_a_reader_who_sees_it(
    db_driver, clear_database
):
    from pangloss_library.clusters import cluster

    m = models()
    a, b, c = await people(m, "ABC")
    await factoid(m, same(a, b, "A is B"))
    await alias(m, b, c)
    run(db_driver, "MATCH (n:Alias) SET n.published = false")
    # (code that is not a request sees everything)
    assert shape(await cluster(a)) == {"B": (1, []), "C": (2, ["B"])}
    token = see_unpublished.set(False)
    try:
        assert shape(await cluster(a)) == {"B": (1, [])}
    finally:
        see_unpublished.reset(token)


@no_type_check
async def test_a_deleted_entity_is_no_member_and_joins_nothing_further(
    db_driver, clear_database
):
    from pangloss_library.clusters import NoSuchEntity, cluster

    m = models()
    a, b, c = await people(m, "ABC")
    await factoid(m, same(a, b), same(b, c))
    # (an entity that something refers to cannot be deleted through the models: it is, here, as an entity that was
    # deleted before anything referred to it and has been referred to since by a write that raced the delete)
    run(db_driver, "MATCH (n:Person {label: 'B'}) SET n.deleted = true")
    assert (await cluster(a)).size == 1
    assert (await cluster(c)).size == 1
    with pytest.raises(NoSuchEntity):
        await cluster(b)


@no_type_check
async def test_a_merged_entity_counts_as_what_it_was_merged_into(clear_database):
    from pangloss_library.clusters import cluster

    m = models()
    a, b, c, d = await people(m, "ABCD")
    await factoid(m, same(a, b, "A is B"), same(b, c, "B is C"))
    await alias(m, c, d, "C is D")
    assert shape(await cluster(a)) == {
        "B": (1, []),
        "C": (2, ["B"]),
        "D": (3, ["B", "C"]),
    }

    merged = await m.Person.merge(absorb=b, into=a)
    # B is A now: the claim that they are the same is the reason, not a member; what was said of B is said of A
    found = await cluster(a)
    assert shape(found) == {"C": (1, []), "D": (2, ["C"])}
    assert between(found, found.claims) == [
        ("B is C", ("A", "C"), ()),
        ("C is D", ("C", "D"), ()),
    ]
    # asked of B, it is A's
    of_b = await cluster(b)
    assert of_b.entity.id == str(a) and shape(of_b) == shape(found)
    # from the other end the member is A, never B
    assert shape(await cluster(d)) == {"C": (1, []), "A": (2, ["C"])}
    # a search for the cluster does not look for B
    assert str(b) not in found.ids()

    await m.Person.unmerge(merged.merge.id)
    assert shape(await cluster(a)) == {
        "B": (1, []),
        "C": (2, ["B"]),
        "D": (3, ["B", "C"]),
    }


@no_type_check
async def test_a_chain_of_merges_is_followed(clear_database):
    from pangloss_library.clusters import cluster

    m = models()
    a, b, c, d = await people(m, "ABCD")
    await alias(m, c, d, "C is D")
    await m.Person.merge(absorb=c, into=b)
    await m.Person.merge(absorb=b, into=a)
    # (the claim names C, which is B, which is A)
    assert shape(await cluster(a)) == {"D": (1, [])}
    assert shape(await cluster(d)) == {"A": (1, [])}
    assert (await cluster(c)).entity.id == str(a)


@no_type_check
async def test_a_cluster_is_bounded_and_says_when_there_is_more(
    clear_database, monkeypatch
):
    from pangloss_library import clusters

    m = models()
    ids = await people(m, "ABCDEF")
    for one, two in zip(ids, ids[1:], strict=False):
        await alias(m, one, two)
    whole = await clusters.cluster(ids[0])
    assert [member.label for member in whole.members] == list("BCDEF")
    assert whole.size == 6 and whole.large and whole.warning_size == 5
    assert not whole.truncated

    monkeypatch.setattr(clusters, "MAX_STEPS", 2)
    stopped = await clusters.cluster(ids[0])
    assert [member.label for member in stopped.members] == ["B", "C"]
    assert stopped.truncated and not stopped.large
    # (the whole of a cluster that ends where the bound is: nothing more, and it does not say there is)
    monkeypatch.setattr(clusters, "MAX_STEPS", 3)
    exact = await clusters.cluster(ids[2])
    assert len(exact.members) == 5 and not exact.truncated

    monkeypatch.setattr(clusters, "MAX_STEPS", 10)
    monkeypatch.setattr(clusters, "MAX_MEMBERS", 3)
    capped = await clusters.cluster(ids[0])
    assert len(capped.members) == 3 and capped.truncated

    monkeypatch.setattr(clusters, "MAX_MEMBERS", 200)
    monkeypatch.setattr(clusters, "DEFAULT_WARNING_SIZE", 6)
    assert not (await clusters.cluster(ids[0])).large


@no_type_check
async def test_the_size_to_warn_from_is_a_setting(clear_database):
    from pangloss_library import clusters

    assert clusters.warning_size() == 5
    saved = core_settings.SETTINGS
    try:
        core_settings.SETTINGS = SimpleNamespace(IDENTITY_CLUSTER_WARNING=2)
        assert clusters.warning_size() == 2
    finally:
        core_settings.SETTINGS = saved


@no_type_check
async def test_clusters_read_while_claims_are_written_are_each_whole(clear_database):
    """Writers add the links of a chain while readers read the cluster: every reading is of the chain as far as it
    was joined at one moment (a member's way to the entity is all there), and the last has all of it"""
    from pangloss_library.clusters import cluster

    m = models()
    ids = await people(m, "ABCDEFGH")
    labels = dict(zip((str(id) for id in ids), "ABCDEFGH", strict=True))
    readings = []

    async def write(index: int):
        await alias(m, ids[index], ids[index + 1], f"link {index}")

    async def read():
        for _ in range(6):
            readings.append(await cluster(ids[0]))
            await asyncio.sleep(0)

    await asyncio.gather(*(write(i) for i in range(7)), read(), read(), read())
    for found in readings:
        members = {member.id: member for member in found.members}
        for member in found.members:
            # (each is reached through members that are there, one step further each time)
            assert all(id in members for id in member.through)
            assert member.distance == len(member.through) + 1
            assert [labels[id] for id in [*member.through, member.id]] == list(
                "BCDEFGH"[: member.distance]
            )
        assert not found.truncated
    assert [member.label for member in (await cluster(ids[0])).members] == list(
        "BCDEFGH"
    )


@no_type_check
async def test_a_merge_made_while_clusters_are_read_never_gives_an_absorbed_member(
    clear_database,
):
    from pangloss_library.clusters import cluster

    m = models()
    a, b, c, d = await people(m, "ABCD")
    await alias(m, a, b, "A is B")
    await alias(m, b, c, "B is C")
    await alias(m, c, d, "C is D")
    readings = []

    async def read():
        for _ in range(8):
            readings.append(await cluster(d))
            await asyncio.sleep(0)

    await asyncio.gather(m.Person.merge(absorb=c, into=b), read(), read())
    for found in readings:
        labels = sorted(member.label for member in found.members)
        # (before the merge, or after it: never C as a member beside what it was merged into, never a lost end)
        assert labels in (["A", "B", "C"], ["A", "B"]), labels
    assert shape(await cluster(d)) == {"B": (1, []), "A": (2, ["B"])}


# ---------------------------------------------------------------------------
# The search key
# ---------------------------------------------------------------------------


@no_type_check
async def test_a_search_asks_for_any_entity_of_a_cluster(clear_database):
    m = models()
    a, b, c, d = await people(m, "ABCD")
    await factoid(m, same(a, b), inside("Negative", same(a, d)))
    await alias(m, b, c)
    for id, label in ((a, "of A"), (b, "of B"), (c, "of C"), (d, "of D")):
        await m.Mention.Create(label=label, target=[ref(id)]).save()

    async def mentions(where) -> list[str]:
        if isinstance(where, dict):
            where = Match(type="Mention", where=where)
        return sorted(r.label for r in (await m.Mention.search(where)).results)

    # without it, only what names A
    assert await mentions(m.Mention.Where(target=Rel(is_=a))) == ["of A"]
    # the whole cluster (the default), from any member of it
    for id in (a, b, c):
        assert await mentions(m.Mention.Where(target=m.Person.Where(same_as_=id))) == [
            "of A",
            "of B",
            "of C",
        ]
    # one step
    assert await mentions(
        m.Mention.Where(target=m.Person.Where(same_as_={"id": a, "steps": "one"}))
    ) == ["of A", "of B"]
    # as JSON
    assert await mentions(
        {"target": {"type": "Person", "where": {"$same_as": str(c)}}}
    ) == ["of A", "of B", "of C"]
    assert await mentions(
        {
            "target": {
                "type": "Person",
                "where": {"$same_as": {"id": str(c), "steps": "one"}},
            }
        }
    ) == ["of B", "of C"]
    # an entity nothing is said of: itself
    assert await mentions(m.Mention.Where(target=m.Person.Where(same_as_=d))) == [
        "of D"
    ]
    # an id nothing has: nothing, and no error
    assert (
        await mentions(m.Mention.Where(target=m.Person.Where(same_as_=uuid4()))) == []
    )

    # the entities themselves
    found = await m.Person.search(m.Person.Where(same_as_=a))
    assert sorted(r.label for r in found.results) == ["A", "B", "C"]
    # with other conditions, and negated
    found = await m.Person.search(m.Person.Where(same_as_=a, label={"ne": "B"}))
    assert sorted(r.label for r in found.results) == ["A", "C"]
    found = await m.Person.search(Match(where={"$not": {"$same_as": str(a)}}))
    assert sorted(r.label for r in found.results) == ["D"]
    # the documents that claim it are found like any (the factoid, by a member it names)
    found = await m.Factoid.search(
        Match(where={"statements": {"type": "Person", "where": {"$same_as": str(c)}}})
    )
    assert [r.label for r in found.results] == ["Factoid"]


@no_type_check
async def test_a_search_for_a_cluster_follows_a_merge(clear_database):
    m = models()
    a, b, c = await people(m, "ABC")
    await alias(m, b, c)
    for id, label in ((a, "of A"), (b, "of B"), (c, "of C")):
        await m.Mention.Create(label=label, target=[ref(id)]).save()
    await m.Person.merge(absorb=b, into=a)
    # (what named B names A now; the claim that names B is about A)
    found = await m.Mention.search(m.Mention.Where(target=m.Person.Where(same_as_=c)))
    assert sorted(r.label for r in found.results) == ["of A", "of B", "of C"]
    found = await m.Person.search(m.Person.Where(same_as_=b))
    assert sorted(r.label for r in found.results) == ["A", "C"]


@no_type_check
async def test_what_a_search_key_refuses(clear_database):
    m = models()
    [a] = await people(m, "A")
    for wrong in ("not an id", {"steps": "one"}, {"id": str(a), "steps": "two"}, 7):
        with pytest.raises(PanglossSearchError, match=r"\$same_as"):
            await m.Person.search(Match(where={"$same_as": wrong}))
    # only of an entity
    with pytest.raises(PanglossSearchError, match="only for entity patterns"):
        await m.Mention.search(Match(where={"$same_as": str(a)}))
    # a check alone reads nothing, and what it gives cannot be made a query until a search has
    checked = check_match(
        m.Person, search_match(m.Person, Match(where={"$same_as": str(a)}), None)
    )
    with pytest.raises(PanglossSearchError, match="read when a search is run"):
        checked[0].value.cypher(None, "n")


# ---------------------------------------------------------------------------
# The API, and the SDK
# ---------------------------------------------------------------------------


@pytest.fixture
def library_installed(monkeypatch):
    """(the library's routes are made only for an installed app)"""
    monkeypatch.setattr(core_settings.SETTINGS, "INSTALLED_APPS", ["pangloss_library"])


@no_type_check
async def test_the_cluster_over_the_api(db_driver, library_installed, api):  # noqa: F811
    m = models()
    client, users = await api()
    a, b, c = await people(m, "ABC")
    first = await factoid(m, same(a, b, "A is B", argument="The seal"), label="Charter")
    await alias(m, b, c, "B is C")
    await factoid(m, inside("Negative", same(a, c, "A is not C")), label="Roll")

    read = await client.get(f"/api/identity/{a}/cluster")
    assert read.status_code == 200, read.text
    found = read.json()
    assert found["entity"] == {"type": "Person", "id": str(a), "label": "A"}
    assert found["members"] == [
        {"type": "Person", "id": str(b), "label": "B", "distance": 1, "through": []},
        {
            "type": "Person",
            "id": str(c),
            "label": "C",
            "distance": 2,
            "through": [str(b)],
        },
    ]
    assert (found["size"], found["large"], found["warningSize"]) == (3, False, 5)
    assert found["truncated"] is False and found["steps"] == "all"
    [claim] = [c for c in found["claims"] if c["label"] == "A is B"]
    assert claim["head"] == {"type": "Factoid", "id": str(first.id), "label": "Charter"}
    assert claim["between"] == sorted([str(a), str(b)])
    assert claim["argument"] == "The seal" and claim["spaces"] == []
    [said_not] = found["inSpaces"]
    assert said_not["label"] == "A is not C" and said_not["spaces"] == ["Negative"]

    one = await client.get(f"/api/identity/{a}/cluster?steps=one")
    assert [member["label"] for member in one.json()["members"]] == ["B"]
    assert (await client.get(f"/api/identity/{a}/cluster?steps=two")).status_code == 422
    assert (await client.get(f"/api/identity/{uuid4()}/cluster")).status_code == 404
    assert (await client.get("/api/identity/nothing/cluster")).status_code == 422

    # what is not published joins only for someone logged in
    run(db_driver, "MATCH (n:Alias) SET n.published = false")
    anonymous = await client.get(f"/api/identity/{a}/cluster")
    assert [member["label"] for member in anonymous.json()["members"]] == ["B"]
    assert anonymous.json()["inSpaces"] == []
    logged_in = await client.get(f"/api/identity/{a}/cluster", headers=users["ann"])
    assert [member["label"] for member in logged_in.json()["members"]] == ["B", "C"]

    # the search key, as a search is sent
    await m.Mention.Create(label="of C", target=[ref(c)]).save()
    await m.Mention.Create(label="of A", target=[ref(a)]).save()
    for headers, expected in ((users["ann"], ["of A", "of C"]), ({}, ["of A"])):
        searched = await client.post(
            "/api/search",
            json={
                "type": "Mention",
                "where": {"target": {"type": "Person", "where": {"$same_as": str(a)}}},
            },
            headers=headers,
        )
        assert searched.status_code == 200, searched.text
        assert sorted(r["label"] for r in searched.json()["results"]) == expected
    refused = await client.post(
        "/api/search",
        json={
            "type": "Mention",
            "where": {"target": {"type": "Person", "where": {"$same_as": "x"}}},
        },
    )
    assert refused.status_code == 422 and "$same_as" in refused.text


@no_type_check
async def test_the_sdk_reads_the_cluster_the_server_does(
    library_installed,
    through_the_api,  # noqa: F811
):
    from pangloss_library import clusters

    m = models()
    client = await through_the_api(create_app())
    a, b, c = await people(m, "ABC")
    await factoid(m, same(a, b, "A is B"), inside("Negative", same(a, c, "not C")))
    await alias(m, b, c, "B is C")
    for steps in ("all", "one"):
        direct = await clusters.cluster(a, steps)
        over = clusters._answer(
            await client.send(clusters._call(str(a), steps)), str(a)
        )
        assert over == direct
    assert [member.label for member in direct.members] == ["B"]
    with pytest.raises(clusters.NoSuchEntity):
        missing = str(uuid4())
        clusters._answer(await client.send(clusters._call(missing, "all")), missing)
