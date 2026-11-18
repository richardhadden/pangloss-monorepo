"""Edges declared on document classes (`DerivesEdge`), on the backend under test: what a document gives, one edge for
each pair whatever the number of documents, several document classes that give one edge, subclasses, and that such an
edge is read, searched and kept up to date as any other"""

from typing import no_type_check

import httpx2 as httpx
import pytest
from pangloss_api import create_app
from pangloss_models import (
    Document,
    Entity,
    ReifiedRelation,
    SemanticSpace,
    Trait,
    Var,
    initialise,
)
from pangloss_testing.live import run

from pangloss_derived import DerivedEdge, DerivesEdge, RuleType, read, rule
from pangloss_derived.store import digest
from pangloss_derived.worker import run_pending_derivations

pytestmark = pytest.mark.asyncio(loop_scope="session")

exchange = RuleType("exchange", "What passed between agents")
social = RuleType("social", "Who had to do with whom")


@no_type_check
def models():
    class Negative[T](SemanticSpace[T]):
        pass

    class InRole[T](ReifiedRelation[T]):
        role: str

    class Agent(Trait):
        pass

    class Person(Entity, Agent):
        pass

    class Group(Entity, Agent):
        pass

    class Place(Entity):
        pass

    class Transfer(Document):
        _derives = [
            DerivesEdge(
                "GaveTo",
                subject="given_by",
                object="given_to",
                ends=("giver", "receiver"),
                reverse_name="received_from",
                qualifiers={"year": "year"},
                types=[exchange, social],
            )
        ]
        given_by: Agent
        given_to: Agent
        year: int

    class Bequest(Transfer):
        executor: Person

    class Sale(Document):
        _derives = [
            DerivesEdge(
                "GaveTo",
                subject="seller",
                object="buyer",
                ends=("giver", "receiver"),
                reverse_name="received_from",
                qualifiers={"year": "sold_in"},
                types=[exchange],
            )
        ]
        seller: Agent
        buyer: Person
        sold_in: int

    class Activity(Document):
        _derives = [
            DerivesEdge(
                "CoParticipants",
                subject="participants",
                object="participants",
                symmetric=True,
                label="participant",
                types=[social],
            ),
            DerivesEdge(
                "TookPlaceWith",
                subject="participants",
                object="host",
                qualifiers={"at": "place"},
            ),
        ]
        participants: list[Agent | InRole[Agent]]
        host: Person | None = None
        place: Place | None = None

    class Marriage(Document):
        _derives = [
            DerivesEdge("MarriedTo", subject="husband", object="wife", symmetric=True)
        ]
        husband: Person
        wife: Person

    class Factoid(Document):
        statements: list[
            Transfer
            | Bequest
            | Sale
            | Activity
            | Marriage
            | Negative[Transfer | Activity]
        ]

    # (as a `derived.py` would: a rule of its own for an edge that a document class declares)
    @rule(types=[exchange])
    def executors(a: Var[Person], b: Var[Agent], y: Var[int]):
        """The executor of a bequest hands it over"""
        return (
            DerivedEdge.named("GaveTo")
            .Derive(giver=a, receiver=b, year=y)
            .when(Bequest.Where(executor=a, given_to=b, year=y))
        )

    initialise()
    return locals()


async def setup(clear_database):
    m = models()
    n = {}
    for name in "ABCD":
        n[name] = await m["Person"].Create(label=name).save()
    n["G"] = await m["Group"].Create(label="G").save()
    n["P"] = await m["Place"].Create(label="P").save()
    return m, n


def ref(item, kind="Person"):
    return {"type": kind, "id": item.id}


def transfer(giver, receiver, year=1500, kind="Transfer", **more):
    return {
        "type": kind,
        "label": "t",
        "given_by": giver if isinstance(giver, dict) else ref(giver),
        "given_to": receiver if isinstance(receiver, dict) else ref(receiver),
        "year": year,
        **more,
    }


