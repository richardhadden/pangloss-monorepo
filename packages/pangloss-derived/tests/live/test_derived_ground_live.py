"""The ground of a head class in derivation, on the backend under test (`pangloss_derived.status`;
implementation_docs/spaces-and-comparison-plan.md, step 4.5): each part walked from its ground, so that what a rumour
says is reported; and the standing of a justification and of a fact (`"record"` or `"claim"`), stored, summed up in
Cypher as `status.summed_standing` says, and given by the readers."""

from typing import Annotated, no_type_check

import httpx2 as httpx
import pytest
from pangloss_api import create_app
from pangloss_derived import DerivedEdge, Object, RuleType, Subject, Var, read, rule
from pangloss_derived.export import graphml
from pangloss_derived.status import summed_standing
from pangloss_derived.worker import run_pending_derivations
from pangloss_models import Document, Entity, Ground, initialise
from pangloss_testing.live import run

pytestmark = pytest.mark.asyncio(loop_scope="session")


@no_type_check
def models():
    class Source(Entity):
        pass

    class Person(Entity):
        pass

    class Place(Entity):
        within: list[Place]

    class Purchase(Document):
        buyer: Person
        seller: Person

    # (a subclass with a ground of its own: what it holds itself, as a head, is neither asserted nor denied)
    class RumouredPurchase(Purchase):
        _meta = Document.Meta(ground=Ground(veridical=0, degree="possible"))

    class Factoid(Document):
        _meta = Document.Meta(ground=Ground(by="source"))
        source: Source
        statements: list[Purchase]

    class Rumour(Document):
        _meta = Document.Meta(ground=Ground(veridical=0, degree="possible"))
        statements: list[Purchase]

    # (a document whose ground is the record: what claims are held against)
    class Register(Document):
        _meta = Document.Meta(ground=Ground(standing="record"))
        statements: list[Purchase]

    class BoughtFrom(DerivedEdge):
        """Who bought from whom"""

        buyer: Annotated[Person, Subject()]
        seller: Annotated[Person, Object()]

    class InRegion(DerivedEdge):
        """A place within a place within a place"""

        place: Annotated[Place, Subject()]
        region: Annotated[Place, Object()]

    trade = RuleType("trade", "Who traded with whom")

    @rule(types=[trade])
    def bought_from(a: Var[Person], b: Var[Person]):
        return BoughtFrom.Derive(buyer=a, seller=b).when(
            Purchase.Where(buyer=a, seller=b)
        )

    @rule
    def in_region(a: Var[Place], b: Var[Place], c: Var[Place]):
        return InRegion.Derive(place=a, region=c).when(
            Place.Where(is_=a, within=b), Place.Where(is_=b, within=c)
        )

    initialise()
    return locals()


@no_type_check
async def world(m):
    source = await m["Source"].Create(label="A chronicle").save()
    seller = await m["Person"].Create(label="Seller").save()
    people = {}

    async def purchase(name: str, type: str = "Purchase"):
        if name not in people:
            people[name] = await m["Person"].Create(label=name).save()
        return {
            "type": type,
            "label": f"purchase by {name}",
            "buyer": {"type": "Person", "id": people[name].id},
            "seller": {"type": "Person", "id": seller.id},
        }

    await (
        m["Factoid"]
        .Create(
            label="F",
            source={"type": "Source", "id": source.id},
            statements=[await purchase("claimed"), await purchase("both")],
        )
        .save()
    )
    await (
        m["Register"]
        .Create(
            label="R", statements=[await purchase("recorded"), await purchase("both")]
        )
        .save()
    )
    await (
        m["Rumour"].Create(label="Talk", statements=[await purchase("rumoured")]).save()
    )
    # (purchases that are heads themselves: of the class matched, and of a subclass with its own ground)
    await m["Purchase"].Create(**await purchase("head")).save()
    await (
        m["RumouredPurchase"]
        .Create(**await purchase("rumoured head", "RumouredPurchase"))
        .save()
    )

    places = {}
    for name, within in (
        ("Europe", []),
        ("France", ["Europe"]),
        ("Paris", ["France"]),
    ):
        places[name] = (
            await m["Place"]
            .Create(
                label=name,
                within=[{"type": "Place", "id": places[w].id} for w in within],
            )
            .save()
        )
    await run_pending_derivations()
    return people, places


