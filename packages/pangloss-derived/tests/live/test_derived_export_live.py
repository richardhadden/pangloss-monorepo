"""Derived edges exported, on the backend under test: GraphML from the API, every edge with what it rests on
(`read.edges_with_evidence`), and the part of an RDF dump that `pangloss_rdf` writes when asked (`--include-derived`),
which says of each edge only what the reader of the dump may know"""

import importlib
import xml.etree.ElementTree as ET
from typing import Annotated, no_type_check

import httpx2 as httpx
import pytest
from pangloss_api import create_app
from pangloss_models import Document, Entity, SemanticSpace, initialise
from pangloss_rdf import RDFMeta, item_uri
from pangloss_rdf.dump import dump
from pangloss_rdf.vocabulary import (
    RDF_OBJECT,
    RDF_PREDICATE,
    RDF_SUBJECT,
    RDF_TYPE,
    pgo,
)
from pangloss_testing.live import run
from pangloss_users import see_unpublished
from rdflib import Dataset, URIRef

from pangloss_derived import (
    DerivedEdge,
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

NS = {"g": "http://graphml.graphdrawing.org/xmlns"}
ONTOLOGY = "http://test.com/ontology/"


@no_type_check
def models():
    class Negative[T](SemanticSpace[T]):
        pass

    class Person(Entity):
        pass

    class Group(Entity):
        pass

    class MemberOf(Document):
        member: Person
        group: Group

    class Gift(Document):
        given_by: Person
        given_to: Person
        year: int
        amount: int

    class Factoid(Document):
        statements: list[MemberOf | Gift | Negative[MemberOf | Gift]]

    # (a class that is not exported as RDF, which says things all the same)
    class Rumour(Document):
        _rdf_meta = RDFMeta(exclude=True)
        statements: list[MemberOf | Gift]

    social = RuleType("social", "Who had to do with whom")

    class SameGroup(DerivedEdge):
        """Members of the same group"""

        _meta = DerivedEdge.Meta(symmetric=True)
        first: Annotated[Person, SymmetricLabel("member")]
        second: Annotated[Person, SymmetricLabel("member")]
        group: Group

    class GaveTo(DerivedEdge):
        giver: Annotated[Person, Subject()]
        receiver: Annotated[Person, Object(reverse_name="received_from")]
        year: int
        amount: Annotated[int, PerJustification()]

    @rule(types=[social])
    def same_group(a: Var[Person], b: Var[Person], g: Var[Group]):
        return SameGroup.Derive(first=a, second=b, group=g).when(
            MemberOf.Where(member=a, group=g), MemberOf.Where(member=b, group=g)
        )

    @rule(types=[social])
    def gave_to(a: Var[Person], b: Var[Person], y: Var[int], n: Var[int]):
        return GaveTo.Derive(giver=a, receiver=b, year=y, amount=n).when(
            Gift.Where(given_by=a, given_to=b, year=y, amount=n)
        )

    initialise()
    # (the part of a dump is found by the app's name, once: and reads the classes declared now)
    importlib.import_module("pangloss_derived.rdf")
    return locals()


async def setup(clear_database):
    m = models()
    n = {}
    for name in "ABCD":
        n[name] = await m["Person"].Create(label=name).save()
    n["G"] = await m["Group"].Create(label="G").save()
    return m, n


def member(who, group):
    return {
        "type": "MemberOf",
        "label": "m",
        "member": {"type": "Person", "id": who.id},
        "group": {"type": "Group", "id": group.id},
    }


def gift(giver, receiver, year=1500, amount=10):
    return {
        "type": "Gift",
        "label": "g",
        "given_by": {"type": "Person", "id": giver.id},
        "given_to": {"type": "Person", "id": receiver.id},
        "year": year,
        "amount": amount,
    }


def negative(*statements):
    return {"type": "Negative", "contents": list(statements)}


async def says(m, label, *statements, kind="Factoid"):
    return await m[kind].Create(label=label, statements=list(statements)).save()


def unpublish(db_driver, document):
    # (as `pangloss-review` leaves a document that is not checked)
    run(
        db_driver,
        "MATCH (h:HeadNode {id: $id}) SET h.published = false",
        id=str(document.id),
    )


async def all_edges(model, page_size=read.EXPORT_PAGE):
    found = []
    async for page in read.edges_with_evidence(model, page_size):
        assert 0 < len(page) <= page_size
        found += page
    return found


@pytest.fixture
def reader():
    """Reads as someone who is not logged in, for as long as it is asked to"""
    before = see_unpublished.get()

    def read_as(logged_in: bool):
        see_unpublished.set(logged_in)

    yield read_as
    see_unpublished.set(before)


# ---------------------------------------------------------------------------
# GraphML from the API
# ---------------------------------------------------------------------------


@no_type_check
async def test_the_graph_of_a_type_as_graphml(clear_database):
    m, n = await setup(clear_database)
    await says(m, "F1", member(n["A"], n["G"]), member(n["B"], n["G"]))
    await says(m, "F2", gift(n["A"], n["C"], 1500, 5), gift(n["A"], n["C"], 1500, 6))
    await says(m, "F3", negative(gift(n["C"], n["D"], 1501)))
    await run_pending_derivations()
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/derived/graph/social", params={"format": "graphml"}
        )
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("application/graphml+xml")
        assert 'filename="social.graphml"' in response.headers["content-disposition"]
        root = ET.fromstring(response.text)
        graph = root.find("g:graph", NS)
        # (one symmetric class and one that is not: directed, the symmetric edges saying they are not)
        assert graph.get("edgedefault") == "directed"
        nodes = {
            node.get("id"): node.find("g:data[@key='n_label']", NS).text
            for node in graph.findall("g:node", NS)
        }
        assert nodes == {str(n[name].id): name for name in "ABCD"}
        edges = {}
        for edge in graph.findall("g:edge", NS):
            values = {d.get("key"): d.text or "" for d in edge.findall("g:data", NS)}
            ends = (nodes[edge.get("source")], nodes[edge.get("target")])
            edges[(values["e_class"], *ends)] = (edge.get("directed"), values)
        assert set(edges) == {
            ("SameGroup", "A", "B"),
            ("GaveTo", "A", "C"),
            ("GaveTo", "C", "D"),
        } or set(edges) == {
            ("SameGroup", "B", "A"),
            ("GaveTo", "A", "C"),
            ("GaveTo", "C", "D"),
        }
        same = next(v for k, v in edges.items() if k[0] == "SameGroup")
        assert same[0] == "false"
        assert same[1]["q_group"] == "G" and same[1]["q_group_id"] == str(n["G"].id)
        twice = edges[("GaveTo", "A", "C")]
        assert twice[0] is None
        assert (twice[1]["e_weight"], twice[1]["q_year"], twice[1]["e_plain"]) == (
            "2",
            "1500",
            "true",
        )
        doubted = edges[("GaveTo", "C", "D")][1]
        assert (doubted["e_plain"], doubted["e_context"]) == ("false", "Negative")

        # (only the plain ones; and the JSON is as it was)
        plain = await client.get(
            "/api/derived/graph/social", params={"format": "graphml", "plain": "true"}
        )
        assert (
            len(ET.fromstring(plain.text).find("g:graph", NS).findall("g:edge", NS))
            == 2
        )
        as_json = await client.get("/api/derived/graph/social")
        assert as_json.json()["count"] == 3
        assert (
            await client.get("/api/derived/graph/social", params={"format": "json"})
        ).json() == as_json.json()
        wrong = await client.get("/api/derived/graph/social", params={"format": "csv"})
        assert wrong.status_code == 422
        missing = await client.get(
            "/api/derived/graph/nothing", params={"format": "graphml"}
        )
        assert missing.status_code == 404


