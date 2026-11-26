"""The exports of derived edges with no database: GraphML made from the edges of a graph, and the terms of the
ontology that `pangloss_rdf` writes for the derived classes"""

import importlib
import xml.etree.ElementTree as ET
from typing import Annotated, no_type_check

import pytest
from pangloss_models import Document, Entity, initialise
from pangloss_models.exceptions import PanglossMetaError

from pangloss_derived import (
    DerivedEdge,
    Object,
    PerJustification,
    Subject,
    SymmetricLabel,
)
from pangloss_derived.export import graphml, graphml_type, qualifier_keys

NS = {"g": "http://graphml.graphdrawing.org/xmlns"}


def ref(id, label, type="Person"):
    return {"id": id, "label": label, "type": type}


def edge(id, source, target, **more):
    return {
        "id": id,
        "class": "GaveTo",
        "source": source,
        "target": target,
        "symmetric": False,
        "attributes": {},
        "justifications": 1,
        "weight": 1,
        "plain": True,
        "context_labels": [],
        "status": "asserted",
        "standing": "claim",
        **more,
    }


def parsed(edges, name="social"):
    root = ET.fromstring(graphml(edges, name))
    keys = {
        k.get("id"): (k.get("for"), k.get("attr.name"), k.get("attr.type"))
        for k in root.findall("g:key", NS)
    }
    graph = root.find("g:graph", NS)
    assert graph is not None

    def values(element):
        return {d.get("key"): d.text or "" for d in element.findall("g:data", NS)}

    nodes = {n.get("id"): values(n) for n in graph.findall("g:node", NS)}
    found = [
        (e.get("id"), e.get("source"), e.get("target"), e.get("directed"), values(e))
        for e in graph.findall("g:edge", NS)
    ]
    return graph, keys, nodes, found


def test_graphml_has_each_entity_once_as_a_node_and_each_edge_with_its_values():
    a, b, c = ref("1", "A"), ref("2", "B"), ref("3", "The court", "Group")
    graph, keys, nodes, edges = parsed(
        [
            edge("k1", a, b, justifications=3, weight=3),
            edge(
                "k2",
                a,
                c,
                plain=False,
                context_labels=["Negative", "Hypothetical"],
                status="reported",
                attributes={"year": 1500, "place": ref("9", "Aachen", "Place")},
            ),
        ]
    )
    assert graph.get("id") == "social" and graph.get("edgedefault") == "directed"
    assert nodes == {
        "1": {"n_label": "A", "n_type": "Person"},
        "2": {"n_label": "B", "n_type": "Person"},
        "3": {"n_label": "The court", "n_type": "Group"},
    }
    assert keys["e_weight"] == ("edge", "weight", "int")
    assert keys["e_plain"] == ("edge", "plain", "boolean")
    assert keys["e_status"] == ("edge", "status", "string")
    assert keys["q_year"] == ("edge", "year", "long")
    assert keys["q_place"] == ("edge", "place", "string")
    assert keys["q_place_id"] == ("edge", "place_id", "string")
    assert keys["n_label"] == ("node", "label", "string")
    first, second = edges
    assert first[:4] == ("k1", "1", "2", None)
    assert first[4] == {
        "e_class": "GaveTo",
        "e_weight": "3",
        "e_justifications": "3",
        "e_plain": "true",
        "e_context": "",
        "e_status": "asserted",
        "e_standing": "claim",
    }
    assert second[4] == {
        "e_class": "GaveTo",
        "e_weight": "1",
        "e_justifications": "1",
        "e_plain": "false",
        "e_context": "Negative|Hypothetical",
        "e_status": "reported",
        "e_standing": "claim",
        "q_year": "1500",
        "q_place": "Aachen",
        "q_place_id": "9",
    }
    # (every key an edge or a node uses is declared)
    used = {k for e in edges for k in e[4]} | {k for n in nodes.values() for k in n}
    assert used <= set(keys)


def test_graphml_of_symmetric_edges_is_undirected_and_a_mixed_graph_says_which():
    a, b = ref("1", "A"), ref("2", "B")
    graph, _, _, edges = parsed([edge("k", a, b, symmetric=True, **{"class": "Met"})])
    assert graph.get("edgedefault") == "undirected"
    assert edges[0][3] is None
    graph, _, _, edges = parsed(
        [edge("k1", a, b, symmetric=True), edge("k2", b, a, symmetric=False)]
    )
    assert graph.get("edgedefault") == "directed"
    assert [(e[0], e[3]) for e in edges] == [("k1", "false"), ("k2", None)]


