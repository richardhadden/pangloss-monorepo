"""Derived edges on the backend under test: the two ends as stored and as read, qualifiers that define the edge, values
of a justification that do not, an edge read from each of its ends and from a qualifier, searches, the graph, and what
a wrapper that says nothing does"""

from typing import Annotated, no_type_check

import httpx2 as httpx
import pytest
from pangloss_api import create_app
from pangloss_models import (
    Conjunction,
    Document,
    Entity,
    Match,
    ReifiedRelation,
    SemanticSpace,
    Trait,
    initialise,
)
from pangloss_testing.live import run

from pangloss_derived import (
    DerivedEdge,
    DerivedMeta,
    Object,
    PerJustification,
    RuleType,
    Subject,
    SymmetricLabel,
    Var,
    read,
    rule,
)
from pangloss_derived.worker import run_pending_derivations

pytestmark = pytest.mark.asyncio(loop_scope="session")


@no_type_check
def models():
    class Negative[T](SemanticSpace[T]):
        pass

    # (says nothing of the derivation: one alternative at a time, and read through as if it were not there)
    class Either[T](Conjunction):
        _derived_meta = DerivedMeta(exclusive=True)
        either: list[T]

    # (says nothing at all)
    class Identification[T](ReifiedRelation[T]):
        identified_by: str

    class Agent(Trait):
        pass

    class Person(Entity, Agent):
        pass

    class Group(Entity, Agent):
        pass

    class MemberOf(Document):
        member: Person | Identification[Either[Person]]
        group: Group

    class Transfer(Document):
        given_by: Agent
        given_to: Agent
        year: int
        amount: int

    class Factoid(Document):
        statements: list[MemberOf | Transfer | Negative[MemberOf | Transfer]]

    family = RuleType("family", "Ties of family")
    exchange = RuleType("exchange", "What passed between agents")

    class SameGroup(DerivedEdge):
        """Members of the same group"""

        _meta = DerivedEdge.Meta(symmetric=True)
        first: Annotated[Person, SymmetricLabel("member")]
        second: Annotated[Person, SymmetricLabel("member")]
        group: Group

    class GaveTo(DerivedEdge):
        """Gave something to"""

        giver: Annotated[Agent, Subject()]
        receiver: Annotated[Agent, Object(reverse_name="received_from")]
        year: int
        amount: Annotated[int, PerJustification()]

    @rule(types=[family])
    def same_group(a: Var[Person], b: Var[Person], g: Var[Group]):
        """Two people said to be members of one group"""
        return SameGroup.Derive(first=a, second=b, group=g).when(
            MemberOf.Where(member=a, group=g),
            MemberOf.Where(member=b, group=g),
        )

    @rule(types=[exchange])
    def gave_to(a: Var[Agent], b: Var[Agent], y: Var[int], n: Var[int]):
        """A transfer from one agent to another"""
        return GaveTo.Derive(giver=a, receiver=b, year=y, amount=n).when(
            Transfer.Where(given_by=a, given_to=b, year=y, amount=n)
        )

    initialise()
    return locals()


async def setup(clear_database):
    m = models()
    n = {}
    for name in "ABCD":
        n[name] = await m["Person"].Create(label=name).save()
    for name in "GH":
        n[name] = await m["Group"].Create(label=name).save()
    return m, n


def ref(item):
    return {"type": type(item).__name__.removesuffix("View"), "id": item.id}


def person(item):
    return {"type": "Person", "id": item.id}


def member(who, group, label="m"):
    return {
        "type": "MemberOf",
        "label": label,
        "member": person(who),
        "group": {"type": "Group", "id": group.id},
    }


def one_of(group, *people, label="m?"):
    return {
        "type": "MemberOf",
        "label": label,
        "member": {
            "type": "Identification",
            "identified_by": "Smith",
            "target": [{"type": "Either", "either": [person(p) for p in people]}],
        },
        "group": {"type": "Group", "id": group.id},
    }


def transfer(giver, receiver, year=1500, amount=10, kinds=("Person", "Person")):
    return {
        "type": "Transfer",
        "label": "t",
        "given_by": {"type": kinds[0], "id": giver.id},
        "given_to": {"type": kinds[1], "id": receiver.id},
        "year": year,
        "amount": amount,
    }