def sale(seller, buyer, year=1500):
    return {
        "type": "Sale",
        "label": "s",
        "seller": seller if isinstance(seller, dict) else ref(seller),
        "buyer": ref(buyer),
        "sold_in": year,
    }


def activity(*participants, **more):
    return {
        "type": "Activity",
        "label": "act",
        "participants": [p if isinstance(p, dict) else ref(p) for p in participants],
        **more,
    }


def in_role(who, role="guest"):
    return {"type": "InRole", "role": role, "target": [ref(who)]}


async def says(m, label, *statements):
    return await m["Factoid"].Create(label=label, statements=list(statements)).save()


async def gifts():
    GaveTo = DerivedEdge.named("GaveTo")
    page = await read.list_facts(GaveTo, page_size=100)
    return sorted(
        (
            v.giver.label,
            v.receiver.label,
            v.qualifiers.year,
            v.justification_count,
            tuple(v.context_labels),
        )
        for v in page["results"]
    )


async def pairs(name):
    edge = DerivedEdge.named(name)
    a, b = edge._ends
    page = await read.list_facts(edge, page_size=100)
    return sorted(
        (*sorted([getattr(v, a).label, getattr(v, b).label]), v.justification_count)
        for v in page["results"]
    )


@no_type_check
async def test_a_document_gives_the_edge_between_its_two_fields(
    clear_database, db_driver
):
    m, n = await setup(clear_database)
    f = await says(m, "F1", transfer(n["A"], n["B"], 1500))
    done = await run_pending_derivations()
    assert done["heads"] == 1
    assert await gifts() == [("A", "B", 1500, 1, ())]
    GaveTo = DerivedEdge.named("GaveTo")
    (view,) = (await read.list_facts(GaveTo))["results"]
    # (the edge is the one a written class of that name would be: its key is of the class, its ends and its year)
    assert view.id == digest("GaveTo", [str(n["A"].id), str(n["B"].id), 1500])
    assert view.types == ["exchange", "social"]
    detail = await read.get_fact(GaveTo, view.id)
    (why,) = detail.justifications
    assert why.rule == "Transfer__GaveTo"
    assert why.description == "`given_by` and `given_to` of one Transfer"
    assert [e.label for e in why.evidence] == ["F1"]
    (stored,) = run(
        db_driver,
        "MATCH (d:PGDerived:GaveTo) RETURN d.pg_subject AS s, d.pg_object AS o",
    )
    assert (stored["s"], stored["o"]) == ("giver", "receiver")
    # (changed, and deleted: as any derived edge)
    await (
        m["Factoid"]
        .Update(id=f.id, label="F1", statements=[transfer(n["B"], n["A"], 1501)])
        .save()
    )
    await run_pending_derivations()
    assert await gifts() == [("B", "A", 1501, 1, ())]
    await m["Factoid"].delete(f.id)
    await run_pending_derivations()
    assert await gifts() == []
    assert run(db_driver, "MATCH (d:PGDerived) RETURN count(d) AS n") == [{"n": 0}]


@no_type_check
async def test_one_edge_for_a_pair_whatever_the_number_of_documents(clear_database):
    m, n = await setup(clear_database)
    for label in ("F1", "F2", "F3"):
        await says(m, label, transfer(n["A"], n["B"], 1500))
    await says(m, "F4", transfer(n["A"], n["B"], 1501))
    await run_pending_derivations()
    # (three documents are three justifications of the one edge; another year is another edge)
    assert await gifts() == [("A", "B", 1500, 3, ()), ("A", "B", 1501, 1, ())]
    edges = await read.graph("exchange")
    assert sorted((e["attributes"]["year"], e["weight"]) for e in edges) == [
        (1500, 3),
        (1501, 1),
    ]
    GaveTo = DerivedEdge.named("GaveTo")
    page = await read.list_facts(GaveTo, GaveTo.Where(year=1500))
    detail = await read.get_fact(GaveTo, page["results"][0].id)
    assert sorted(j.evidence[0].label for j in detail.justifications) == [
        "F1",
        "F2",
        "F3",
    ]