@no_type_check
async def test_a_fact_has_the_standing_of_its_justifications_and_each_part_its_ground(
    db_driver, clear_database
):
    m = models()
    await world(m)
    page = await read.list_facts(m["BoughtFrom"], page_size=100)
    assert {
        v.buyer.label: (v.status, v.standing, tuple(v.statuses))
        for v in page["results"]
    } == {
        "claimed": ("asserted", "claim", ("asserted",)),
        "recorded": ("asserted", "record", ("asserted",)),
        # (one justification of each: a claim)
        "both": ("asserted", "claim", ("asserted",)),
        # (a statement directly in a rumour, whose ground is neither asserted nor denied)
        "rumoured": ("reported", "claim", ("reported",)),
        # (a head matched itself: by its class as stored, a document's ground by default, and the subclass's own)
        "head": ("asserted", "claim", ("asserted",)),
        "rumoured head": ("reported", "claim", ("reported",)),
    }
    # (what rests on a rumour is never plain: the rumour's class qualifies it, as a space passed through would)
    assert {
        v.buyer.label: (v.plain, v.context_labels)
        for v in page["results"]
        if v.buyer.label in ("claimed", "rumoured", "rumoured head")
    } == {
        "claimed": (True, []),
        "rumoured": (False, ["Rumour"]),
        "rumoured head": (False, ["RumouredPurchase"]),
    }
    # (an entity's own relations alone: the record)
    regions = await read.list_facts(m["InRegion"], page_size=100)
    assert [
        (v.place.label, v.region.label, v.status, v.standing)
        for v in regions["results"]
    ] == [("Paris", "Europe", "asserted", "record")]


@no_type_check
async def test_a_fact_s_standing_is_summed_up_in_the_database_as_summed_standing_says(
    db_driver, clear_database
):
    m = models()
    await world(m)
    rows = run(
        db_driver,
        "MATCH (d:PGDerived)<-[:justifies]-(j:PGJustification) "
        "RETURN d.key AS key, d.standing AS standing, collect(j.standing) AS js",
    )
    assert len(rows) == 7
    assert {row["standing"] for row in rows} == {"claim", "record"}
    for row in rows:
        assert row["standing"] == summed_standing(row["js"]), row
    assert sorted(len(row["js"]) for row in rows) == [1, 1, 1, 1, 1, 1, 2]
    # (each justification has its standing as a property, and in its context)
    import json

    for row in run(
        db_driver,
        "MATCH (j:PGJustification) RETURN j.standing AS standing, j.context AS context",
    ):
        assert row["standing"] in ("claim", "record")
        assert json.loads(row["context"])["standing"] == row["standing"]


@no_type_check
async def test_the_readers_give_the_standing(clear_database):
    m = models()
    people, places = await world(m)
    about = await read.derived_of_entity(m["Person"], people["recorded"].id)
    (item,) = about["BoughtFrom"]["items"]
    assert item["standing"] == "record"
    about = await read.derived_of_entity(m["Place"], places["Paris"].id)
    (item,) = about["InRegion"]["items"]
    assert item["standing"] == "record"

    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/derived/BoughtFrom", params={"buyer": str(people["both"].id)}
        )
        assert response.status_code == 200, response.text
        (fact,) = response.json()["results"]
        assert fact["standing"] == "claim"
        one = await client.get(f"/api/derived/BoughtFrom/{fact['id']}")
        assert one.status_code == 200, one.text
        assert one.json()["standing"] == "claim"
        # (why: each justification, a claim of the factoid and the record of the register)
        assert sorted(
            (j["evidence"][0]["type"], j["standing"])
            for j in one.json()["justifications"]
        ) == [("Factoid", "claim"), ("Register", "record")]

    # (the graph and the export sum up what the reader sees)
    edges = await read.graph("trade")
    assert {e["source"]["label"]: e["standing"] for e in edges}["recorded"] == "record"
    assert '<data key="e_standing">record</data>' in graphml(edges, "trade")
    found = [
        item
        for page in [p async for p in read.edges_with_evidence(m["BoughtFrom"])]
        for item in page
    ]
    assert {f["view"].buyer.label: f["standing"] for f in found} == {
        "claimed": "claim",
        "recorded": "record",
        "both": "claim",
        "rumoured": "claim",
        "head": "claim",
        "rumoured head": "claim",
    }