async def says(m, label, *statements):
    return await m["Factoid"].Create(label=label, statements=list(statements)).save()


async def gifts(m, **where):
    page = await read.list_facts(
        m["GaveTo"], m["GaveTo"].Where(**where) if where else None, page_size=100
    )
    return sorted(
        (v.giver.label, v.receiver.label, v.qualifiers.year, v.justification_count)
        for v in page["results"]
    )


async def groups(m, **where):
    page = await read.list_facts(
        m["SameGroup"], m["SameGroup"].Where(**where) if where else None, page_size=100
    )
    return sorted(
        (*sorted([v.first.label, v.second.label]), v.qualifiers.group.label)
        for v in page["results"]
    )


# ---------------------------------------------------------------------------
# Stored and read
# ---------------------------------------------------------------------------


@no_type_check
async def test_an_asymmetric_edge_is_stored_with_its_ends_named_and_read_as_one_edge(
    clear_database, db_driver
):
    m, n = await setup(clear_database)
    await says(m, "F1", transfer(n["A"], n["B"], 1500, 80))
    await run_pending_derivations()
    (stored,) = run(
        db_driver,
        "MATCH (d:PGDerived:GaveTo) RETURN properties(d) AS p, "
        "[(d)-[r]->(x) | [type(r), x.label]] AS edges",
    )
    assert stored["p"]["pg_subject"] == "giver"
    assert stored["p"]["pg_object"] == "receiver"
    assert stored["p"]["year"] == 1500
    # (a value of a justification is not on the edge)
    assert "amount" not in stored["p"]
    assert sorted(stored["edges"]) == [["giver", "A"], ["receiver", "B"]]
    (view,) = (await read.list_facts(m["GaveTo"]))["results"]
    assert view.ends == ["giver", "receiver"] and view.symmetric is False
    assert (view.giver.label, view.receiver.label) == ("A", "B")
    assert view.giver.type == "Person"
    assert view.qualifiers.model_dump() == {"year": 1500}
    assert view.plain and not view.qualified_only and view.context_labels == []
    assert view.justification_count == 1 and view.justifications is None
    detail = await read.get_fact(m["GaveTo"], view.id)
    (why,) = detail.justifications
    assert why.rule == "gave_to" and why.values == {"amount": 80}
    assert [e.label for e in why.evidence] == ["F1"]
    (kept,) = run(db_driver, "MATCH (j:PGJustification) RETURN j.`values` AS v")
    assert kept["v"] == '{"amount": 80}'


@no_type_check
async def test_a_symmetric_edge_is_stored_once_with_its_ends_in_order_of_id(
    clear_database, db_driver
):
    m, n = await setup(clear_database)
    # (said in the other order: B before A)
    await says(m, "F1", member(n["B"], n["G"]), member(n["A"], n["G"]))
    await run_pending_derivations()
    (stored,) = run(
        db_driver,
        "MATCH (d:PGDerived:SameGroup) MATCH (d)-[:first]->(a) MATCH (d)-[:second]->(b) "
        "RETURN d.pg_subject AS s, d.pg_object AS o, a.id AS a, b.id AS b",
    )
    assert (stored["s"], stored["o"]) == ("first", "second")
    assert stored["a"] < stored["b"]
    (view,) = (await read.list_facts(m["SameGroup"]))["results"]
    assert view.symmetric and view.ends == ["first", "second"]
    assert await groups(m) == [("A", "B", "G")]


@no_type_check
async def test_a_qualifier_is_part_of_what_the_edge_is(clear_database):
    m, n = await setup(clear_database)
    # (the same two people in two groups, and a gift in each of two years)
    await says(m, "F1", member(n["A"], n["G"]), member(n["B"], n["G"]))
    await says(m, "F2", member(n["A"], n["H"]), member(n["B"], n["H"]))
    await says(m, "F3", transfer(n["A"], n["B"], 1500), transfer(n["A"], n["B"], 1501))
    await run_pending_derivations()
    assert await groups(m) == [("A", "B", "G"), ("A", "B", "H")]
    assert await gifts(m) == [("A", "B", 1500, 1), ("A", "B", 1501, 1)]
    # (a filter by a qualifier: an entity, and a value)
    assert await groups(m, group=n["H"]) == [("A", "B", "H")]
    assert await gifts(m, year=1501) == [("A", "B", 1501, 1)]
    assert await gifts(m, year=1499) == []