# ---------------------------------------------------------------------------
# Every edge, with what it rests on
# ---------------------------------------------------------------------------


@no_type_check
async def test_every_edge_once_whatever_the_size_of_a_page(clear_database):
    m, n = await setup(clear_database)
    people = [await m["Person"].Create(label=f"P{i}").save() for i in range(7)]
    await says(m, "F1", *[gift(n["A"], p, 1500) for p in people])
    await run_pending_derivations()
    whole = await all_edges(m["GaveTo"])
    assert len(whole) == 7
    for size in (1, 2, 3, 7, 8):
        paged = await all_edges(m["GaveTo"], size)
        assert [e["view"].id for e in paged] == [e["view"].id for e in whole]
    assert await all_edges(m["SameGroup"]) == []


@no_type_check
async def test_what_an_edge_rests_on_is_what_the_reader_sees(
    clear_database, db_driver, reader
):
    m, n = await setup(clear_database)
    f1 = await says(m, "F1", gift(n["A"], n["B"], 1500, 1))
    f2 = await says(m, "F2", negative(gift(n["A"], n["B"], 1500, 2)))
    f3 = await says(m, "F3", gift(n["C"], n["D"], 1500, 3))
    await run_pending_derivations()
    unpublish(db_driver, f1)
    unpublish(db_driver, f3)

    def summary(found):
        return sorted(
            (
                e["view"].giver.label,
                e["view"].receiver.label,
                e["justifications"],
                e["plain"],
                tuple(e["context_labels"]),
                tuple(sorted(str(h["id"]) for h in e["evidence"])),
            )
            for e in found
        )

    reader(True)
    assert summary(await all_edges(m["GaveTo"])) == [
        ("A", "B", 2, True, ("Negative",), tuple(sorted([str(f1.id), str(f2.id)]))),
        ("C", "D", 1, True, (), (str(f3.id),)),
    ]
    # (a reader sees the gift from A to B only as what a negated statement says; the other not at all. The stored
    # edge still says it is plain: that is of all its justifications)
    reader(False)
    assert summary(await all_edges(m["GaveTo"])) == [
        ("A", "B", 1, False, ("Negative",), (str(f2.id),)),
    ]
    (view,) = (await read.list_facts(m["GaveTo"]))["results"]
    assert view.plain and view.justification_count == 2


