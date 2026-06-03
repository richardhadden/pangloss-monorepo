from datetime import datetime
from inspect import isclass
from typing import Annotated, get_args, get_origin, no_type_check
from uuid import UUID, uuid7

from pydantic.fields import FieldInfo

from pangloss_models import initialise
from pangloss_models.model_bases.base_models import _APIHeadMeta
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.embedded import Embedded
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.reified_relation import (
    ReifiedRelation,
    ReifiedRelationDocument,
)


@no_type_check
def test_document_has_head_view():
    class Person(Entity):
        pass

    class Statement(Document):
        name: str
        person: Person
        action: Action

    class Action(Document):
        pass

    initialise()

    assert Statement.HeadView

    assert "name" in Statement.HeadView.model_fields
    assert Statement.HeadView.model_fields["name"].annotation is str

    assert "label" in Statement.HeadView.model_fields
    assert Statement.HeadView.model_fields["label"].annotation is str

    assert "id" in Statement.HeadView.model_fields
    assert Statement.HeadView.model_fields["id"].annotation is UUID

    assert "meta" in Statement.HeadView.model_fields
    assert Statement.HeadView.model_fields["meta"].annotation is _APIHeadMeta

    assert "person" in Statement.HeadView.model_fields
    assert Statement.HeadView.model_fields["person"].annotation is Person.ReferenceView

    assert "action" in Statement.HeadView.model_fields
    assert Statement.HeadView.model_fields["action"].annotation is Action.View


@no_type_check
def test_entity_has_head_view():
    class Person(Entity):
        name: str

    initialise()

    assert Person.HeadView

    assert "name" in Person.HeadView.model_fields
    assert Person.HeadView.model_fields["name"].annotation is str

    assert "label" in Person.HeadView.model_fields
    assert Person.HeadView.model_fields["label"].annotation is str

    assert "id" in Person.HeadView.model_fields
    assert Person.HeadView.model_fields["id"].annotation is UUID

    assert "meta" in Person.HeadView.model_fields
    assert Person.HeadView.model_fields["meta"].annotation is _APIHeadMeta


@no_type_check
def test_reified_relation_document_has_head_view():
    class Person(Entity):
        pass

    class Place(Entity):
        pass

    class SomethingInPlace[T](ReifiedRelationDocument[T]):
        place: Place

    class Statement(Document):
        person_in_place: SomethingInPlace[Person]

    initialise()

    assert SomethingInPlace[Person].HeadView

    assert "place" in SomethingInPlace[Person].HeadView.model_fields
    assert (
        SomethingInPlace[Person].HeadView.model_fields["place"].annotation
        is Place.ReferenceView
    )
    assert "target" in SomethingInPlace[Person].HeadView.model_fields
    target_annotation = (
        SomethingInPlace[Person].HeadView.model_fields["target"].annotation
    )
    assert get_origin(target_annotation) is list
    annotated = get_args(target_annotation)[0]

    assert get_origin(annotated) is Annotated

    assert get_args(annotated)[0] is Person.ReferenceView

    assert (
        SomethingInPlace[Person].HeadView.model_fields["meta"].annotation
        is _APIHeadMeta
    )

    assert SomethingInPlace[Person].HeadView._owner is SomethingInPlace[Person]


TEST_META = {
    "created_by": "Me",
    "created_when": datetime.now(),
    "updated_by": "Me",
    "updated_when": datetime.now(),
}


@no_type_check
def test_incoming_relation_simple():
    class Person(Entity):
        pass

    class Statement(Document):
        features_person: Person

    initialise()

    assert "features_person_reverse" in Person.HeadView.model_fields

    assert (
        Person.HeadView.model_fields["features_person_reverse"].annotation
        == list[Statement.ReferenceView]
    )

    p = Person.HeadView(id=uuid7(), label="A Person", meta=TEST_META)

    p2 = Person.HeadView(
        id=uuid7(),
        label="A Person",
        meta=TEST_META,
        features_person_reverse=[
            {"type": "Statement", "id": uuid7(), "label": "A Statement"}
        ],
    )

    assert isinstance(p2.features_person_reverse[0], Statement.ReferenceView)
    assert p2.features_person_reverse[0].label == "A Statement"


@no_type_check
def test_incoming_relation_via_reified():
    class Person(Entity):
        pass

    class Identification[T](ReifiedRelation[T]):
        certainty: int

    class Statement(Document):
        involves_person: Identification[Person]

    initialise()

    assert "involves_person_reverse" in Person.HeadView.model_fields

    involves_person_reverse_annotation = Person.HeadView.model_fields[
        "involves_person_reverse"
    ].annotation

    assert get_origin(involves_person_reverse_annotation) is list

    bound_statement_view = get_args(involves_person_reverse_annotation)[0]
    assert issubclass(bound_statement_view, Statement.View)
    assert "involves_person" in bound_statement_view.model_fields
    assert issubclass(
        bound_statement_view.model_fields["involves_person"].annotation,
        Identification.View,
    )

    identification_view = bound_statement_view.model_fields[
        "involves_person"
    ].annotation

    assert get_origin(identification_view.model_fields["target"].annotation) is list

    annotated = get_args(identification_view.model_fields["target"].annotation)[0]

    assert get_args(annotated)[0] is Person.ReferenceView


def test_incoming_simple_via_embedded():
    class Intermedate[T](ReifiedRelation[T]):
        pass

    class Statement(Document):
        date: Date

    class Date(Embedded):
        date_specific: DateSpecific

    class DateSpecific(Embedded):
        involved_person: Person

    class Person(Entity):
        pass

    initialise()

    involves_person_reverse_annotation = Person.HeadView.model_fields[
        "involved_person_reverse"
    ].annotation

    assert get_origin(involves_person_reverse_annotation) is list
    assert get_args(involves_person_reverse_annotation)[0] is Statement.ReferenceView


def test_incoming_via_reified_in_embedded():
    class Identification[T](ReifiedRelation[T]):
        pass

    class Statement(Document):
        date: Date

    class Date(Embedded):
        date_specific: DateSpecific

    class DateSpecific(Embedded):
        involves_person: Identification[Person]

    class Person(Entity):
        pass

    initialise()

    assert "involves_person_reverse" in Person.HeadView.model_fields

    involves_person_reverse_annotation = Person.HeadView.model_fields[
        "involves_person_reverse"
    ].annotation

    assert get_origin(involves_person_reverse_annotation) is list

    bound_statement_view = get_args(involves_person_reverse_annotation)[0]
    assert issubclass(bound_statement_view, Statement.View)
    assert "involves_person" in bound_statement_view.model_fields

    involves_person_annotation = bound_statement_view.model_fields[
        "involves_person"
    ].annotation
    assert isclass(involves_person_annotation) and issubclass(
        involves_person_annotation,
        Identification.View,
    )

    identification_view = bound_statement_view.model_fields[
        "involves_person"
    ].annotation

    assert isclass(identification_view) and issubclass(
        identification_view, Identification.View
    )

    assert get_origin(identification_view.model_fields["target"].annotation) is list

    annotated = get_args(identification_view.model_fields["target"].annotation)[0]

    assert get_args(annotated)[0] is Person.ReferenceView