@no_type_check
async def test_a_value_of_a_justification_does_not_make_another_edge(
    clear_database, db_driver
):
    m, n = await setup(clear_database)
    await says(m, "F1", transfer(n["A"], n["B"], 1500, 80))
    f2 = await says(m, "F2", transfer(n["A"], n["B"], 1500, 60))
    await run_pending_derivations()
    # (one edge, with two justifications that keep their own values)
    assert await gifts(m) == [("A", "B", 1500, 2)]
    (view,) = (await read.list_facts(m["GaveTo"]))["results"]
    detail = await read.get_fact(m["GaveTo"], view.id)
    assert sorted(
        (j.values["amount"], j.evidence[0].label) for j in detail.justifications
    ) == [(60, "F2"), (80, "F1")]
    # (the amount of one changes: its justification is replaced, the edge stays)
    await (
        m["Factoid"]
        .Update(id=f2.id, label="F2", statements=[transfer(n["A"], n["B"], 1500, 61)])
        .save()
    )
    await run_pending_derivations()
    assert await gifts(m) == [("A", "B", 1500, 2)]
    again = await read.get_fact(m["GaveTo"], view.id)
    assert sorted(j.values["amount"] for j in again.justifications) == [61, 80]
    await m["Factoid"].delete(f2.id)
    await run_pending_derivations()
    assert await gifts(m) == [("A", "B", 1500, 1)]
    assert run(db_driver, "MATCH (d:PGDerived) RETURN count(d) AS n") == [{"n": 1}]


@no_type_check
async def test_the_direction_of_an_asymmetric_edge_is_kept(clear_database):
    m, n = await setup(clear_database)
    await says(m, "F1", transfer(n["A"], n["B"]), transfer(n["B"], n["A"]))
    await says(m, "F2", transfer(n["A"], n["A"], 1502))
    await run_pending_derivations()
    # (two edges, not one: and a thing may give to itself, which a symmetric edge never joins)
    assert await gifts(m) == [
        ("A", "A", 1502, 1),
        ("A", "B", 1500, 1),
        ("B", "A", 1500, 1),
    ]
    GaveTo = m["GaveTo"]
    assert (await read.list_facts(GaveTo, entity=n["A"]))["count"] == 3
    given = await read.list_facts(GaveTo, entity=n["A"], at=["giver"])
    assert sorted(v.receiver.label for v in given["results"]) == ["A", "B"]
    received = await read.list_facts(GaveTo, entity=n["A"], at=["receiver"])
    assert sorted(v.giver.label for v in received["results"]) == ["A", "B"]
    assert (await read.list_facts(GaveTo, entity=n["B"], at=["giver"]))["count"] == 1
    assert await gifts(m, giver=n["B"]) == [("B", "A", 1500, 1)]
    assert await gifts(m, receiver=n["B"]) == [("A", "B", 1500, 1)]
    assert await gifts(m, giver=n["A"], receiver=n["A"]) == [("A", "A", 1502, 1)]
    with pytest.raises(read.PanglossDerivedError, match="has no field 'given'"):
        await read.list_facts(GaveTo, entity=n["A"], at=["given"])


@no_type_check
async def test_a_trait_at_an_end_takes_any_entity_of_it(clear_database):
    m, n = await setup(clear_database)
    await says(m, "F1", transfer(n["A"], n["G"], kinds=("Person", "Group")))
    await run_pending_derivations()
    (view,) = (await read.list_facts(m["GaveTo"]))["results"]
    assert (view.giver.type, view.receiver.type) == ("Person", "Group")
    section = await read.derived_of_entity(m["Group"], n["G"].id)
    assert list(section) == ["received_from"]
    assert section["received_from"]["items"][0]["other"]["label"] == "A"


# ---------------------------------------------------------------------------
# What is derived about an entity
# ---------------------------------------------------------------------------