def test_graphml_escapes_what_xml_would_read_as_markup():
    a = ref('1"', 'A & <B> "the bold"')
    b = ref("2", "Ångström's")
    text = graphml(
        [edge("k<1>", a, b, attributes={"note": "x < y & z", "ok": True, "n": None})],
        'the "graph"',
    )
    _, keys, nodes, edges = parsed(
        [edge("k<1>", a, b, attributes={"note": "x < y & z", "ok": True, "n": None})]
    )
    assert "A &amp; &lt;B&gt;" in text and "<B>" not in text
    assert nodes['1"']["n_label"] == 'A & <B> "the bold"'
    assert nodes["2"]["n_label"] == "Ångström's"
    assert edges[0][0] == "k<1>" and edges[0][4]["q_note"] == "x < y & z"
    assert edges[0][4]["q_ok"] == "true" and keys["q_ok"][2] == "boolean"
    # (a qualifier with no value is not written, and has no key)
    assert "q_n" not in keys and "q_n" not in edges[0][4]


def test_graphml_of_nothing_is_an_empty_graph():
    graph, keys, nodes, edges = parsed([])
    assert graph.get("edgedefault") == "undirected"
    assert nodes == {} and edges == []
    assert set(keys) == {
        "n_label",
        "n_type",
        "e_class",
        "e_weight",
        "e_justifications",
        "e_plain",
        "e_context",
        "e_status",
        "e_standing",
    }


def test_a_qualifier_two_classes_use_for_two_types_is_text():
    a, b = ref("1", "A"), ref("2", "B")
    edges = [
        edge("k1", a, b, attributes={"when": 1500, "share": 0.5}),
        edge("k2", a, b, attributes={"when": "about 1500", "share": 0.25}),
    ]
    assert qualifier_keys(edges) == {"q_when": "string", "q_share": "double"}
    _, keys, _, found = parsed(edges)
    assert keys["q_when"][2] == "string"
    assert [e[4]["q_when"] for e in found] == ["1500", "about 1500"]
    assert [graphml_type(v) for v in (True, 1, 1.5, "x")] == [
        "boolean",
        "long",
        "double",
        "string",
    ]


def test_a_node_with_no_label_is_called_by_its_id():
    _, _, nodes, _ = parsed([edge("k", ref("1", None), ref("2", ""))])
    assert nodes["1"]["n_label"] == "1" and nodes["2"]["n_label"] == "2"


# ---------------------------------------------------------------------------
# The ontology of the derived classes (`pangloss_rdf`)
# ---------------------------------------------------------------------------


@pytest.fixture
def rdf(settings):
    """The derived package's part of `pangloss_rdf`, with the settings of these tests"""
    import pangloss_core.settings as core_settings

    before = core_settings.__dict__.get("SETTINGS")
    core_settings.SETTINGS = settings
    module = importlib.import_module("pangloss_derived.rdf")
    yield module
    core_settings.SETTINGS = before


@no_type_check
def declare():
    class Person(Entity):
        pass

    class Group(Entity):
        pass

    class Note(Document):
        about: Person

    class SameGroup(DerivedEdge):
        """Members of the same group"""

        _meta = DerivedEdge.Meta(symmetric=True)
        first: Annotated[Person, SymmetricLabel("member")]
        second: Annotated[Person, SymmetricLabel("member")]
        group: Group

    class GaveTo(DerivedEdge):
        giver: Annotated[Person, Subject()]
        receiver: Annotated[Group, Object(reverse_name="received_from")]
        year: int
        likelihood: Annotated[int, PerJustification()]

    initialise(bind_database=False)
    return locals()


