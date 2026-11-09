from types import SimpleNamespace
from typing import Annotated
from uuid import UUID

import pytest
from pangloss_models import (
    Document,
    EdgeModel,
    Entity,
    ReifiedRelation,
    RelationConfig,
    Trait,
    ViaEdge,
    initialise,
)
from pangloss_models.exceptions import PanglossMetaError
from pangloss_rdf import (
    IRI,
    RDFMeta,
    check_models,
    class_uri,
    edge_uri,
    item_uri,
    property_uri,
    reverse_property_uri,
    value_uri,
)
from pangloss_rdf import uris as module
from pangloss_rdf.uris import property_name

ID = UUID("0190a000-0000-7000-8000-000000000001")
ONTOLOGY = "https://example.org/ontology"


def declare():
    class Agent(Trait):
        nickname: str

    class Person(Entity, Agent):
        date_of_birth: str

    class Group(Entity, Agent):
        pass

    class Sure(EdgeModel):
        level: int

    class InRole[T](ReifiedRelation[T]):
        role: str

    class Statement(Document):
        _meta = Document.Meta(abstract=True)

        involves: list[Agent]

    class Activity(Statement):
        carried_out_by: Annotated[
            ViaEdge[Agent, Sure], RelationConfig(reverse_name="carried_out")
        ]
        participants: list[InRole[Agent]]
        witnesses: list[Person]

    initialise()
    return SimpleNamespace(**locals())


def test_a_class_is_under_the_ontology():
    m = declare()
    assert class_uri(m.Person) == IRI(f"{ONTOLOGY}/Person")


def test_every_use_of_a_generic_is_one_class():
    m = declare()
    assert class_uri(m.InRole[m.Person]) == class_uri(m.InRole[m.Group])
    assert class_uri(m.InRole[m.Person]) == IRI(f"{ONTOLOGY}/InRole")


def test_a_property_is_camel_case_on_its_class():
    m = declare()
    assert property_uri(m.Activity, "carried_out_by") == IRI(
        f"{ONTOLOGY}/Activity.carriedOutBy"
    )
    assert property_name(m.Person, "date_of_birth") == "Person.dateOfBirth"


def test_a_subclass_uses_the_property_of_the_class_that_declares_it():
    m = declare()
    assert property_uri(m.Activity, "involves") == IRI(f"{ONTOLOGY}/Statement.involves")


def test_a_field_of_a_trait_is_the_traits():
    m = declare()
    uri = IRI(f"{ONTOLOGY}/Agent.nickname")
    assert property_uri(m.Person, "nickname") == uri
    assert property_uri(m.Group, "nickname") == uri


def test_a_field_of_a_generic_is_the_generics():
    m = declare()
    assert property_uri(m.InRole[m.Person], "role") == IRI(f"{ONTOLOGY}/InRole.role")


def test_a_field_of_a_kind_of_model_is_the_declared_class():
    m = declare()
    assert property_uri(m.InRole[m.Person], "target") == IRI(
        f"{ONTOLOGY}/InRole.target"
    )


def test_a_field_of_an_edge_model():
    m = declare()
    assert property_uri(m.Sure, "level") == IRI(f"{ONTOLOGY}/Sure.level")


def test_a_reverse_property():
    m = declare()
    assert reverse_property_uri(m.Activity, "carried_out_by") == IRI(
        f"{ONTOLOGY}/Activity.carriedOut"
    )
    assert reverse_property_uri(m.Activity, "witnesses") == IRI(
        f"{ONTOLOGY}/Activity.witnessesReverse"
    )


def test_a_literal_has_no_reverse():
    m = declare()
    with pytest.raises(PanglossMetaError, match="not a relation"):
        reverse_property_uri(m.Person, "date_of_birth")


def test_a_field_that_is_not_there():
    m = declare()
    with pytest.raises(PanglossMetaError, match="no field"):
        property_uri(m.Person, "nope")


def test_an_item_is_under_the_base_url_with_no_double_slash():
    m = declare()
    assert item_uri(m.Person, ID) == IRI(f"https://example.org/Person/{ID}")


def test_the_uris_of_what_has_no_id():
    subject = IRI("https://example.org/Activity/1")
    assert value_uri(subject, "Person.born") == IRI(f"{subject}/Person.born")
    assert value_uri(subject, "Person.names", 2) == IRI(f"{subject}/Person.names/2")
    assert edge_uri(subject, "Activity.by") == IRI(f"{subject}/edge/Activity.by/0")
    assert edge_uri(subject, "Activity.by", 3) == IRI(f"{subject}/edge/Activity.by/3")


def test_a_class_name_is_used_for_the_class_and_its_items():
    class Person(Entity):
        _rdf_meta = RDFMeta(class_name="Human")

        name: str

    class Student(Person):
        pass

    initialise()
    assert class_uri(Person) == IRI(f"{ONTOLOGY}/Human")
    assert item_uri(Person, ID) == IRI(f"https://example.org/Human/{ID}")
    assert property_uri(Person, "name") == IRI(f"{ONTOLOGY}/Human.name")
    # (a subclass has its own name, and its parent's property)
    assert class_uri(Student) == IRI(f"{ONTOLOGY}/Student")
    assert property_uri(Student, "name") == IRI(f"{ONTOLOGY}/Human.name")


def test_a_class_uri_replaces_the_class_only():
    class Person(Entity):
        _rdf_meta = RDFMeta(class_uri="http://xmlns.com/foaf/0.1/Person")

    initialise()
    assert class_uri(Person) == IRI("http://xmlns.com/foaf/0.1/Person")
    assert item_uri(Person, ID) == IRI(f"https://example.org/Person/{ID}")


@pytest.mark.parametrize(
    ("setting", "expected"),
    [
        ("https://onto.org/x", "https://onto.org/x/Thing"),
        ("https://onto.org/x/", "https://onto.org/x/Thing"),
        ("https://onto.org/x#", "https://onto.org/x#Thing"),
    ],
)
def test_the_ontology_can_be_elsewhere(monkeypatch, setting, expected):
    class Thing(Entity):
        pass

    monkeypatch.setattr(
        module,
        "get_settings",
        lambda: SimpleNamespace(
            ENTITY_BASE_URL="https://example.org/", RDF_ONTOLOGY_URL=setting
        ),
    )
    assert class_uri(Thing) == IRI(expected)


def test_good_models_pass_the_check():
    declare()
    check_models()


def test_two_classes_with_one_name_are_refused():
    class Person(Entity):
        _rdf_meta = RDFMeta(class_name="Thing")

    class Thing(Entity):
        pass

    initialise()
    with pytest.raises(PanglossMetaError, match="both the class .*/Thing"):
        check_models()


def test_two_fields_with_one_property_are_refused():
    class Person(Entity):
        first_name: str
        firstName: str

    initialise()
    with pytest.raises(PanglossMetaError, match="both the property .*Person.firstName"):
        check_models()


def test_a_class_under_the_ontologys_address_is_refused():
    class Person(Entity):
        _rdf_meta = RDFMeta(class_name="ontology")

    initialise()
    with pytest.raises(PanglossMetaError, match="under the ontology"):
        check_models()
