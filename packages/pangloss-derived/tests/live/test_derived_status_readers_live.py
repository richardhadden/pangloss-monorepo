"""A justification's status kept, a fact's summed up, and what reads them, on the backend under test
(`pangloss_derived.status`; implementation_docs/spaces-and-comparison-plan.md, step 4.1 (c) and (d)): rules that take
justifications of other statuses (`.when(..., status=[...])`: what was denied, what was forbidden), a fact's status
in Cypher and by `status.summed` on mixed facts, and the views, filters, API, graph and why."""

import httpx2 as httpx
import pytest
from typing import Annotated, no_type_check

from pangloss_api import create_app
from pangloss_derived import (
    DerivedEdge,
    Object,
    RuleType,
    Subject,
    Var,
    read,
    rule,
)
from pangloss_derived.export import graphml
from pangloss_derived.status import STATUSES, ordered, summed
from pangloss_derived.worker import run_pending_derivations
from pangloss_models import Document, Entity, Modal, SemanticSpace, initialise
from pangloss_testing.live import run

pytestmark = pytest.mark.asyncio(loop_scope="session")


@no_type_check
def models():
    class Reported[T](SemanticSpace[T]):
        pass

    class Known[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(veridical=1)

    class Not[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical="not")

    class Ordered[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(
            logical=Modal("necessity", "command"), fit="prescribes"
        )

    class Person(Entity):
        pass

    class Purchase(Document):
        buyer: Person | Not[Person]
        seller: Person

    class Factoid(Document):
        statements: list[
            Purchase
            | Reported[Purchase | Not[Purchase]]
            | Known[Purchase]
            | Not[Purchase | Known[Purchase]]
            | Ordered[Purchase | Not[Purchase]]
        ]

    trade = RuleType("trade", "Who traded with whom")

    class BoughtFrom(DerivedEdge):
        """Who bought from whom"""

        buyer: Annotated[Person, Subject()]
        seller: Annotated[Person, Object()]

    class DidNotBuyFrom(DerivedEdge):
        """Who is said not to have bought from whom"""

        buyer: Annotated[Person, Subject()]
        seller: Annotated[Person, Object()]

    class ForbiddenToBuyFrom(DerivedEdge):
        """Who was forbidden to buy from whom"""

        buyer: Annotated[Person, Subject()]
        seller: Annotated[Person, Object()]

    class SaidToHaveBoughtFrom(DerivedEdge):
        """Whatever any source says of a purchase"""

        buyer: Annotated[Person, Subject()]
        seller: Annotated[Person, Object()]

    @rule
    def bought_from(a: Var[Person], b: Var[Person]):
        return BoughtFrom.Derive(buyer=a, seller=b).when(
            Purchase.Where(buyer=a, seller=b)
        )

    @rule
    def did_not_buy_from(a: Var[Person], b: Var[Person]):
        return DidNotBuyFrom.Derive(buyer=a, seller=b).when(
            Purchase.Where(buyer=a, seller=b), status=["denied"]
        )

    @rule
    def forbidden_to_buy_from(a: Var[Person], b: Var[Person]):
        return ForbiddenToBuyFrom.Derive(buyer=a, seller=b).when(
            Purchase.Where(buyer=a, seller=b), status=["prescribed_not"]
        )

    @rule(types=[trade])
    def said_to_have_bought_from(a: Var[Person], b: Var[Person]):
        return SaidToHaveBoughtFrom.Derive(buyer=a, seller=b).when(
            Purchase.Where(buyer=a, seller=b), status=list(STATUSES)
        )

    initialise()
    return {
        "Person": Person,
        "Factoid": Factoid,
        "BoughtFrom": BoughtFrom,
        "DidNotBuyFrom": DidNotBuyFrom,
        "ForbiddenToBuyFrom": ForbiddenToBuyFrom,
        "SaidToHaveBoughtFrom": SaidToHaveBoughtFrom,
    }


def inside(space, *contents):
    return {"type": space, "contents": list(contents)}


@no_type_check
async def world(clear_database):
    m = models()
    seller = await m["Person"].Create(label="Seller").save()
    people = {}

    async def purchase(name: str):
        if name not in people:
            people[name] = await m["Person"].Create(label=name).save()
        return {
            "type": "Purchase",
            "label": f"purchase by {name}",
            "buyer": {"type": "Person", "id": people[name].id},
            "seller": {"type": "Person", "id": seller.id},
        }

    return m, purchase, people


async def by_buyer(model, where=None) -> dict:
    """Each fact by its buyer: its status and statuses"""
    page = await read.list_facts(model, where, page_size=100)
    return {v.buyer.label: (v.status, tuple(v.statuses)) for v in page["results"]}


@no_type_check
async def test_a_rule_takes_what_was_denied_or_forbidden_for_a_class_of_its_own(
    clear_database,
):
    m, purchase, _ = await world(clear_database)
    await (
        m["Factoid"]
        .Create(
            label="F",
            statements=[
                await purchase("bought"),
                inside("Not", await purchase("denied")),
                inside("Ordered", inside("Not", await purchase("forbidden"))),
                inside("Reported", inside("Not", await purchase("reported not"))),
            ],
        )
        .save()
    )
    await run_pending_derivations()
    assert await by_buyer(m["BoughtFrom"]) == {"bought": ("asserted", ("asserted",))}
    assert await by_buyer(m["DidNotBuyFrom"]) == {"denied": ("denied", ("denied",))}
    # (a forbidding is summed up as a denial is: it speaks against the purchase)
    assert await by_buyer(m["ForbiddenToBuyFrom"]) == {
        "forbidden": ("denied", ("prescribed_not",))
    }
    (denied,) = (await read.list_facts(m["DidNotBuyFrom"]))["results"]
    # (what the spaces say is kept: it is not asserted)
    assert denied.context_labels == ["Not"] and denied.qualified_only
    why = await read.get_fact(m["DidNotBuyFrom"], denied.id)
    assert [j.status for j in why.justifications] == ["denied"]
    assert [j.context.model_dump()["patterns"] for j in why.justifications]


# (each buyer's purchases, by where they are, and what the fact is summed up as)
MIXED = {
    "asserted twice": ([None, "Known"], "asserted"),
    "asserted and said nothing of": ([None, "NotKnown"], "asserted"),
    "contested": ([None, "Not"], "contested"),
    "forbidden and done": (["Ordered", "OrderedNot", None], "contested"),
    "reported and denied": (["Reported", "Not"], "reported"),
    "ordered and forbidden": (["Ordered", "OrderedNot"], "prescribed"),
    "denied every way": (["Not", "ReportedNot", "OrderedNot"], "denied"),
    "denied and said nothing of": (["Not", "NotKnown"], "nothing"),
}


def placed(where, statement):
    return {
        None: statement,
        "Known": inside("Known", statement),
        "Not": inside("Not", statement),
        "NotKnown": inside("Not", inside("Known", statement)),
        "Reported": inside("Reported", statement),
        "ReportedNot": inside("Reported", inside("Not", statement)),
        "Ordered": inside("Ordered", statement),
        "OrderedNot": inside("Ordered", inside("Not", statement)),
    }[where]


async def mixed(m, purchase):
    statements = [
        placed(where, await purchase(buyer))
        for buyer, (places, _) in MIXED.items()
        for where in places
    ]
    return await m["Factoid"].Create(label="F", statements=statements).save()


@no_type_check
async def test_a_fact_is_summed_up_in_the_database_as_status_summed_says(
    db_driver, clear_database
):
    m, purchase, _ = await world(clear_database)
    await mixed(m, purchase)
    await run_pending_derivations()
    rows = run(
        db_driver,
        "MATCH (d:PGDerived:SaidToHaveBoughtFrom)<-[:justifies]-(j:PGJustification) "
        "MATCH (d)-[:buyer]->(p) "
        "RETURN p.label AS buyer, d.status AS status, d.statuses AS statuses, collect(j.status) AS js",
    )
    assert len(rows) == len(MIXED)
    for row in rows:
        assert row["status"] == summed(row["js"]), row
        assert list(row["statuses"]) == ordered(row["js"]), row
        assert row["status"] == MIXED[row["buyer"]][1], row
    # (the view says the same)
    assert {
        buyer: status
        for buyer, (status, _) in (await by_buyer(m["SaidToHaveBoughtFrom"])).items()
    } == {buyer: fact for buyer, (_, fact) in MIXED.items()}
    # (each justification has its status as a property, and in its context)
    import json

    for row in run(
        db_driver,
        "MATCH (j:PGJustification) RETURN j.status AS status, j.context AS context",
    ):
        assert row["status"] in STATUSES
        assert json.loads(row["context"])["status"] == row["status"]


@no_type_check
async def test_a_justification_found_again_in_a_space_changes_its_status_and_its_fact(
    db_driver, clear_database
):
    m, purchase, _ = await world(clear_database)
    factoid = (
        await m["Factoid"].Create(label="F", statements=[await purchase("A")]).save()
    )
    await run_pending_derivations()
    assert await by_buyer(m["SaidToHaveBoughtFrom"]) == {
        "A": ("asserted", ("asserted",))
    }
    (before,) = run(
        db_driver,
        "MATCH (j:PGJustification {rule: 'said_to_have_bought_from'}) RETURN j.key AS key",
    )
    # (the same purchase, its id kept, now saying that it was not A who bought: the same justification, found again
    # with a new context)
    stored = await m["Factoid"].get(factoid.id)
    (statement,) = [s.model_dump(mode="json") for s in stored.statements]
    statement["buyer"] = inside("Not", statement["buyer"])
    await m["Factoid"].Update(id=factoid.id, label="F", statements=[statement]).save()
    await run_pending_derivations()
    (after,) = run(
        db_driver,
        "MATCH (j:PGJustification {rule: 'said_to_have_bought_from'}) RETURN j.key AS key, j.status AS status",
    )
    assert after["key"] == before["key"] and after["status"] == "denied"
    assert await by_buyer(m["SaidToHaveBoughtFrom"]) == {"A": ("denied", ("denied",))}
    assert await by_buyer(m["BoughtFrom"]) == {}


@no_type_check
async def test_the_readers_filter_by_the_status_and_give_it(clear_database):
    m, purchase, people = await world(clear_database)
    await mixed(m, purchase)
    await run_pending_derivations()
    Said = m["SaidToHaveBoughtFrom"]
    assert set(await by_buyer(Said, Said.Where(status="contested"))) == {
        "contested",
        "forbidden and done",
    }
    assert set(await by_buyer(Said, Said.Where(status="denied", plain=False))) == {
        "denied every way"
    }

    # (the graph of a type, with each edge's status; and as GraphML)
    edges = await read.graph("trade")
    assert {e["source"]["label"]: e["status"] for e in edges} == {
        buyer: fact for buyer, (_, fact) in MIXED.items()
    }
    assert '<data key="e_status">contested</data>' in graphml(edges, "trade")

    # (what is derived about a person, as the view of an entity has it)
    about = await read.derived_of_entity(m["Person"], people["contested"].id)
    (item,) = about["SaidToHaveBoughtFrom"]["items"]
    assert item["status"] == "contested" and item["statuses"] == [
        "asserted",
        "denied",
    ]

    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/derived/SaidToHaveBoughtFrom", params={"status": "prescribed"}
        )
        assert response.status_code == 200, response.text
        (fact,) = response.json()["results"]
        assert fact["buyer"]["label"] == "ordered and forbidden"
        assert fact["status"] == "prescribed"
        assert fact["statuses"] == ["prescribed", "prescribed_not"]
        one = await client.get(f"/api/derived/SaidToHaveBoughtFrom/{fact['id']}")
        assert sorted(j["status"] for j in one.json()["justifications"]) == [
            "prescribed",
            "prescribed_not",
        ]
        # (a status a fact is never summed up as)
        wrong = await client.get(
            "/api/derived/SaidToHaveBoughtFrom", params={"status": "reported_not"}
        )
        assert wrong.status_code == 422
        graph = await client.get("/api/derived/graph/trade")
        assert {e["status"] for e in graph.json()["edges"]} == {
            fact for _, fact in MIXED.values()
        }