@no_type_check
async def test_what_is_derived_about_an_entity_is_by_what_it_is_of_the_edge(
    clear_database,
):
    m, n = await setup(clear_database)
    await says(
        m,
        "F1",
        member(n["A"], n["G"]),
        member(n["B"], n["G"]),
        transfer(n["A"], n["B"], 1500, 5),
        transfer(n["C"], n["A"], 1501, 6),
        transfer(n["D"], n["A"], 1502, 7),
    )
    await run_pending_derivations()
    section = await read.derived_of_entity(m["Person"], n["A"].id)
    assert list(section) == ["SameGroup", "GaveTo", "received_from"]
    same = section["SameGroup"]
    assert (same["type"], same["role"], same["count"]) == ("SameGroup", "ends", 1)
    assert same["symmetric"] and same["ends"] == ["first", "second"]
    assert same["symmetricLabel"] == {"name": "member", "fields": ["first", "second"]}
    (row,) = same["items"]
    assert row["other"]["label"] == "B" and row["otherField"] in ("first", "second")
    assert row["as"] == [f for f in ("first", "second") if f != row["otherField"]]
    assert row["fields"] == {
        "group": {"id": str(n["G"].id), "type": "Group", "label": "G"}
    }
    assert "ends" not in row and row["plain"] is True
    # (what it gave, under the class's name; what it received, under the reverse name of the object)
    gave = section["GaveTo"]
    assert (gave["type"], gave["role"], gave["as"]) == ("GaveTo", "subject", ["giver"])
    assert gave["reverseName"] == "received_from" and gave["symmetricLabel"] is None
    (row,) = gave["items"]
    assert (row["other"]["label"], row["otherField"], row["as"]) == (
        "B",
        "receiver",
        ["giver"],
    )
    assert row["fields"] == {"year": 1500} and row["justifications"] == 1
    received = section["received_from"]
    assert (received["type"], received["role"], received["count"]) == (
        "GaveTo",
        "object",
        2,
    )
    assert sorted(
        (r["other"]["label"], r["otherField"], r["fields"]["year"])
        for r in received["items"]
    ) == [("C", "giver", 1501), ("D", "giver", 1502)]
    # (as the view of the person has it)
    viewed = await read.derived_section(m["Person"], await m["Person"].get(n["A"].id))
    assert viewed == {"_derived": section}
    # (nothing about someone nothing is said of; and nothing at all is no key)
    assert await read.derived_of_entity(m["Group"], n["H"].id) == {}
    assert await read.derived_section(m["Group"], await m["Group"].get(n["H"].id)) == {}


@no_type_check
async def test_a_qualifier_entity_lists_the_edges_it_qualifies_with_both_their_ends(
    clear_database,
):
    m, n = await setup(clear_database)
    await says(
        m, "F1", member(n["A"], n["G"]), member(n["B"], n["G"]), member(n["C"], n["G"])
    )
    await says(m, "F2", member(n["A"], n["H"]), member(n["D"], n["H"]))
    await run_pending_derivations()
    section = await read.derived_of_entity(m["Group"], n["G"].id)
    assert list(section) == ["SameGroup:group"]
    qualified = section["SameGroup:group"]
    assert (qualified["role"], qualified["as"], qualified["count"]) == (
        "qualifier",
        ["group"],
        3,
    )
    pairs = sorted(
        tuple(sorted(end["label"] for end in row["ends"].values()))
        for row in qualified["items"]
    )
    assert pairs == [("A", "B"), ("A", "C"), ("B", "C")]
    for row in qualified["items"]:
        assert set(row["ends"]) == {"first", "second"}
        # (the group itself is not repeated in each row)
        assert row["fields"] == {} and row["other"] is None and row["as"] == ["group"]
    other = await read.derived_of_entity(m["Group"], n["H"].id)
    assert other["SameGroup:group"]["count"] == 1
    # (the page route, for "and N more": only the edges it qualifies)
    page = await read.list_facts(m["SameGroup"], entity=n["G"], at=["group"])
    assert page["count"] == 3


