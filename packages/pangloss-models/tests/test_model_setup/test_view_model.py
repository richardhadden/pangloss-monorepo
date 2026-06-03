import datetime
from types import UnionType
from typing import Annotated, Literal, get_args, get_origin, no_type_check
from uuid import uuid7

import pytest
from annotated_types import Gt, MinLen
from pydantic import ValidationError

from pangloss_models import initialise
from pangloss_models.field_definitions import (
    FieldBinding,
    FieldSubclassing,
    ListFieldDefinition,
    LiteralFieldDefinition,
)
from pangloss_models.model_bases.annotated_value import AnnotatedValue
from pangloss_models.model_bases.configs import RelationConfig
from pangloss_models.model_bases.conjunction import (
    Conjunction,
    _ConjunctionViewBase,
)
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.edge_model import EdgeModel
from pangloss_models.model_bases.embedded import Embedded
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.helpers import DBField, Fulfils, ViaEdge
from pangloss_models.model_bases.reified_relation import (
    ReifiedRelation,
    _ReifiedRelationViewBase,
)
from pangloss_models.model_bases.semantic_space import (
    SemanticSpace,
    _SemanticSpaceViewBase,
)
from pangloss_models.model_bases.trait import Trait


@no_type_check
def test_camel_case():
    class Statement(Document):
        some_snake: str

    initialise()

    st = Statement.View(**dict(id=uuid7(), label="A statement", someSnake="hello"))
    assert st.some_snake == "hello"
    assert st.id


@no_type_check
def test_meta_accessible_through_view():
    class Statement(Document):
        some_snake: str

    initialise()

    assert Statement.View._meta is Statement._meta


@no_type_check
def test_type_field_is_correct():
    class Statement(Document):
        pass

    initialise()

    assert Statement.View.model_fields["type"].annotation == Literal["Statement"]


@no_type_check
def test_view_model_for_document_has_id():
    class Statement(Document):
        pass

    initialise()

    assert Statement.View

    assert Statement.View._owner is Statement

    assert "id" in Statement.View.model_fields

    st_id = uuid7()
    st = Statement.View(id=st_id, label="A Statement")
    assert st.label == "A Statement"
    assert st.id == st_id


@no_type_check
def test_view_model_for_entity():
    class Person(Entity):
        pass

    initialise()

    assert Person.View

    assert "id" in Person.View.model_fields
    assert "label" in Person.View.model_fields


@no_type_check
def test_build_base_view_model_for_reified_relation():

    class Identification[TTarget](ReifiedRelation[TTarget]):
        pass

    initialise()

    assert "id" in Identification.View.model_fields


@no_type_check
def test_add_fields_to_document_view_model():
    class Statement(Document):
        name: str
        age: int
        numbers: list[int]

    initialise()

    assert "id" in Statement.View.model_fields
    assert "name" in Statement.View.model_fields
    name_field = Statement.View.model_fields["name"]
    assert name_field.annotation is str

    assert "age" in Statement.View.model_fields
    age_field = Statement.View.model_fields["age"]
    assert age_field.annotation is int

    assert "numbers" in Statement.View.model_fields
    numbers_field = Statement.View.model_fields["numbers"]
    assert numbers_field.annotation == list[int]

    st_id = uuid7()
    st = Statement.View(
        id=st_id, label="A Statement", name="John", age=12, numbers=[1, 2, 3]
    )
    assert st.id == st_id
    assert st.label == "A Statement"
    assert st.name == "John"
    assert st.age == 12
    assert st.numbers == [1, 2, 3]

    with pytest.raises(ValidationError):
        st = Statement.View(
            id=st_id, label="A Statement", name="John", age=12, numbers="WRONG"
        )


@no_type_check
def test_add_simple_relation_from_document_to_entity():

    class Statement(Document):
        was_carried_out_by: Person

    class Person(Entity):
        pass

    initialise()

    assert Statement.View
    assert Statement.View.model_fields["was_carried_out_by"]
    assert (
        Statement.View.model_fields["was_carried_out_by"].annotation
        is Person.ReferenceView
    )