# ---------------------------------------------------------------------------
# The dump of `pangloss_rdf`
# ---------------------------------------------------------------------------


async def dumped(path, **options):
    before = see_unpublished.get()
    try:
        result = await dump(path, **options)
    finally:
        see_unpublished.set(before)
    data = Dataset(default_union=True)
    data.parse(data=path.read_text(), format="nquads")
    return result, data


def objects(data, subject, predicate):
    return sorted(
        str(o) for o in data.objects(URIRef(str(subject)), URIRef(str(predicate)))
    )


def edge_nodes(data, kind):
    return sorted(
        str(s)
        for s in data.subjects(URIRef(RDF_TYPE.value), URIRef(f"{ONTOLOGY}{kind}"))
    )


@no_type_check
async def test_a_dump_has_the_derived_edges_only_when_asked(clear_database, tmp_path):
    m, n = await setup(clear_database)
    f1 = await says(m, "F1", member(n["A"], n["G"]))
    f2 = await says(m, "F2", member(n["B"], n["G"]))
    await says(m, "F3", gift(n["A"], n["B"], 1500, 7))
    await run_pending_derivations()
    plain, without = await dumped(tmp_path / "plain.nq")
    assert edge_nodes(without, "SameGroup") == []
    assert not any("/derived/" in str(s) for s, _, _, _ in without.quads())
    result, data = await dumped(tmp_path / "with.nq", include=["derived"])
    # (two items more, and nothing of the rest changed)
    assert result.items == plain.items + 2
    assert {q for q in without.quads() if "issued" not in str(q[1])} <= {
        q for q in data.quads() if "issued" not in str(q[1])
    }
    a, b, g = (item_uri(type(n[k])._owner, n[k].id) for k in "ABG")
    (same,) = edge_nodes(data, "SameGroup")
    assert same.startswith("http://test.com/derived/SameGroup/")
    predicate = f"{ONTOLOGY}sameGroup"
    ends = objects(data, same, RDF_SUBJECT) + objects(data, same, RDF_OBJECT)
    assert sorted(ends) == sorted([str(a), str(b)])
    assert objects(data, same, RDF_PREDICATE) == [predicate]
    assert str(pgo("DerivedEdge")) in objects(data, same, RDF_TYPE)
    assert objects(data, same, f"{ONTOLOGY}SameGroup.group") == [str(g)]
    assert objects(data, same, pgo("plain")) == ["true"]
    assert objects(data, same, pgo("justificationCount")) == ["1"]
    assert objects(data, same, pgo("context")) == []
    factoid = type(f1)._owner
    assert objects(data, same, pgo("justifiedBy")) == sorted(
        str(item_uri(factoid, f.id)) for f in (f1, f2)
    )
    # (the direct triple, from the subject to the object as stored; in the graph of the edge)
    subject, object_ = (
        objects(data, same, RDF_SUBJECT)[0],
        objects(data, same, RDF_OBJECT)[0],
    )
    assert objects(data, subject, predicate) == [object_]
    assert {
        str(graph)
        for s, p, o, graph in data.quads(
            (URIRef(subject), URIRef(predicate), None, None)
        )
    } == {same}
    # (the asymmetric one: from the giver, with its qualifier; the amount of a justification is not written)
    (gave,) = edge_nodes(data, "GaveTo")
    assert objects(data, gave, RDF_SUBJECT) == [str(a)]
    assert objects(data, gave, RDF_OBJECT) == [str(b)]
    assert objects(data, gave, f"{ONTOLOGY}GaveTo.year") == ["1500"]
    assert objects(data, a, f"{ONTOLOGY}gaveTo") == [str(b)]
    assert not any(
        "amount" in str(p)
        for s, p, o, _ in data.quads((URIRef(gave), None, None, None))
    )