@no_type_check
async def test_the_first_page_of_a_section_and_the_pages_after_it(clear_database):
    m, n = await setup(clear_database)
    people = [await m["Person"].Create(label=f"P{i:02}").save() for i in range(30)]
    await says(m, "F1", *[transfer(n["A"], p, 1500) for p in people])
    await says(m, "F2", transfer(people[0], n["A"], 1500))
    await run_pending_derivations()
    section = await read.derived_of_entity(m["Person"], n["A"].id)
    gave = section["GaveTo"]
    assert gave["count"] == 30 and len(gave["items"]) == read.FIRST_PAGE
    # (in order of the label of... the subject, which is A for all: then by key; all of them come, once)
    seen = {row["id"] for row in gave["items"]}
    second = await read.list_facts(m["GaveTo"], entity=n["A"], at=["giver"], page=2)
    assert second["count"] == 30 and second["next_page"] is None
    seen |= {v.id for v in second["results"]}
    assert len(seen) == 30
    assert section["received_from"]["count"] == 1
    # (a page past the end still says how many there are)
    past = await read.list_facts(m["GaveTo"], entity=n["A"], at=["giver"], page=9)
    assert past["results"] == [] and past["count"] == 30


# ---------------------------------------------------------------------------
# Filters and searches
# ---------------------------------------------------------------------------


@no_type_check
async def test_a_filter_by_an_end_of_a_symmetric_edge_matches_either_end(
    clear_database,
):
    m, n = await setup(clear_database)
    await says(
        m, "F1", member(n["A"], n["G"]), member(n["B"], n["G"]), member(n["C"], n["G"])
    )
    await run_pending_derivations()
    for who in "ABC":
        others = sorted(set("ABC") - {who})
        expected = sorted((*sorted([who, o]), "G") for o in others)
        # (whichever field is named, and whichever end the id's order put it at)
        assert await groups(m, first=n[who]) == expected
        assert await groups(m, second=n[who]) == expected
    assert await groups(m, first=n["C"], second=n["A"]) == [("A", "C", "G")]
    assert await groups(m, first=n["A"], second=n["C"]) == [("A", "C", "G")]
    assert await groups(m, first=n["A"], second=n["D"]) == []
    assert await groups(m, first=n["A"], group=n["H"]) == []


@no_type_check
async def test_a_search_by_a_derived_edge_gives_the_other_end(clear_database):
    m, n = await setup(clear_database)
    await says(
        m,
        "F1",
        member(n["A"], n["G"]),
        member(n["B"], n["G"]),
        member(n["C"], n["G"]),
        transfer(n["A"], n["B"], 1500),
        transfer(n["C"], n["B"], 1501),
        transfer(n["B"], n["D"], 1502),
    )
    await run_pending_derivations()
    Person, GaveTo, SameGroup = m["Person"], m["GaveTo"], m["SameGroup"]

    async def found(where):
        return sorted(p.label for p in (await Person.search(where)).results)

    # (anyone in a gift, at either end)
    assert await found(Person.Where(derived_=GaveTo.Where())) == ["A", "B", "C", "D"]
    # (who gave to B: not B, which is the end the filter gives)
    assert await found(Person.Where(derived_=GaveTo.Where(receiver=n["B"]))) == [
        "A",
        "C",
    ]
    assert await found(Person.Where(derived_=GaveTo.Where(giver=n["B"]))) == ["D"]
    assert await found(
        Person.Where(derived_=GaveTo.Where(receiver=n["B"], year=1501))
    ) == ["C"]
    assert await found(Person.Where(derived_=GaveTo.Where(year=1502))) == ["B", "D"]
    # (of a symmetric class: those in a group with B, by either field; never B)
    assert await found(Person.Where(derived_=SameGroup.Where(first=n["B"]))) == [
        "A",
        "C",
    ]
    assert await found(Person.Where(derived_=SameGroup.Where(second=n["B"]))) == [
        "A",
        "C",
    ]
    assert await found(Person.Where(derived_=SameGroup.Where(group=n["G"]))) == [
        "A",
        "B",
        "C",
    ]
    # (the JSON, as the API takes it)
    assert await found(
        Match(
            where={
                "$derived": {"type": "GaveTo", "where": {"receiver": str(n["B"].id)}}
            }
        )
    ) == ["A", "C"]
    # (a group, by the edges it qualifies)
    groups_found = await m["Group"].search(
        m["Group"].Where(derived_=SameGroup.Where(first=n["A"]))
    )
    assert [g.label for g in groups_found.results] == ["G"]