@no_type_check
async def test_several_document_classes_and_a_written_rule_give_one_edge(
    clear_database,
):
    m, n = await setup(clear_database)
    await says(m, "F1", transfer(n["A"], n["B"], 1500))
    await says(m, "F2", sale(n["A"], n["B"], 1500))
    await says(m, "F3", sale(ref(n["G"], "Group"), n["C"], 1502))
    await run_pending_derivations()
    assert await gifts() == [("A", "B", 1500, 2, ()), ("G", "C", 1502, 1, ())]
    GaveTo = DerivedEdge.named("GaveTo")
    page = await read.list_facts(GaveTo, GaveTo.Where(year=1500))
    detail = await read.get_fact(GaveTo, page["results"][0].id)
    assert sorted(j.rule for j in detail.justifications) == [
        "Sale__GaveTo",
        "Transfer__GaveTo",
    ]
    # (the edge has the types of the rules that derive it; the graph of a type has what its rules derive)
    assert detail.types == ["exchange", "social"]
    assert len(await read.graph("exchange")) == 2
    assert [e["source"]["label"] for e in await read.graph("social")] == ["A"]
    # (a subclass of the document class gives its parent's edge; and the written rule one of its own)
    await says(
        m, "F4", transfer(n["A"], n["D"], 1503, kind="Bequest", executor=ref(n["C"]))
    )
    await run_pending_derivations()
    by_rule = {}
    for view in (await read.list_facts(GaveTo, GaveTo.Where(year=1503)))["results"]:
        detail = await read.get_fact(GaveTo, view.id)
        by_rule[(view.giver.label, view.receiver.label)] = [
            j.rule for j in detail.justifications
        ]
    assert by_rule == {
        ("A", "D"): ["Transfer__GaveTo"],
        ("C", "D"): ["executors"],
    }


@no_type_check
async def test_one_field_as_both_ends_pairs_everyone_once(clear_database):
    m, n = await setup(clear_database)
    await says(m, "F1", activity(n["A"], in_role(n["B"]), ref(n["G"], "Group")))
    await run_pending_derivations()
    # (each pair once, through a role as if it were not there, and nobody with themselves)
    assert await pairs("CoParticipants") == [
        ("A", "B", 1),
        ("A", "G", 1),
        ("B", "G", 1),
    ]
    edge = DerivedEdge.named("CoParticipants")
    (first, *_) = (await read.list_facts(edge))["results"]
    assert first.symmetric and first.plain and first.context_labels == []
    # (an activity of one, and the same people again in another)
    await says(m, "F2", activity(n["D"]))
    await says(m, "F3", activity(n["B"], n["A"]))
    await run_pending_derivations()
    assert await pairs("CoParticipants") == [
        ("A", "B", 2),
        ("A", "G", 1),
        ("B", "G", 1),
    ]
    section = await read.derived_of_entity(m["Person"], n["A"].id)
    assert section["CoParticipants"]["symmetricLabel"] == {
        "name": "participant",
        "fields": ["first", "second"],
    }
    assert section["CoParticipants"]["count"] == 2


@no_type_check
async def test_a_list_field_and_an_optional_one_and_a_qualifier_that_is_an_entity(
    clear_database,
):
    m, n = await setup(clear_database)
    place = ref(n["P"], "Place")
    await says(m, "F1", activity(n["A"], n["B"], host=ref(n["C"]), place=place))
    # (no host: no edge; a host and no place: no edge either, as the place is part of what the edge is)
    await says(m, "F2", activity(n["A"], n["B"]))
    await says(m, "F3", activity(n["D"], host=ref(n["C"])))
    await run_pending_derivations()
    edge = DerivedEdge.named("TookPlaceWith")
    page = await read.list_facts(edge, page_size=100)
    assert sorted(
        (v.participants.label, v.host.label, v.qualifiers.at.label)
        for v in page["results"]
    ) == [("A", "C", "P"), ("B", "C", "P")]
    # (the place lists the edges it qualifies)
    section = await read.derived_of_entity(m["Place"], n["P"].id)
    assert section["TookPlaceWith:at"]["count"] == 2
    # (the host is at the object end, with no reverse name: under the class's own)
    host = await read.derived_of_entity(m["Person"], n["C"].id)
    assert list(host) == ["TookPlaceWith"] and host["TookPlaceWith"]["count"] == 2


