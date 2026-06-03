from typing import Literal, no_type_check
from uuid import UUID, uuid7

from pydantic import AnyHttpUrl

from pangloss_models import initialise
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.edge_model import EdgeModel
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.reified_relation import ReifiedRelationDocument


def test_reference_set_on_entities():
    class Person(Entity):
        pass

    initialise()

    assert Person.ReferenceSet
    assert Person.ReferenceSet.model_fields["type"].annotation == Literal["Person"]
    assert Person.ReferenceSet.model_fields["id"].annotation == UUID | AnyHttpUrl


@no_type_check
def test_reference_set_with_edge_property():
    class Person(Entity):
        pass

    class Certainty(EdgeModel):
        certainty: int

    initialise()

    assert Person.ReferenceSet

    assert Person.ReferenceSet.model_fields["type"].annotation == Literal["Person"]

    assert Person.ReferenceSet.apply_edge_model(Certainty)

    assert issubclass(Person.ReferenceSet._via.Certainty, Person.ReferenceSet)

    assert (
        Person.ReferenceSet._via.Certainty.__name__ == "PersonReferenceSetViaCertainty"
    )

    assert (
        Person.ReferenceSet._via.Certainty.model_fields["edge_properties"].annotation
        is Certainty
    )

    assert (
        Person.ReferenceSet._via.Certainty.model_fields["type"].annotation
        == Literal["Person"]
    )

    _uuid = uuid7()

    p = Person.ReferenceSet(id=_uuid, label="something")
    assert p.id == _uuid
    assert p.label is None


def test_reference_view_on_entities():
    class Person(Entity):
        age: int

    initialise()

    assert Person.ReferenceView
    assert Person.ReferenceView.model_fields["type"].annotation == Literal["Person"]
    assert Person.ReferenceView.model_fields["id"].annotation == UUID
    assert "age" not in Person.ReferenceView.model_fields


def test_reference_view_via_edge():
    class Person(Entity):
        pass

    class Certainty(EdgeModel):
        certainty: int

    initialise()

    assert Person.ReferenceView

    assert Person.ReferenceView.model_fields["type"].annotation == Literal["Person"]

    assert Person.ReferenceView.apply_edge_model(Certainty)

    assert issubclass(Person.ReferenceView._via.Certainty, Person.ReferenceView)

    assert (
        Person.ReferenceView._via.Certainty.__name__
        == "PersonReferenceViewViaCertainty"
    )

    assert (
        Person.ReferenceView._via.Certainty.model_fields["edge_properties"].annotation
        is Certainty
    )

    assert (
        Person.ReferenceView._via.Certainty.model_fields["type"].annotation
        == Literal["Person"]
    )

    _uuid = uuid7()

    p = Person.ReferenceView(id=_uuid, label="something")
    assert p.id == _uuid
    assert p.label == "something"


def test_reference_view_on_entities_with_extra_fields():
    class Person(Entity):
        _meta = Entity.Meta(reference_view_extra_fields=["age"])
        age: int

    initialise()

    assert Person.ReferenceView
    assert Person.ReferenceView.model_fields["type"].annotation == Literal["Person"]
    assert Person.ReferenceView.model_fields["id"].annotation == UUID
    assert Person.ReferenceView.model_fields["age"].annotation is int


def test_reference_view_on_documents():
    class Statement(Document):
        age: int

    initialise()

    assert Statement.ReferenceView
    assert (
        Statement.ReferenceView.model_fields["type"].annotation == Literal["Statement"]
    )
    assert Statement.ReferenceView.model_fields["id"].annotation == UUID
    assert "age" not in Statement.ReferenceView.model_fields


def test_reference_view_via_edge_on_document():
    class Statement(Document):
        pass

    class Certainty(EdgeModel):
        certainty: int

    initialise()

    assert Statement.ReferenceView

    assert (
        Statement.ReferenceView.model_fields["type"].annotation == Literal["Statement"]
    )

    assert Statement.ReferenceView.apply_edge_model(Certainty)

    assert issubclass(Statement.ReferenceView._via.Certainty, Statement.ReferenceView)

    assert (
        Statement.ReferenceView._via.Certainty.__name__
        == "StatementReferenceViewViaCertainty"
    )

    assert (
        Statement.ReferenceView._via.Certainty.model_fields[
            "edge_properties"
        ].annotation
        is Certainty
    )

    assert (
        Statement.ReferenceView._via.Certainty.model_fields["type"].annotation
        == Literal["Statement"]
    )

    _uuid = uuid7()

    p = Statement.ReferenceView(id=_uuid, label="something")
    assert p.id == _uuid
    assert p.label == "something"


def test_reference_view_on_reified_relation_document():
    class Action(Document):
        pass

    class InPlace[Target](ReifiedRelationDocument[Target]):
        action: Action

    class Person(Entity):
        pass

    initialise()

    assert InPlace[Person].ReferenceView

    assert InPlace[Person].ReferenceView.model_fields["label"].annotation is str
    assert (
        InPlace[Person].ReferenceView.model_fields["type"].annotation
        == Literal["InPlace"]
    )


def test_reference_view_on_reified_relation_document_via_edge_model():
    class Action(Document):
        pass

    class InPlace[Target](ReifiedRelationDocument[Target]):
        action: Action

    class Person(Entity):
        pass

    class Certainty(EdgeModel):
        certainty: int

    initialise()

    assert InPlace[Person].ReferenceView

    assert InPlace[Person].ReferenceView.model_fields["label"].annotation is str
    assert (
        InPlace[Person].ReferenceView.model_fields["type"].annotation
        == Literal["InPlace"]
    )

    in_place_with_edge_model = InPlace[Person].ReferenceView.apply_edge_model(Certainty)

    assert (
        InPlace[Person].ReferenceView._via.Certainty.__name__
        == "InPlaceReferenceViewViaCertainty"
    )

    assert issubclass(in_place_with_edge_model, InPlace[Person].ReferenceView)
    assert (
        in_place_with_edge_model.model_fields["edge_properties"].annotation is Certainty
    )
    assert in_place_with_edge_model.model_fields["label"].annotation is str