@no_type_check
def test_add_simple_relation_from_document_to_entity_inheriting():

    class Statement(Document):
        was_carried_out_by: Person

    class Person(Entity):
        pass

    class Dude(Person):
        pass

    initialise()

    assert Statement.View
    assert Statement.View.model_fields["was_carried_out_by"]
    assert (
        Statement.View.model_fields["was_carried_out_by"].annotation
        == Person.ReferenceView | Dude.ReferenceView
    )


@no_type_check
def test_add_simple_relation_from_document_to_by_union():

    class Statement(Document):
        was_carried_out_by: Person | Dude

    class Person(Entity):
        pass

    class Dude(Entity):
        pass

    initialise()

    assert Statement.View
    assert Statement.View.model_fields["was_carried_out_by"]
    assert (
        Statement.View.model_fields["was_carried_out_by"].annotation
        == Person.ReferenceView | Dude.ReferenceView
    )
    st_id = uuid7()
    st = Statement.View(
        id=st_id,
        label="A Statement",
        was_carried_out_by={"type": "Dude", "id": uuid7(), "label": "A Dude"},
    )
    assert st.label == "A Statement"
    assert isinstance(st.was_carried_out_by, Dude.ReferenceView)


@no_type_check
def test_add_simple_relation_from_document_to_entity_with_list_wrapper():
    class Statement(Document):
        was_carried_out_by: list[Person]

    class Person(Entity):
        pass

    initialise()

    assert Statement.View
    assert Statement.View.model_fields["was_carried_out_by"]
    annotation = Statement.View.model_fields["was_carried_out_by"].annotation
    assert get_args(get_args(annotation)[0])[0] is Person.ReferenceView

    st = Statement.View(
        id=uuid7(),
        label="A Statement",
        was_carried_out_by=[{"type": "Person", "id": uuid7(), "label": "A Person"}],
    )

    assert isinstance(st.was_carried_out_by, list)
    assert isinstance(st.was_carried_out_by[0], Person.ReferenceView)


@no_type_check
def test_add_simple_relation_from_document_to_entity_via_edge():

    class Statement(Document):
        was_carried_out_by: ViaEdge[Person, Certainty]

    class Person(Entity):
        pass

    class Certainty(EdgeModel):
        pass

    initialise()

    assert Statement.View
    assert Statement.View.model_fields["was_carried_out_by"]
    assert (
        Statement.View.model_fields["was_carried_out_by"].annotation
        is Person.ReferenceView._via.Certainty
    )

    assert set(Person.ReferenceView._via.Certainty.model_fields.keys()) == {
        "edge_properties",
        "id",
        "label",
        "type",
    }


@no_type_check
def test_add_relation_from_document_to_document():
    class Statement(Document):
        action: Action

    class Action(Document):
        pass

    initialise()

    assert "action" in Statement._meta.fields
    assert Statement.View.model_fields["action"]
    assert Statement.View.model_fields["action"].annotation is Action.View


@no_type_check
def test_add_relation_from_document_to_document_via_edge():
    class Statement(Document):
        action: ViaEdge[Action, Certainty]

    class Action(Document):
        pass

    class Certainty(EdgeModel):
        pass

    initialise()

    assert "action" in Statement._meta.fields
    assert Statement.View.model_fields["action"]
    assert (
        Statement.View.model_fields["action"].annotation is Action.View._via.Certainty
    )


@no_type_check
def test_add_self_reference_to_document():
    class DeferredOrder(Document):
        deferred_order: Order

    class Task(Document):
        pass

    class Order(Document):
        thing_ordered: Order | DeferredOrder | Task

    class SubTask(Task):
        pass

    initialise()

    assert (
        Order.View.model_fields["thing_ordered"].annotation
        == Order.View | DeferredOrder.View | Task.View | SubTask.View
    )