@no_type_check
async def test_a_symmetric_edge_of_two_fields_is_stored_once(clear_database, db_driver):
    m, n = await setup(clear_database)

    def marriage(husband, wife):
        return {
            "type": "Marriage",
            "label": "m",
            "husband": ref(husband),
            "wife": ref(wife),
        }

    # (whichever of the two has the lower id is the husband in one and the wife in the other)
    await says(m, "F1", marriage(n["A"], n["B"]))
    await says(m, "F2", marriage(n["B"], n["A"]))
    await says(m, "F3", marriage(n["C"], n["C"]))
    await run_pending_derivations()
    assert await pairs("MarriedTo") == [("A", "B", 2)]
    (stored,) = run(
        db_driver,
        "MATCH (d:PGDerived:MarriedTo) MATCH (d)-[:husband]->(a) MATCH (d)-[:wife]->(b) "
        "RETURN a.id < b.id AS ordered",
    )
    assert stored["ordered"]
    edge = DerivedEdge.named("MarriedTo")
    for field in ("husband", "wife"):
        for who in "AB":
            page = await read.list_facts(edge, edge.Where(**{field: n[who]}))
            assert page["count"] == 1


@no_type_check
async def test_a_declared_edge_inside_a_space_has_its_context(clear_database):
    m, n = await setup(clear_database)
    await says(
        m, "F1", {"type": "Negative", "contents": [transfer(n["A"], n["B"], 1500)]}
    )
    await run_pending_derivations()
    assert await gifts() == [("A", "B", 1500, 1, ("Negative",))]
    await says(m, "F2", transfer(n["A"], n["B"], 1500))
    await run_pending_derivations()
    GaveTo = DerivedEdge.named("GaveTo")
    (view,) = (await read.list_facts(GaveTo))["results"]
    assert view.plain and view.justification_count == 2


@no_type_check
async def test_a_declared_edge_in_the_api_and_in_a_search(clear_database):
    m, n = await setup(clear_database)
    await says(m, "F1", transfer(n["A"], n["B"], 1500), sale(n["C"], n["B"], 1501))
    await run_pending_derivations()
    Person = m["Person"]
    GaveTo = DerivedEdge.named("GaveTo")
    found = await Person.search(Person.Where(derived_=GaveTo.Where(receiver=n["B"])))
    assert sorted(p.label for p in found.results) == ["A", "C"]
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        schema = (await client.get("/api/derived")).json()
        assert schema["classes"]["GaveTo"]["ends"] == ["giver", "receiver"]
        assert schema["classes"]["GaveTo"]["reverseName"] == "received_from"
        assert sorted(schema["rules"]) == [
            "Activity__CoParticipants",
            "Activity__TookPlaceWith",
            "Marriage__MarriedTo",
            "Sale__GaveTo",
            "Transfer__GaveTo",
            "executors",
        ]
        assert sorted(schema["types"]["exchange"]["rules"]) == [
            "Sale__GaveTo",
            "Transfer__GaveTo",
            "executors",
        ]
        page = (
            await client.get("/api/derived/GaveTo", params={"receiver": str(n["B"].id)})
        ).json()
        assert sorted(e["giver"]["label"] for e in page["results"]) == ["A", "C"]
        viewed = (await client.get(f"/api/Person/{n['B'].id}")).json()["_derived"]
        assert list(viewed) == ["received_from"]
        assert viewed["received_from"]["count"] == 2
