"""`Cites[T]` in the models, with no database (`pangloss_models.citations`): a relation that names a document by its
id, written as a small node of the citing document"""

from uuid import uuid4

import pytest
from pangloss_models import (
    Cites,
    Document,
    Entity,
    PanglossModelError,
    export_models,
    initialise,
)
from pangloss_models.citations import allows, citation_class, is_citation
from pangloss_models.field_definitions import RelationToCitation
from pydantic import ValidationError


def models():
    class Person(Entity):
        pass

    class Statement(Document):
        _meta = Document.Meta(abstract=True)

    class Birth(Statement):
        person: Person

    class Death(Statement):
        person: Person

    class Note(Document):
        text: str = ""

    class Factoid(Document):
        _meta = Document.Meta(cited_with=["source"])
        source: str = ""
        statements: list[Statement]

    class SameAs(Document):
        people: list[Person]
        evidence: list[Cites[Statement]]  # ty: ignore[invalid-type-form]
        see: Cites[Note | Factoid] | None = None  # ty: ignore[invalid-type-form]

    initialise()
    return Person, Statement, Birth, Death, Note, Factoid, SameAs


def test_a_citation_is_a_relation_to_a_node_of_the_citing_document():
    _, Statement, _, _, Note, Factoid, SameAs = models()
    fields = SameAs._meta.fields.relation_fields

    (option,) = fields["evidence"].type_options
    assert isinstance(option, RelationToCitation)
    assert option.annotated_type is citation_class()
    assert option.cited == frozenset({Statement})

    (option,) = fields["see"].type_options
    assert option.cited == frozenset({Note, Factoid})
    assert fields["see"].optional


def test_it_is_written_as_a_reference_or_in_full():
    Person, *_, SameAs = models()
    target = uuid4()
    made = SameAs.Create(
        label="x",
        people=[],
        evidence=[
            {"type": "Birth", "id": target},
            {"type": "PGCitation", "target_id": target, "target_type": "Death"},
            {"type": "PGCitation", "targetId": target, "targetType": "Death"},
        ],
    )
    assert [(c.target_id, c.target_type) for c in made.evidence] == [
        (target, "Birth"),
        (target, "Death"),
        (target, "Death"),
    ]
    assert all(is_citation(c) for c in made.evidence)
    assert made.see is None

    # (one alone, and none)
    one = SameAs.Create(
        label="x", people=[], evidence=[], see={"type": "Note", "id": target}
    )
    assert one.see.target_type == "Note"


def test_what_is_not_a_citation_is_refused():
    *_, SameAs = models()
    with pytest.raises(ValidationError):
        SameAs.Create(label="x", people=[], evidence=[{"type": "Birth"}])
    with pytest.raises(ValidationError):
        # (a document written out in full is containment, not a citation)
        SameAs.Create(
            label="x",
            people=[],
            evidence=[{"type": "Birth", "label": "b", "person": None}],
        )


def test_which_classes_may_be_cited():
    _, Statement, Birth, _, Note, Factoid, _ = models()
    assert allows(frozenset({Statement}), "Birth")
    assert allows(frozenset({Birth}), "Birth")
    assert not allows(frozenset({Birth}), "Death")
    assert not allows(frozenset({Statement}), "Note")
    assert allows(frozenset({Note, Factoid}), "Factoid")
    assert not allows(frozenset({Statement}), "Nothing")


def test_only_a_document_can_be_cited():
    class Person(Entity):
        pass

    class SameAs(Document):
        evidence: list[Cites[Person]]  # ty: ignore[invalid-type-form]

    with pytest.raises(PanglossModelError, match="only a document can be cited"):
        initialise()


def test_the_export_says_what_may_be_cited_and_the_class_of_the_node():
    models()
    exported = export_models()["models"]
    fields = {f["name"]: f for f in exported["SameAs"]["fields"]}
    assert fields["evidence"]["options"] == [
        {
            "kind": "document",
            "type": "PGCitation",
            "edgeModel": None,
            "cites": ["Statement"],
        }
    ]
    assert fields["see"]["options"][0]["cites"] == ["Factoid", "Note"]

    citation = exported["PGCitation"]
    assert citation["createDirectly"] is False
    assert {f["name"] for f in citation["fields"]} >= {
        "target_id",
        "target_type",
        "changed_since_cited",
        "target_head_id",
        "cited_version",
    }


def test_a_project_without_citations_has_no_such_model():
    class Person(Entity):
        pass

    initialise()
    assert "PGCitation" not in export_models()["models"]


def test_a_generic_document_may_be_cited_by_its_base_class():
    from pangloss_models import ReifiedRelationDocument
    from pangloss_models.citations import cited_types

    class Person(Entity):
        pass

    class Place(Entity):
        pass

    class Claim[T](ReifiedRelationDocument[T]):
        pass

    class Other[T](ReifiedRelationDocument[T]):
        pass

    class Review(Document):
        claims: list[Cites[Claim[Person] | Claim[Place]]]  # ty: ignore[invalid-type-form]

    initialise()
    annotation = Review.__annotations__["claims"].__args__[0]
    cited = cited_types(annotation)
    assert cited == frozenset({Claim[Person], Claim[Place]})
    # (a node of a generic is stored as its base)
    assert allows(cited, "Claim")
    assert not allows(cited, "Other")
    assert not allows(frozenset({Claim[Person]}), "Nothing")


def test_a_generic_that_is_not_known_is_allowed_by_its_name():
    from pangloss_models.model_registry import ModelRegistry

    class Person(Entity):
        pass

    from pangloss_models import ReifiedRelationDocument

    class Claim[T](ReifiedRelationDocument[T]):
        pass

    initialise()
    cited = frozenset({Claim[Person]})
    del ModelRegistry._model_dict["Claim"]
    try:
        assert allows(cited, "Claim")
        assert not allows(cited, "Person")
        assert not allows(frozenset({Person}), "Claim")
    finally:
        ModelRegistry._model_dict["Claim"] = Claim


def test_a_citation_that_does_not_protect_says_so():
    from pangloss_models.citations import protects, type_name_of

    class Note(Document):
        pass

    class DerivedFrom[Target](Cites[Target]):
        protect = False

    class Derived(Document):
        cites: list[Cites[Note]]  # ty: ignore[invalid-type-form]
        rests_on: list[DerivedFrom[Note]]  # ty: ignore[invalid-type-form]

    initialise()
    assert protects(Cites[Note])
    assert not protects(DerivedFrom[Note])
    # (what is no citation at all protects as any relation does)
    assert protects(Note)
    assert type_name_of({"type": "PGCitation"}) == "PGCitation"
    assert type_name_of(Note.Create(label="n")) == "Note"
    assert type_name_of(object()) is None
