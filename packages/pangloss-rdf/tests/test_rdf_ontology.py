"""The ontology, shapes and checks, from models alone"""

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated

import pytest
from pangloss_models import Document, Entity, RelationConfig, Trait, initialise
from pangloss_models.exceptions import PanglossMetaError
from pangloss_models.field_definitions import FieldSubclassing
from pangloss_rdf import (
    IRI,
    OntologyProperty,
    RDFField,
    RDFMeta,
    class_uri,
    property_uri,
)
from pangloss_rdf.checks import check_markers, warnings
from pangloss_rdf.fields import ontology_prefixes, rdf_field
from pangloss_rdf.generate import generate_module
from pangloss_rdf.ontology import jsonld_context, ontology_quads
from pangloss_rdf.shacl import shape_quads
from pangloss_rdf.serialise import prefixes, serialise
from pangloss_rdf.vocabulary import (
    RDFS_SUBCLASS,
    RDFS_SUBPROPERTY,
    check_prefixes,
    ontology_prefix,
    owl,
    pgo,
    schema,
)

P1 = OntologyProperty("http://o/P1", domain=("http://o/E1",), range=("http://o/E2",))


class E1:
    _rdf_uri = "http://o/E1"


class E2:
    _rdf_uri = "http://o/E2"


def declare():
    class Agent(Trait):
        pass

    class Person(Entity, Agent, E2):
        """A person"""

        name: str
        nick: str | None = None

    class Group(Entity, Agent):
        pass

    class Base(Document):
        _meta = Document.Meta(abstract=True)

        involves: list[Agent]

    class Act(Base, E1):
        by: Annotated[
            Person,
            RelationConfig(
                reverse_name="did",
                subclasses_parent_fields=[
                    FieldSubclassing("involves", field_on_model=Base)
                ],
            ),
            RDFField(parent=P1),
        ]
        either: Person | Group

    initialise()
    return Person, Group, Base, Act, Agent


def has(quads, s, p, o):
    return any(q.subject == s and q.predicate == p and q.object == o for q in quads)


def test_the_classes_and_their_parents():
    Person, _, _, Act, Agent = declare()
    quads = list(ontology_quads())
    assert has(quads, class_uri(Person), RDFS_SUBCLASS, class_uri(Agent))
    assert has(quads, class_uri(Person), RDFS_SUBCLASS, IRI("http://o/E2"))
    assert has(quads, class_uri(Act), RDFS_SUBCLASS, IRI("http://o/E1"))


def test_a_narrowing_and_an_alignment_are_subproperties():
    _, _, Base, Act, _ = declare()
    quads = list(ontology_quads())
    by = property_uri(Act, "by")
    assert has(quads, by, RDFS_SUBPROPERTY, property_uri(Base, "involves"))
    assert has(quads, by, RDFS_SUBPROPERTY, IRI("http://o/P1"))


def test_several_ranges_are_not_an_intersection():
    Person, Group, _, Act, _ = declare()
    quads = list(ontology_quads())
    either = property_uri(Act, "either")
    assert has(quads, either, schema("rangeIncludes"), class_uri(Person))
    assert has(quads, either, schema("rangeIncludes"), class_uri(Group))
    assert not [q for q in quads if q.predicate.value.endswith("rdf-schema#range")]


def test_the_reverse_is_an_inverse():
    _, _, _, Act, _ = declare()
    quads = list(ontology_quads())
    did = IRI("https://example.org/ontology/Act.did")
    assert has(quads, did, owl("inverseOf"), property_uri(Act, "by"))


def test_a_required_literal_has_a_minimum_and_an_optional_one_none():
    Person, *_ = declare()
    quads = list(shape_quads())
    minimums = {
        q.subject.value.rsplit("/", 1)[1]
        for q in quads
        if q.predicate.value.endswith("minCount")
    }
    assert "name" in minimums
    assert "nick" not in minimums


def test_the_context_has_the_terms():
    Person, *_ = declare()
    context = jsonld_context()
    assert context["Person"] == class_uri(Person).value
    assert context["Act.by"]["@type"] == "@id"


def test_an_excluded_field_or_class_is_not_in_it():
    class Hidden(Entity):
        _rdf_meta = RDFMeta(exclude=True)

    class Open(Entity):
        secret: Annotated[str, RDFField(exclude=True)]

    initialise()
    quads = list(ontology_quads())
    assert not [q for q in quads if q.subject == class_uri(Hidden)]
    assert not [q for q in quads if q.subject == property_uri(Open, "secret")]


def test_a_marker_on_each_kind_of_field_is_kept():
    class Person(Entity):
        name: Annotated[str, RDFField(name="n")]
        tags: Annotated[list[str], RDFField(language="la")]

    initialise()
    assert rdf_field(Person._meta.fields["name"]).name == "n"
    assert rdf_field(Person._meta.fields["tags"]).language == "la"
    assert property_uri(Person, "name").value.endswith("/Person.n")


def test_ordered_is_only_for_a_list():
    class Person(Entity):
        name: Annotated[str, RDFField(ordered=True)]

    initialise()
    with pytest.raises(PanglossMetaError, match="only a list"):
        check_markers()


def test_a_name_and_a_uri_are_not_both_given():
    with pytest.raises(PanglossMetaError, match="not both"):
        RDFField(name="a", uri="http://a/b")