@no_type_check
def test_the_ontology_has_a_property_for_each_derived_class(rdf):
    from pangloss_rdf.vocabulary import RDF_TYPE, RDFS_LABEL, owl, pgo, rdfs

    m = declare()
    quads = list(rdf.derived_ontology())
    triples = {
        (
            q.subject.value,
            q.predicate.value,
            getattr(q.object, "value", None) or q.object.lexical,
        )
        for q in quads
    }
    base = "http://test.com/ontology/"

    def has(s, p, o):
        return (s, p.value, o) in triples

    core = pgo("DerivedEdge").value
    assert has(core, RDF_TYPE, owl("Class").value)
    assert has(core, rdfs("subClassOf"), pgo("Edge").value)
    assert has(pgo("justifiedBy").value, RDF_TYPE, owl("ObjectProperty").value)
    # (a symmetric class: a symmetric property between people, with its description)
    same = f"{base}sameGroup"
    assert rdf.predicate_uri(m["SameGroup"]).value == same
    assert has(same, RDF_TYPE, owl("ObjectProperty").value)
    assert has(same, RDF_TYPE, owl("SymmetricProperty").value)
    assert has(same, RDFS_LABEL, "Same group")
    assert has(same, rdfs("comment"), "Members of the same group")
    assert has(same, rdfs("domain"), f"{base}Person")
    assert has(same, rdfs("range"), f"{base}Person")
    assert rdf.reverse_uri(m["SameGroup"]) is None
    # (an asymmetric one: its inverse by the reverse name, and not symmetric)
    gave = f"{base}gaveTo"
    assert not has(gave, RDF_TYPE, owl("SymmetricProperty").value)
    assert has(gave, rdfs("domain"), f"{base}Person")
    assert has(gave, rdfs("range"), f"{base}Group")
    assert has(f"{base}receivedFrom", owl("inverseOf"), gave)
    assert has(f"{base}receivedFrom", RDFS_LABEL, "received from")
    # (the class of its statements, and its qualifiers: an entity and a value; not a value of a justification)
    assert has(f"{base}GaveTo", rdfs("subClassOf"), core)
    assert has(f"{base}GaveTo.year", RDF_TYPE, owl("DatatypeProperty").value)
    assert has(f"{base}GaveTo.year", rdfs("domain"), f"{base}GaveTo")
    assert has(f"{base}SameGroup.group", RDF_TYPE, owl("ObjectProperty").value)
    assert has(f"{base}SameGroup.group", rdfs("range"), f"{base}Group")
    assert not any("likelihood" in s for s, _, _ in triples)


@no_type_check
def test_the_ontology_is_only_in_the_whole_when_asked_for(rdf):
    from pangloss_rdf.dump import dump_sections, sections_named
    from pangloss_rdf.ontology import ontology_quads

    declare()
    importlib.reload(rdf)
    assert "derived" in dump_sections()
    without = {q.subject.value for q in ontology_quads()}
    included = {q.subject.value for q in ontology_quads(["derived"])}
    assert "http://test.com/ontology/sameGroup" not in without
    assert "http://test.com/ontology/sameGroup" in included
    assert without < included
    with pytest.raises(ValueError, match="no part of a dump called 'nothing'"):
        sections_named(["nothing"])
    with pytest.raises(ValueError, match="there are: derived"):
        list(ontology_quads(["nothing"]))


@no_type_check
def test_a_derived_class_with_the_name_of_a_model_is_refused(rdf):
    class Person(Entity):
        pass

    class Knows(Entity):
        pass

    class Knows2(DerivedEdge):
        a: Annotated[Person, Subject()]
        b: Annotated[Person, Object(reverse_name="taught")]

    class Taught(DerivedEdge):
        a: Annotated[Person, Subject()]
        b: Annotated[Person, Object()]

    initialise(bind_database=False)
    # (`Taught` is `taught`, which is also the reverse of `Knows2`)
    with pytest.raises(PanglossMetaError) as error:
        list(rdf.derived_ontology())
    assert "are both the property http://test.com/ontology/taught" in str(error.value)


@no_type_check
def test_the_quads_of_an_edge_are_what_its_reader_may_know(rdf):
    from pangloss_rdf.vocabulary import RDF_OBJECT, RDF_PREDICATE, RDF_SUBJECT, pgo

    m = declare()
    GaveTo = m["GaveTo"]
    view = GaveTo.View(
        id="KEY",
        ends=["giver", "receiver"],
        giver={"id": "1", "type": "Person", "label": "A"},
        receiver={"id": "2", "type": "Group", "label": "G"},
        qualifiers={"year": 1500},
        status="asserted",
        standing="claim",
    )
    found = {
        "view": view,
        "evidence": [{"id": "n1", "type": "Note"}, {"id": "x", "type": "Unknown"}],
        "justifications": 2,
        "plain": True,
        "context_labels": ["Negative"],
        "status": "asserted",
        "standing": "claim",
    }
    quads = rdf.edge_quads(GaveTo, found)
    node = "http://test.com/derived/GaveTo/KEY"
    assert {q.graph.value for q in quads} == {node}
    a, g = "http://test.com/Person/1", "http://test.com/Group/2"
    predicate = "http://test.com/ontology/gaveTo"
    plain = [
        (q.subject.value, q.predicate.value, getattr(q.object, "value", None))
        for q in quads
    ]
    assert plain[0] == (a, predicate, g)
    of_node = {
        q.predicate.value: getattr(q.object, "value", None) or q.object.lexical
        for q in quads
        if q.subject.value == node
    }
    assert of_node[RDF_SUBJECT.value] == a and of_node[RDF_OBJECT.value] == g
    assert of_node[RDF_PREDICATE.value] == predicate
    assert of_node["http://test.com/ontology/GaveTo.year"] == "1500"
    assert of_node[pgo("plain").value] == "true"
    assert of_node[pgo("justificationCount").value] == "2"
    assert of_node[pgo("context").value] == "Negative"
    # (the documents it rests on; one of a class there is not is left out)
    assert [q.object.value for q in quads if q.predicate == pgo("justifiedBy")] == [
        "http://test.com/Note/n1"
    ]
    # (none of its justifications is plain: no direct triple, only the statement)
    # (a plain one that is asserted says no status: the direct triple says it)
    assert pgo("derivedStatus").value not in of_node
    doubted = rdf.edge_quads(GaveTo, {**found, "plain": False, "status": "reported"})
    assert not any(q.subject.value == a for q in doubted)
    # (the status, in place of the direct triple)
    assert len(doubted) == len(quads)
    assert [
        q.object.lexical for q in doubted if q.predicate == pgo("derivedStatus")
    ] == ["reported"]
    # (a plain one that is contested: the direct triple, and the status)
    contested = rdf.edge_quads(GaveTo, {**found, "status": "contested"})
    assert contested[0] == quads[0]
    assert [
        q.object.lexical for q in contested if q.predicate == pgo("derivedStatus")
    ] == ["contested"]
    # (an end of a class that is not exported: nothing)
    gone = GaveTo.View(
        id="K2",
        ends=["giver", "receiver"],
        giver={"id": "1", "type": "Nobody", "label": "A"},
        receiver={"id": "2", "type": "Group", "label": "G"},
        qualifiers={"year": 1500},
        status="asserted",
        standing="claim",
    )
    assert rdf.edge_quads(GaveTo, {**found, "view": gone}) == []