@no_type_check
async def test_a_dump_says_of_an_edge_what_its_reader_may_know(
    clear_database, db_driver, tmp_path
):
    m, n = await setup(clear_database)
    f1 = await says(m, "F1", gift(n["A"], n["B"], 1500, 1))
    f2 = await says(m, "F2", negative(gift(n["A"], n["B"], 1500, 2)))
    await says(m, "F3", gift(n["C"], n["D"], 1500, 3))
    f3 = (await m["Factoid"].list()).results
    await run_pending_derivations()
    unpublish(db_driver, f1)
    unpublish(db_driver, next(f for f in f3 if f.label == "F3"))
    a, b, c, d = (item_uri(m["Person"], n[k].id) for k in "ABCD")
    gave_to = f"{ONTOLOGY}gaveTo"
    factoid = m["Factoid"]
    # (for a reader who is not logged in: the gift from A to B only as a negated statement says it, so with no direct
    # triple; the gift from C to D not at all)
    _, public = await dumped(tmp_path / "public.nq", include=["derived"])
    (gave,) = edge_nodes(public, "GaveTo")
    assert objects(public, gave, RDF_SUBJECT) == [str(a)]
    assert objects(public, gave, pgo("plain")) == ["false"]
    assert objects(public, gave, pgo("context")) == ["Negative"]
    assert objects(public, gave, pgo("justificationCount")) == ["1"]
    assert objects(public, gave, pgo("justifiedBy")) == [str(item_uri(factoid, f2.id))]
    assert objects(public, a, gave_to) == [] and objects(public, c, gave_to) == []
    # (with what is not published: both, and the first is plain)
    _, whole = await dumped(
        tmp_path / "whole.nq", include=["derived"], include_unpublished=True
    )
    assert len(edge_nodes(whole, "GaveTo")) == 2
    assert objects(whole, a, gave_to) == [str(b)]
    assert objects(whole, c, gave_to) == [str(d)]
    first = next(
        e
        for e in edge_nodes(whole, "GaveTo")
        if objects(whole, e, RDF_SUBJECT) == [str(a)]
    )
    assert objects(whole, first, pgo("justificationCount")) == ["2"]
    assert objects(whole, first, pgo("plain")) == ["true"]
    assert objects(whole, first, pgo("context")) == ["Negative"]
    assert len(objects(whole, first, pgo("justifiedBy"))) == 2


@no_type_check
async def test_a_document_of_a_class_that_is_not_exported_is_not_named(
    clear_database, tmp_path
):
    m, n = await setup(clear_database)
    await says(m, "R", gift(n["A"], n["B"], 1500, 1), kind="Rumour")
    f = await says(m, "F", gift(n["A"], n["B"], 1500, 2))
    await run_pending_derivations()
    _, data = await dumped(tmp_path / "data.nq", include=["derived"])
    (gave,) = edge_nodes(data, "GaveTo")
    # (it rests on both, and says so; only the one that is exported is named)
    assert objects(data, gave, pgo("justificationCount")) == ["2"]
    assert objects(data, gave, pgo("justifiedBy")) == [
        str(item_uri(m["Factoid"], f.id))
    ]
    assert "Rumour" not in (tmp_path / "data.nq").read_text()


@no_type_check
async def test_the_other_formats_of_a_dump_have_the_edges_too(clear_database, tmp_path):
    m, n = await setup(clear_database)
    await says(m, "F1", member(n["A"], n["G"]), member(n["B"], n["G"]))
    await run_pending_derivations()
    before = see_unpublished.get()
    try:
        for format in ("trig", "ttl"):
            path = tmp_path / f"data.{format}"
            await dump(path, format, include=["derived"])
            data = Dataset(default_union=True)
            data.parse(
                data=path.read_text(), format="trig" if format == "trig" else "turtle"
            )
            assert len(edge_nodes(data, "SameGroup")) == 1
        compressed = tmp_path / "data.nq.gz"
        result = await dump(compressed, include=["derived"])
        # (four people, a group, a factoid, and the edge)
        assert result.items == 7
        with pytest.raises(ValueError, match="no part of a dump called 'other'"):
            await dump(tmp_path / "no.nq", include=["other"])
        assert not (tmp_path / "no.nq").exists()
    finally:
        see_unpublished.set(before)