@no_type_check
async def test_the_graph_has_the_subject_as_source_the_qualifiers_and_a_weight(
    clear_database,
):
    m, n = await setup(clear_database)
    await says(m, "F1", transfer(n["B"], n["A"], 1500, 80))
    await says(m, "F2", transfer(n["B"], n["A"], 1500, 60))
    await says(m, "F3", member(n["A"], n["G"]), member(n["B"], n["G"]))
    await run_pending_derivations()
    (edge,) = await read.graph("exchange")
    assert (edge["source"]["label"], edge["target"]["label"]) == ("B", "A")
    assert edge["class"] == "GaveTo" and edge["symmetric"] is False
    # (the qualifiers only: not the ends again, nor a value of a justification)
    assert edge["attributes"] == {"year": 1500}
    assert edge["justifications"] == 2 and edge["weight"] == 2 and edge["plain"]
    (tie,) = await read.graph("family")
    assert tie["symmetric"] and tie["weight"] == 1
    assert tie["attributes"]["group"]["label"] == "G"


# ---------------------------------------------------------------------------
# What a wrapper does by default
# ---------------------------------------------------------------------------


@no_type_check
async def test_an_identification_that_says_nothing_is_read_through(clear_database):
    m, n = await setup(clear_database)
    await says(m, "F1", member(n["A"], n["G"]))
    await says(m, "F2", one_of(n["G"], n["B"], n["C"]))
    await run_pending_derivations()
    page = await read.list_facts(m["SameGroup"], page_size=100)
    found = sorted(
        (
            *sorted([v.first.label, v.second.label]),
            tuple(v.context_labels),
            v.plain,
        )
        for v in page["results"]
    )
    # (plain, through an identification and an alternative: and still one alternative at a time, so not B with C)
    assert found == [("A", "B", (), True), ("A", "C", (), True)]
    (edge, _) = page["results"]
    detail = await read.get_fact(m["SameGroup"], edge.id)
    (why,) = detail.justifications
    assert why.context_labels == []
    # (what it passed through is not kept in the context either)
    assert [r["through"] for r in why.context.relations if r["field"] == "member"] == [
        [],
        [],
    ]


@no_type_check
async def test_a_semantic_space_still_qualifies(clear_database):
    m, n = await setup(clear_database)
    await says(m, "F1", member(n["A"], n["G"]))
    await says(
        m, "F2", {"type": "Negative", "contents": [one_of(n["G"], n["B"], n["C"])]}
    )
    await says(
        m, "F3", {"type": "Negative", "contents": [transfer(n["A"], n["B"], 1500, 9)]}
    )
    await run_pending_derivations()
    page = await read.list_facts(m["SameGroup"], page_size=100)
    assert sorted(
        (tuple(v.context_labels), v.plain, v.qualified_only) for v in page["results"]
    ) == [(("Negative",), False, True), (("Negative",), False, True)]
    assert (await read.list_facts(m["SameGroup"], m["SameGroup"].Where(plain=True)))[
        "count"
    ] == 0
    (gift,) = (await read.list_facts(m["GaveTo"]))["results"]
    assert gift.context_labels == ["Negative"] and not gift.plain
    # (said plainly as well: the edge is plain, and keeps the label of the justification that is not)
    await says(m, "F4", transfer(n["A"], n["B"], 1500, 9))
    await run_pending_derivations()
    (gift,) = (await read.list_facts(m["GaveTo"]))["results"]
    assert gift.plain and gift.context_labels == ["Negative"]
    assert gift.justification_count == 2
    assert await read.graph("exchange", plain_only=True) != []
    assert await read.graph("family", plain_only=True) == []


# ---------------------------------------------------------------------------
# The API
# ---------------------------------------------------------------------------