def test_warnings_for_placeholders_and_a_domain_that_does_not_fit():
    class Act(Document):
        x: Annotated[
            str,
            RDFField(parent=OntologyProperty("http://o/P", domain=("http://o/E9",))),
        ]

    initialise()
    found = warnings()
    assert any("ENTITY_BASE_URL" in w for w in found)
    assert any("not in the domain" in w for w in found)


def test_the_mixins_module_is_generated(tmp_path: Path):
    source = tmp_path / "o.ttl"
    source.write_text(
        """
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        @prefix o: <http://o/> .
        o:A a rdfs:Class ; rdfs:comment "An \\"A\\"."@en .
        o:B a rdfs:Class ; rdfs:subClassOf o:A .
        o:C a rdfs:Class ; rdfs:subClassOf o:A, o:B .
        o:Old a owl:Class ; owl:deprecated true .
        o:p-q a owl:ObjectProperty ; rdfs:domain o:A ; rdfs:range o:B .
        """
    )
    namespace: dict = {}
    exec(generate_module(source, "O"), namespace)
    assert ontology_prefixes()["O"] == "http://o/"
    assert namespace["C"].__bases__ == (namespace["B"],)
    assert namespace["C"]._rdf_uri == "http://o/C"
    assert "Old" not in namespace
    assert namespace["p_q"] == OntologyProperty(
        "http://o/p-q", ("http://o/A",), ("http://o/B",)
    )


def test_the_package_imports_without_the_server_or_rdflib():
    import subprocess
    import sys

    code = (
        "import sys, pangloss_rdf.meta, pangloss_rdf.fields, pangloss_rdf.ontologies.crm;"
        "from pangloss_rdf import RDFMeta, RDFField;"
        "assert not {'rdflib','fastapi','typer'} & set(sys.modules), 'imported'"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def _settings(monkeypatch, **values):
    import pangloss_rdf.vocabulary as vocabulary

    base = {"ENTITY_BASE_URL": "https://example.org/", "PROJECT_NAME": "My Project"}
    settings = SimpleNamespace(**(base | values))
    monkeypatch.setattr(vocabulary, "get_settings", lambda: settings)
    monkeypatch.setattr(
        sys.modules["pangloss_rdf.uris"], "get_settings", lambda: settings
    )


def test_the_prefix_comes_from_the_project(monkeypatch):
    _settings(monkeypatch)
    assert ontology_prefix() == "my_project"
    assert prefixes()["my_project"] == "https://example.org/ontology/"


def test_the_core_terms_are_the_projects_own(monkeypatch):
    _settings(monkeypatch)
    assert pgo("Edge").value == "https://example.org/ontology/core#Edge"
    assert prefixes()["core"] == "https://example.org/ontology/core#"


def test_the_settings_choose_the_prefixes_and_address(monkeypatch):
    _settings(
        monkeypatch,
        RDF_PREFIX="demo",
        RDF_CORE_PREFIX="fp",
        RDF_CORE_URL="https://w3id.org/factoid/ns",
    )
    assert prefixes()["demo"] == "https://example.org/ontology/"
    assert prefixes()["fp"] == "https://w3id.org/factoid/ns#"
    check_prefixes()


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("rdf", "rdf_"),
        ("core", "core_"),
        ("1st", "p_1st"),
        ("", "p"),
        ("A-b c", "a_b_c"),
    ],
)
def test_a_name_that_will_not_do_is_made_into_a_prefix(monkeypatch, name, expected):
    _settings(monkeypatch, PROJECT_NAME=name)
    assert ontology_prefix() == expected
    check_prefixes()


@pytest.mark.parametrize(
    "values",
    [
        {"RDF_PREFIX": "owl"},
        {"RDF_PREFIX": "a b"},
        {"RDF_PREFIX": "1a"},
        {"RDF_PREFIX": "x", "RDF_CORE_PREFIX": "x"},
    ],
)
def test_a_prefix_that_cannot_be_used_is_refused(monkeypatch, values):
    _settings(monkeypatch, **values)
    with pytest.raises(PanglossMetaError, match="RDF prefixes"):
        check_prefixes()


def test_the_core_terms_are_defined_unless_they_are_elsewhere(monkeypatch):
    declare()
    defined = {q.subject for q in ontology_quads()}
    assert pgo("Edge") in defined and pgo("inSpace") in defined
    assert not [q for q in ontology_quads() if q.predicate == owl("imports")]


def test_a_mixed_in_ontology_has_its_prefix_in_the_output():
    from pangloss_rdf.ontologies.crm import E21_Person
    from pangloss_rdf.terms import Quad

    uri = IRI("https://example.org/x")
    text = serialise(
        [
            Quad(
                uri,
                IRI("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"),
                IRI(E21_Person._rdf_uri),
            )
        ],
        "ttl",
    )
    assert "crm:E21_Person" in text
    assert "ns1:" not in text


def test_a_prefix_a_generated_module_cannot_have(tmp_path: Path):
    source = tmp_path / "o.ttl"
    source.write_text("")
    with pytest.raises(PanglossMetaError, match="cannot be a prefix"):
        generate_module(source, "CIDOC CRM")


def test_a_project_prefix_cannot_be_that_of_a_mixed_in_ontology(monkeypatch):
    import pangloss_rdf.ontologies.crm  # noqa: F401

    _settings(monkeypatch, RDF_PREFIX="crm")
    with pytest.raises(PanglossMetaError, match="mixed in"):
        check_prefixes()