@no_type_check
def test_relation_to_entity_via_reified_relation():
    class Identification[TTarget](ReifiedRelation[TTarget]):
        some_value: int

    class Statement(Document):
        is_about_person: Identification[Person]

    class Person(Entity):
        pass

    initialise()

    assert issubclass(Identification.View, _ReifiedRelationViewBase)
    assert Identification.View.model_fields["some_value"].annotation is int

    assert (
        Statement.View.model_fields["is_about_person"].annotation.__name__
        == "Identification[Person]View"
    )

    identification_person_view_model = Statement.View.model_fields[
        "is_about_person"
    ].annotation
    assert issubclass(identification_person_view_model, Identification.View)
    assert identification_person_view_model.model_fields["some_value"].annotation is int
    assert identification_person_view_model._owner is Identification

    target_annotation = identification_person_view_model.model_fields[
        "target"
    ].annotation
    assert get_origin(target_annotation) is list
    assert get_args(get_args(target_annotation)[0])[0] is Person.ReferenceView

    person_id = uuid7()

    st = Statement.View(
        id=uuid7(),
        label="A Statement",
        is_about_person={
            "id": uuid7(),
            "type": "Identification",
            "target": [{"type": "Person", "id": person_id, "label": "A Person"}],
            "some_value": 1,
        },
    )

    assert isinstance(st.is_about_person, identification_person_view_model)
    assert st.is_about_person.target[0].id == person_id


@no_type_check
def test_relation_with_double_reified_relation():
    class WithProxy[TTarget, TProxy](ReifiedRelation[TTarget]):
        proxy: list[TProxy]

    class Identification[T](ReifiedRelation[T]):
        some_value: int

    class Statement(Document):
        is_about_person: WithProxy[Identification[Person], Identification[Person]]

    class Person(Entity):
        pass

    initialise()

    is_about_person_field = Statement.View.model_fields["is_about_person"]
    assert (
        is_about_person_field.annotation.__name__
        == "WithProxy[Identification[Person], Identification[Person]]View"
    )
    assert issubclass(is_about_person_field.annotation, WithProxy.View)
    assert is_about_person_field.annotation.model_fields["target"].annotation
    proxy_target_annotation = is_about_person_field.annotation.model_fields[
        "target"
    ].annotation
    assert get_origin(proxy_target_annotation) is list
    assert get_origin(get_args(proxy_target_annotation)[0]) is Annotated

    proxy_identification_target_annotation = get_args(
        get_args(proxy_target_annotation)[0]
    )[0]
    assert issubclass(proxy_identification_target_annotation, Identification.View)
    assert (
        get_origin(
            proxy_identification_target_annotation.model_fields["target"].annotation
        )
        is list
    )
    assert (
        get_origin(
            get_args(
                proxy_identification_target_annotation.model_fields["target"].annotation
            )[0]
        )
        is Annotated
    )
    assert (
        get_args(
            get_args(
                proxy_identification_target_annotation.model_fields["target"].annotation
            )[0]
        )[0]
        is Person.ReferenceView
    )

    assert is_about_person_field.annotation.model_fields["proxy"].annotation
    proxy_proxy_annotation = is_about_person_field.annotation.model_fields[
        "proxy"
    ].annotation
    assert get_origin(proxy_proxy_annotation) is list
    assert get_origin(get_args(proxy_proxy_annotation)[0]) is Annotated

    proxy_identification_target_annotation = get_args(
        get_args(proxy_proxy_annotation)[0]
    )[0]
    assert issubclass(proxy_identification_target_annotation, Identification.View)
    assert (
        get_origin(
            proxy_identification_target_annotation.model_fields["target"].annotation
        )
        is list
    )
    assert (
        get_origin(
            get_args(
                proxy_identification_target_annotation.model_fields["target"].annotation
            )[0]
        )
        is Annotated
    )
    assert (
        get_args(
            get_args(
                proxy_identification_target_annotation.model_fields["target"].annotation
            )[0]
        )[0]
        is Person.ReferenceView
    )