@no_type_check
async def test_the_api_gives_edges_their_ends_and_the_sections_of_an_entity(
    clear_database,
):
    m, n = await setup(clear_database)
    await says(
        m,
        "F1",
        member(n["A"], n["G"]),
        member(n["B"], n["G"]),
        transfer(n["A"], n["B"], 1500, 80),
        transfer(n["C"], n["A"], 1501, 60),
    )
    await run_pending_derivations()
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        schema = (await client.get("/api/derived")).json()["classes"]
        gave = schema["GaveTo"]
        assert gave["ends"] == ["giver", "receiver"] and gave["symmetric"] is False
        assert gave["reverseName"] == "received_from"
        assert gave["qualifiers"] == ["year"] and gave["perJustification"] == ["amount"]
        assert {f: v["role"] for f, v in gave["fields"].items()} == {
            "giver": "subject",
            "receiver": "object",
            "year": "qualifier",
            "amount": "per_justification",
        }
        assert schema["SameGroup"]["symmetricLabel"] == {
            "name": "member",
            "fields": ["first", "second"],
        }
        assert schema["SameGroup"]["reverseName"] is None

        page = (
            await client.get("/api/derived/GaveTo", params={"giver": str(n["A"].id)})
        ).json()
        (edge,) = page["results"]
        assert edge["type"] == "GaveTo" and edge["ends"] == ["giver", "receiver"]
        assert edge["giver"]["label"] == "A" and edge["receiver"]["label"] == "B"
        assert edge["qualifiers"] == {"year": 1500}
        assert edge["symmetric"] is False and edge["plain"] is True
        assert edge["contextLabels"] == [] and edge["justificationCount"] == 1
        assert "year" not in edge and "amount" not in edge

        why = (await client.get(f"/api/derived/GaveTo/{edge['id']}")).json()
        (justification,) = why["justifications"]
        assert justification["values"] == {"amount": 80}

        # (a qualifier as a parameter; a value of a justification is not one)
        assert (await client.get("/api/derived/GaveTo", params={"year": 1501})).json()[
            "count"
        ] == 1
        refused = await client.get("/api/derived/GaveTo", params={"amount": 80})
        assert refused.status_code == 422
        assert "Unknown query parameter 'amount'" in refused.text

        # (the edges of an entity, at one end only)
        a = str(n["A"].id)
        both = await client.get("/api/derived/GaveTo", params={"entity": a})
        assert both.json()["count"] == 2
        given = await client.get(
            "/api/derived/GaveTo", params={"entity": a, "at": "giver"}
        )
        assert [e["receiver"]["label"] for e in given.json()["results"]] == ["B"]
        received = await client.get(
            "/api/derived/GaveTo", params={"entity": a, "at": "receiver"}
        )
        assert [e["giver"]["label"] for e in received.json()["results"]] == ["C"]
        either = await client.get(
            "/api/derived/GaveTo", params={"entity": a, "at": "giver,receiver"}
        )
        assert either.json()["count"] == 2
        for wrong, said in (
            ({"at": "giver"}, "`at` needs `entity`"),
            ({"entity": a, "at": "given"}, "GaveTo has no relation field 'given'"),
            ({"entity": a, "at": "year"}, "GaveTo has no relation field 'year'"),
        ):
            response = await client.get("/api/derived/GaveTo", params=wrong)
            assert response.status_code == 422, response.text
            assert said in response.text

        # (a symmetric end as a parameter matches either end)
        for field in ("first", "second"):
            for who in "AB":
                tie = await client.get(
                    "/api/derived/SameGroup", params={field: str(n[who].id)}
                )
                assert tie.json()["count"] == 1

        viewed = (await client.get(f"/api/Person/{a}")).json()["_derived"]
        assert list(viewed) == ["SameGroup", "GaveTo", "received_from"]
        assert viewed["received_from"]["items"][0]["other"]["label"] == "C"
        about = (await client.get(f"/api/derived/about/Person/{a}")).json()
        assert about == viewed
        group = (await client.get(f"/api/derived/about/Group/{n['G'].id}")).json()
        assert list(group) == ["SameGroup:group"]
        assert set(group["SameGroup:group"]["items"][0]["ends"]) == {"first", "second"}

        graph = (await client.get("/api/derived/graph/exchange")).json()
        assert graph["count"] == 2
        assert {e["weight"] for e in graph["edges"]} == {1}
        assert all(set(e["attributes"]) == {"year"} for e in graph["edges"])