def test_adding_the_part_of_a_dump_leaves_the_conversion_as_it_was():
    """(a regression: `pangloss_derived.rdf` imported `pangloss_rdf.dump`, and with it the module
    `pangloss_rdf.convert`, before anything had used the package's function of that name, which is imported lazily:
    `from pangloss_rdf import convert` then gave the module, and every conversion failed. The module can be called)"""
    import subprocess
    import sys

    code = (
        "import typing\n"
        "from pangloss_core import BaseSettings, DatabaseSettings\n"
        "from pydantic import AnyHttpUrl\n"
        "class Settings(BaseSettings):\n"
        "    PROJECT_NAME: str = 'T'\n"
        "    BACKEND_CORS_ORIGINS: list[typing.Any] = []\n"
        "    INSTALLED_APPS: list[str] = []\n"
        "    STORAGE: str | None = 'pangloss_sdk.storage:api'\n"
        "    DATABASE: DatabaseSettings = DatabaseSettings()\n"
        "    INTERFACE_LANGUAGES: list[str] = ['en']\n"
        "    DEFAULT_INTERFACE_LANGUAGE: str = 'en'\n"
        "    AUTHJWT_SECRET_KEY: str = 'x'\n"
        "    ENTITY_BASE_URL: AnyHttpUrl = AnyHttpUrl('http://test.com/')\n"
        "Settings()\n"
        "import pangloss_derived.rdf\n"
        "import pangloss_rdf.dump\n"
        "from pangloss_rdf import convert\n"
        "assert callable(convert), convert\n"
        "from pangloss_models import Entity, initialise\n"
        "class Person(Entity):\n"
        "    pass\n"
        "initialise(bind_database=False)\n"
        "view = Person.View(id='01a1e8f7-24f0-767c-960b-dd361801eca1', label='A', type='Person')\n"
        "assert any('Person' in str(q.subject) for q in convert(view))\n"
        "print('ok')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=120
    )
    assert result.stdout.strip().endswith("ok"), result.stderr[-2000:]


@no_type_check
def test_an_edge_of_the_record_says_so_and_a_claim_says_nothing(rdf):
    from pangloss_rdf.vocabulary import pgo

    GaveTo = declare()["GaveTo"]
    view = GaveTo.View(
        id="KEY",
        ends=["giver", "receiver"],
        giver={"id": "1", "type": "Person", "label": "A"},
        receiver={"id": "2", "type": "Group", "label": "G"},
        qualifiers={"year": 1500},
        status="asserted",
        standing="record",
    )
    found = {
        "view": view,
        "evidence": [],
        "justifications": 1,
        "plain": True,
        "context_labels": [],
        "status": "asserted",
        "standing": "record",
    }

    def standings(found):
        return [
            q.object.lexical
            for q in rdf.edge_quads(GaveTo, found)
            if q.predicate == pgo("derivedStanding")
        ]

    assert standings(found) == ["record"]
    assert standings({**found, "standing": "claim"}) == []
    ontology = list(rdf.derived_ontology())
    assert any(q.subject == pgo("derivedStanding") for q in ontology)