@no_type_check
def test_relation_with_semantic_space():
    class Negative[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        has_statement: list[Statement | Negative[Statement]]

    class Statement(Document):
        text: str

    initialise()

    statement_field = Factoid.View.model_fields["has_statement"]
    assert statement_field
    assert get_origin(statement_field.annotation) is list
    assert get_origin(get_args(statement_field.annotation)[0]) is Annotated
    # Having peeled away the list and the Annotated...
    type_union = get_args(get_args(statement_field.annotation)[0])[0]
    assert isinstance(type_union, UnionType)
    type_union_items = get_args(type_union)
    assert set(t.__name__ for t in type_union_items) == set(
        ["StatementView", "Negative[Statement]View"]
    )

    Negative_Statement_View: type[_SemanticSpaceViewBase] = [
        c for c in type_union_items if c.__name__ == "Negative[Statement]View"
    ][0]

    assert issubclass(Negative_Statement_View, _SemanticSpaceViewBase)

    f = Factoid.View(
        id=uuid7(),
        label="A Factoid",
        has_statement=[
            {
                "id": uuid7(),
                "type": "Negative",
                "contents": [
                    {
                        "id": uuid7(),
                        "type": "Statement",
                        "label": "Yohoo!",
                        "text": "Woo",
                    }
                ],
            }
        ],
    )

    assert f.label == "A Factoid"
    assert f.has_statement[0].type == "Negative"
    assert isinstance(f.has_statement[0], Negative.View)
    assert f.has_statement[0].contents[0].type == "Statement"
    assert isinstance(f.has_statement[0].contents[0], Statement.View)


@no_type_check
def test_relation_with_conjunction():
    class Causes[TCause, TResult](Conjunction):
        cause: TCause
        result: TResult

    class Statement(Document):
        pass

    class Factoid(Document):
        has_statements: Statement | Causes[Statement, Statement]

    initialise()

    # Check that Factoid.Create has the has_statements field
    assert "has_statements" in Factoid.View.model_fields

    # Check the annotation is a Union
    has_statements_field = Factoid.View.model_fields["has_statements"]
    assert has_statements_field
    annotation = has_statements_field.annotation

    assert isinstance(annotation, UnionType)
    union_items = get_args(annotation)
    assert len(union_items) == 2
    assert set(t.__name__ for t in union_items) == {
        "StatementView",
        "Causes[Statement, Statement]View",
    }

    # Check that Causes has a Create model
    assert hasattr(Causes, "View")
    assert issubclass(Causes.View, _ConjunctionViewBase)

    # Check that the specialized Causes[Statement, Statement] has a Create model

    causes_statement_view = [
        item
        for item in union_items
        if item.__name__ == "Causes[Statement, Statement]View"
    ][0]  # The Causes[Statement, Statement]View
    assert issubclass(causes_statement_view, Causes.View)
    assert "cause" in causes_statement_view.model_fields
    assert "result" in causes_statement_view.model_fields
    assert causes_statement_view.model_fields["cause"].annotation == Statement.View
    assert causes_statement_view.model_fields["result"].annotation == Statement.View

    # Create an instance with a Statement
    f1 = Factoid.View(
        id=uuid7(),
        label="A Factoid",
        has_statements={
            "id": uuid7(),
            "type": "Statement",
            "label": "A Statement",
        },
    )
    assert f1.label == "A Factoid"
    assert f1.has_statements.type == "Statement"
    assert isinstance(f1.has_statements, Statement.View)

    # Create an instance with a Causes conjunction
    f2 = Factoid.View(
        id=uuid7(),
        label="Another Factoid",
        has_statements={
            "id": uuid7(),
            "type": "Causes",
            "cause": {
                "id": uuid7(),
                "type": "Statement",
                "label": "Cause Statement",
            },
            "result": {
                "id": uuid7(),
                "type": "Statement",
                "label": "Result Statement",
            },
        },
    )
    assert f2.label == "Another Factoid"
    assert f2.has_statements.type == "Causes"
    assert isinstance(f2.has_statements, causes_statement_view)
    assert f2.has_statements.cause.type == "Statement"
    assert isinstance(f2.has_statements.cause, Statement.View)
    assert f2.has_statements.result.type == "Statement"
    assert isinstance(f2.has_statements.result, Statement.View)


@no_type_check
def test_relation_to_trait():
    class Agent(Trait):
        pass

    class Person(Entity, Agent):
        pass

    class Group(Entity, Agent):
        pass

    class Posse(Group):
        pass

    class Organisation(Entity, Agent):
        pass

    class Statement(Document):
        thing_carried_out_by: Agent

    initialise()

    thing_carried_out_by_field = Statement.View.model_fields["thing_carried_out_by"]
    assert (
        thing_carried_out_by_field.annotation
        == Person.ReferenceView
        | Group.ReferenceView
        | Organisation.ReferenceView
        | Posse.ReferenceView
    )

    st = Statement.View(
        id=uuid7(),
        label="A Statement",
        thing_carried_out_by={"type": "Group", "id": uuid7(), "label": "A Group"},
    )


@no_type_check
def test_relation_to_embedded():
    class Date(Embedded):
        when: datetime.datetime

    class Statement(Document):
        date: Date

    initialise()

    assert Date.View.model_fields["when"].annotation is datetime.datetime
    assert Date.View.model_fields["type"].annotation == Literal["Date"]

    assert Statement._meta.fields["date"]

    assert Statement.View.model_fields["date"]

    st = Statement.View(
        id=uuid7(),
        label="A Statement",
        date={"type": "Date", "when": "2019-01-01", "id": uuid7()},
    )

    assert st.label == "A Statement"
    assert isinstance(st.date, Date.View)
    assert st.date.type == "Date"
    assert isinstance(st.date.when, datetime.datetime)
    assert st.date.when == datetime.datetime(2019, 1, 1)


@no_type_check
def test_annotated_value():
    class WithCertainty[T](AnnotatedValue[T]):
        certainty: int

    class Naming(Document):
        name: WithCertainty[str]

    initialise()

    assert WithCertainty[str].model_fields["value"].annotation is str

    assert Naming.View.model_fields["name"].annotation == WithCertainty[str]


@no_type_check
def test_db_field_not_in_view_model():

    class Statement(Document):
        some_field: int
        db_int_field: Annotated[int, DBField]
        person_field: Person
        db_person_field: Annotated[Person, DBField]
        embedded_field: Date
        db_embedded_field: Annotated[Date, DBField]

    class Person(Entity):
        pass

    class Date(Embedded):
        pass

    initialise()

    assert "some_field" in Statement.View.model_fields
    assert "db_int_field" not in Statement.View.model_fields
    assert "person_field" in Statement.View.model_fields
    assert "db_person_field" not in Statement.View.model_fields
    assert "embedded_field" in Statement.View.model_fields
    assert "db_embedded_field" not in Statement.View.model_fields


@no_type_check
def test_inherited_from_fulfils_is_optional():
    class PersonInPlace(Document):
        located_person: Person
        place: Place

    class Activity(Document, Fulfils[PersonInPlace]):
        person_responsible: Annotated[
            Person,
            RelationConfig(
                subclasses_parent_fields=[
                    FieldSubclassing("located_person", field_on_model=PersonInPlace)
                ]
            ),
        ]

    class Person(Entity):
        pass

    class Place(Entity):
        pass

    initialise()

    assert (
        Activity.View.model_fields["person_responsible"].annotation
        is Person.ReferenceView
    )

    assert Activity.View.model_fields["place"].annotation == Place.ReferenceView | None


"""Tests fixed up to here"""


@no_type_check
def test_literal_validators():
    class Factoid(Document):
        number: Annotated[
            int,
            Gt(1),
        ]

    initialise()

    statements_field = Factoid._meta.fields["number"]
    assert isinstance(statements_field, LiteralFieldDefinition)

    assert statements_field.validators == [Gt(1)]

    assert Factoid.View.model_fields["number"]
    assert Factoid.View.model_fields["number"].metadata == [Gt(1)]

    with pytest.raises(ValidationError):
        Factoid.View(id=uuid7(), label="A Factoid", number=1)


@no_type_check
def test_list_validators():
    class Factoid(Document):
        numbers: Annotated[list[Annotated[int, Gt(1)]], MinLen(1)]

    initialise()

    statements_field = Factoid._meta.fields["numbers"]
    assert isinstance(statements_field, ListFieldDefinition)

    assert statements_field.validators == [MinLen(1)]
    assert statements_field.inner_type_validators == [Gt(1)]

    assert Factoid.View.model_fields["numbers"]
    assert Factoid.View.model_fields["numbers"].metadata == [MinLen(1)]

    with pytest.raises(ValidationError):
        Factoid.View(id=uuid7(), label="A Factoid", numbers=[])

    with pytest.raises(ValidationError):
        Factoid.View(id=uuid7(), label="A Factoid", numbers=[1])

    Factoid.View(id=uuid7(), label="A Factoid", numbers=[2, 2, 2])


@no_type_check
def test_meta_on_view_model():
    class Statement(Document):
        pass

    initialise()

    st = Statement.View(
        id=uuid7(),
        label="A Statement",
        meta={
            "semantic_spaces": ["Negative"],
            "semantic_space_labels": ["Order -> Negative"],
        },
    )

    assert st.meta.semantic_spaces == ["Negative"]
    assert st.meta.semantic_space_labels == ["Order -> Negative"]