# ---------------------------------------------------------------------------
# Merged entities (the core's merge)
# ---------------------------------------------------------------------------


@no_type_check
async def test_a_merged_end_moves_its_edges_to_the_survivor(clear_database, db_driver):
    m, n = await setup(clear_database)
    await says(m, "F1", member(n["A"], n["G"]), member(n["C"], n["G"]))
    await says(m, "F2", member(n["B"], n["G"]))
    await says(m, "F3", transfer(n["B"], n["D"], 1500, 1))
    await says(
        m, "F4", transfer(n["A"], n["D"], 1500, 2), transfer(n["D"], n["B"], 1501)
    )
    await run_pending_derivations()
    assert await groups(m) == [("A", "B", "G"), ("A", "C", "G"), ("B", "C", "G")]
    assert await gifts(m) == [
        ("A", "D", 1500, 1),
        ("B", "D", 1500, 1),
        ("D", "B", 1501, 1),
    ]
    await m["Person"].merge(absorb=n["B"].id, into=n["A"].id)
    done = await run_pending_derivations()
    assert done["heads"] > 0
    # (B's membership is A's now: no edge of A with itself, and A with C rests on both factoids)
    assert await groups(m) == [("A", "C", "G")]
    (tie,) = (await read.list_facts(m["SameGroup"]))["results"]
    detail = await read.get_fact(m["SameGroup"], tie.id)
    assert sorted(
        tuple(sorted(e.label for e in j.evidence)) for j in detail.justifications
    ) == [("F1",), ("F1", "F2")]
    # (the two gifts to D of one year are one edge now, with a justification from each factoid)
    assert await gifts(m) == [("A", "D", 1500, 2), ("D", "A", 1501, 1)]
    # (nothing is left about the one absorbed)
    assert run(
        db_driver,
        "MATCH (d:PGDerived)-[]->(x {id: $id}) RETURN count(d) AS n",
        id=str(n["B"].id),
    ) == [{"n": 0}]
    section = await read.derived_of_entity(m["Person"], n["A"].id)
    assert list(section) == ["SameGroup", "GaveTo", "received_from"]


@no_type_check
async def test_a_merged_qualifier_makes_two_edges_one(clear_database, db_driver):
    m, n = await setup(clear_database)
    await says(m, "F1", member(n["A"], n["G"]), member(n["B"], n["G"]))
    await says(m, "F2", member(n["A"], n["H"]), member(n["B"], n["H"]))
    await run_pending_derivations()
    assert await groups(m) == [("A", "B", "G"), ("A", "B", "H")]
    await m["Group"].merge(absorb=n["H"].id, into=n["G"].id)
    await run_pending_derivations()
    assert await groups(m) == [("A", "B", "G")]
    (tie,) = (await read.list_facts(m["SameGroup"]))["results"]
    # (each membership of A with each of B, now that the two groups are one)
    assert tie.justification_count == 4
    assert run(db_driver, "MATCH (d:PGDerived) RETURN count(d) AS n") == [{"n": 1}]
    section = await read.derived_of_entity(m["Group"], n["G"].id)
    assert section["SameGroup:group"]["count"] == 1


@no_type_check
async def test_a_rebuild_finds_every_edge_again_and_changes_nothing(
    clear_database, db_driver
):
    from pangloss_derived.registry import DerivedRegistry
    from pangloss_derived.worker import worker

    m, n = await setup(clear_database)
    await says(
        m,
        "F1",
        member(n["A"], n["G"]),
        member(n["B"], n["G"]),
        transfer(n["A"], n["B"], 1500, 80),
        transfer(n["A"], n["B"], 1500, 60),
    )
    await run_pending_derivations()

    def stored():
        return (
            run(db_driver, "MATCH (d:PGDerived) RETURN d.key AS k ORDER BY k"),
            run(db_driver, "MATCH (j:PGJustification) RETURN j.key AS k ORDER BY k"),
        )

    before = stored()
    assert (len(before[0]), len(before[1])) == (2, 3)
    for name in ("same_group", "gave_to"):
        counts = await worker.rebuild(DerivedRegistry.checked[name])
        assert (counts["new"], counts["removed"]) == (0, 0), counts
    assert stored() == before
