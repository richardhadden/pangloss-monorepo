import datetime
from inspect import isclass
from types import UnionType
from typing import (
    Annotated,
    Literal,
    NamedTuple,
    Union,
    get_args,
    get_origin,
    no_type_check,
)
from uuid import UUID, uuid7

import pytest
from annotated_types import Gt, MinLen
from pydantic import AnyHttpUrl, ValidationError

from pangloss_models import initialise
from pangloss_models.exceptions import PanglossMetaError
from pangloss_models.field_definitions import (
    FieldBinding,
    FieldSubclassing,
    ListFieldDefinition,
    LiteralFieldDefinition,
    RelationFieldDefinition,
)
from pangloss_models.model_bases.annotated_value import AnnotatedValue
from pangloss_models.model_bases.configs import RelationConfig
from pangloss_models.model_bases.conjunction import (
    Conjunction,
    _ConjunctionCreateBase,
    _ConjunctionUpdateBase,
)
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.edge_model import EdgeModel
from pangloss_models.model_bases.embedded import Embedded
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.helpers import DBField, Fulfils, ViaEdge
from pangloss_models.model_bases.reified_relation import (
    ReifiedRelation,
    ReifiedRelationDocument,
    _ReifiedRelationCreateBase,
    _ReifiedRelationUpdateBase,
)
from pangloss_models.model_bases.semantic_space import (
    SemanticSpace,
    _SemanticSpaceCreateBase,
    _SemanticSpaceUpdateBase,
)
from pangloss_models.model_bases.trait import Trait


def test_document_has_update_model():
    class Statement(Document):
        pass

    initialise()

    assert Statement.Update
    for field_name in {"id", "label", "type"}:
        assert field_name in Statement.Update.model_fields

    assert Statement.Update.model_fields["type"].annotation == Literal["Statement"]


def test_entity_has_update_model():
    class Person(Entity):
        pass

    initialise()

    assert Person.Update
    for field_name in {"id", "label", "type"}:
        assert field_name in Person.Update.model_fields

    assert Person.Update.model_fields["type"].annotation == Literal["Person"]


def test_conjunction_has_update_model():

    class Alternative[T](Conjunction):
        pass

    class Person(Entity):
        pass

    initialise()

    assert Alternative.Update

    assert Alternative[Person].Update

    for field_name in {"id", "type"}:
        assert field_name in Alternative.Update.model_fields

    assert Alternative.Update.model_fields["type"].annotation == Literal["Alternative"]
    assert (
        Alternative[Person].Update.model_fields["type"].annotation
        == Literal["Alternative"]
    )


def test_reified_relation_has_update_model():

    class Identification[T](ReifiedRelation[T]):
        pass

    class Person(Entity):
        pass

    initialise()

    assert Identification.Update
    assert Identification[Person].Update

    for field_name in {"id", "type"}:
        assert field_name in Identification.Update.model_fields
        assert field_name in Identification[Person].Update.model_fields

    assert (
        Identification.Update.model_fields["type"].annotation
        == Literal["Identification"]
    )

    assert (
        Identification[Person].Update.model_fields["type"].annotation
        == Literal["Identification"]
    )


def test_reified_relation_document_has_update_model():
    class PersonInPlace[T](ReifiedRelationDocument[T]):
        pass

    class Person(Entity):
        pass

    initialise()

    assert PersonInPlace.Update

    assert PersonInPlace[Person].Update

    for field_name in {"id", "type"}:
        assert field_name in PersonInPlace.Update.model_fields
        assert field_name in PersonInPlace[Person].Update.model_fields

    assert (
        PersonInPlace.Update.model_fields["type"].annotation == Literal["PersonInPlace"]
    )
    assert (
        PersonInPlace[Person].Update.model_fields["type"].annotation
        == Literal["PersonInPlace"]
    )


def test_semantic_space_has_update_model():

    class Negative[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    initialise()

    assert Negative.Update
    assert Negative[Action].Update

    for field_name in {"id", "type"}:
        assert field_name in Negative.Update.model_fields
        assert field_name in Negative[Action].Update.model_fields

    assert Negative.Update.model_fields["type"].annotation == Literal["Negative"]
    assert (
        Negative[Action].Update.model_fields["type"].annotation == Literal["Negative"]
    )


def test_literal_field_on_update_model():
    class Statement(Document):
        number: int

    class Dude(Entity):
        name: str

    initialise()

    assert Statement.Update.model_fields["number"]
    assert Statement.Update.model_fields["number"].annotation is int

    assert Dude.Update.model_fields["name"]
    assert Dude.Update.model_fields["name"].annotation is str


@no_type_check
def test_relation_to_embedded():
    class Date(Embedded):
        when: datetime.datetime

    class Other(Date):
        when: datetime.datetime

    class Statement(Document):
        date: Date

    initialise()

    assert Date.Update.model_fields["when"].annotation is datetime.datetime
    assert Date.Update.model_fields["type"].annotation == Literal["Date"]

    assert Statement._meta.fields["date"]

    assert Statement.Create.model_fields["date"]
    assert (
        Statement.Create.model_fields["date"].annotation == Date.Create | Other.Create
    )

    st_update = Statement.Update(
        id=uuid7(), label="A Statement", date={"type": "Date", "when": "2019-01-01"}
    )

    assert isinstance(st_update.date, Date.Create)

    st_update2 = Statement.Update(
        id=uuid7(),
        label="A Statement",
        date={"id": uuid7(), "type": "Date", "when": "2019-01-01"},
    )

    assert isinstance(st_update2.date, Date.Update)

    st_update3 = Statement.Update(
        id=uuid7(),
        label="A Statement",
        date={"id": uuid7(), "type": "Other", "when": "2019-01-01"},
    )

    assert isinstance(st_update3.date, Other.Update)


@no_type_check
def test_camel_case():
    class Statement(Document):
        some_snake: str

    initialise()

    st = Statement.Update(**dict(id=uuid7(), label="A statement", someSnake="hello"))
    assert st.some_snake == "hello"


@no_type_check
def test_meta_accessible_through_update():
    class Statement(Document):
        some_snake: str

    initialise()

    assert Statement.Update._meta is Statement._meta


@no_type_check
def test_type_field_is_correct():
    class Statement(Document):
        pass

    initialise()

    assert Statement.Update.model_fields["type"].annotation == Literal["Statement"]


@no_type_check
def test_update_model_for_document_with_no_id():
    class Statement(Document):
        pass

    initialise()

    assert Statement.Update

    assert Statement.Update._owner is Statement

    assert "id" in Statement.Update.model_fields

    uuid_value = uuid7()

    st = Statement.Update(id=uuid_value, label="A Statement")
    assert st.label == "A Statement"
    assert st.id == uuid_value


@no_type_check
def test_add_fields_to_document_update_model():
    class Statement(Document):
        name: str
        age: int
        numbers: list[int]

    initialise()

    assert "name" in Statement.Update.model_fields
    name_field = Statement.Update.model_fields["name"]
    assert name_field.annotation is str

    assert "age" in Statement.Update.model_fields
    age_field = Statement.Update.model_fields["age"]
    assert age_field.annotation is int

    assert "numbers" in Statement.Update.model_fields
    numbers_field = Statement.Update.model_fields["numbers"]
    assert numbers_field.annotation == list[int]

    st = Statement.Update(
        id=uuid7(), label="A Statement", name="John", age=12, numbers=[1, 2, 3]
    )
    assert st.label == "A Statement"
    assert st.name == "John"
    assert st.age == 12
    assert st.numbers == [1, 2, 3]

    with pytest.raises(ValidationError):
        st = Statement.Update(
            id=uuid7(), label="A Statement", name="John", age=12, numbers="WRONG"
        )


@no_type_check
def test_add_simple_relation_from_document_to_entity():

    class Statement(Document):
        was_carried_out_by: Person

    class Person(Entity):
        pass

    initialise()

    assert Statement.Update
    assert Statement.Update.model_fields["was_carried_out_by"]
    assert (
        Statement.Update.model_fields["was_carried_out_by"].annotation
        is Person.ReferenceSet
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

    assert Statement.Update
    assert Statement.Update.model_fields["was_carried_out_by"]
    assert (
        Statement.Update.model_fields["was_carried_out_by"].annotation
        == Person.ReferenceSet | Dude.ReferenceSet
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

    assert Statement.Update
    assert Statement.Update.model_fields["was_carried_out_by"]
    assert (
        Statement.Update.model_fields["was_carried_out_by"].annotation
        == Person.ReferenceSet | Dude.ReferenceSet
    )

    st = Statement.Create(
        label="A Statement", was_carried_out_by={"type": "Dude", "id": uuid7()}
    )
    assert st.label == "A Statement"
    assert isinstance(st.was_carried_out_by, Dude.ReferenceSet)


@no_type_check
def test_add_simple_relation_from_document_to_entity_with_list_wrapper():
    class Statement(Document):
        was_carried_out_by: list[Person]

    class Person(Entity):
        pass

    initialise()

    assert Statement.Update
    assert Statement.Update.model_fields["was_carried_out_by"]
    annotation = Statement.Update.model_fields["was_carried_out_by"].annotation
    assert get_args(get_args(annotation)[0])[0] is Person.ReferenceSet

    st = Statement.Update(
        id=uuid7(),
        label="A Statement",
        was_carried_out_by=[{"type": "Person", "id": uuid7()}],
    )

    assert isinstance(st.was_carried_out_by, list)
    assert isinstance(st.was_carried_out_by[0], Person.ReferenceSet)


@no_type_check
def test_add_simple_relation_from_document_to_entity_via_edge():

    class Statement(Document):
        was_carried_out_by: ViaEdge[Person, Certainty]

    class Person(Entity):
        pass

    class Certainty(EdgeModel):
        pass

    initialise()

    assert Statement.Update
    assert Statement.Update.model_fields["was_carried_out_by"]
    assert (
        Statement.Update.model_fields["was_carried_out_by"].annotation
        is Person.ReferenceSet._via.Certainty
    )

    assert set(Person.ReferenceSet._via.Certainty.model_fields.keys()) == {
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
    assert Statement.Update.model_fields["action"]
    assert (
        Statement.Update.model_fields["action"].annotation
        == Action.Create | Action.Update
    )


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
    assert Statement.Update.model_fields["action"]
    assert (
        Statement.Update.model_fields["action"].annotation
        == Action.Create._via.Certainty | Action.Update._via.Certainty
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
        Order.Update.model_fields["thing_ordered"].annotation
        == Order.Create
        | DeferredOrder.Create
        | Task.Create
        | SubTask.Create
        | Order.Update
        | DeferredOrder.Update
        | Task.Update
        | SubTask.Update
    )


"""Testing up to here"""


@no_type_check
def test_relation_to_entity_via_reified_relation():
    class Identification[TTarget](ReifiedRelation[TTarget]):
        some_value: int

    class Statement(Document):
        is_about_person: Identification[Person]

    class Person(Entity):
        pass

    initialise()

    assert issubclass(Identification.Update, _ReifiedRelationUpdateBase)
    assert Identification.Update.model_fields["some_value"].annotation is int

    statement_update_is_about_person_annotation = Statement.Update.model_fields[
        "is_about_person"
    ].annotation

    args = get_args(statement_update_is_about_person_annotation)
    assert args[0].__name__ == "Identification[Person]Update"
    assert args[1].__name__ == "Identification[Person]Create"

    assert issubclass(args[0], Identification.Update)
    assert issubclass(args[1], Identification.Create)

    identification_person_update_model = args[0]

    assert (
        identification_person_update_model.model_fields["some_value"].annotation is int
    )

    assert identification_person_update_model._owner is Identification

    target_annotation = identification_person_update_model.model_fields[
        "target"
    ].annotation
    assert get_origin(target_annotation) is list
    assert get_args(get_args(target_annotation)[0])[0] is Person.ReferenceSet

    statement_uuid = uuid7()
    person_uuid = uuid7()
    is_about_person_identification_id = uuid7()

    st = Statement.Update(
        id=statement_uuid,
        label="A Statement",
        is_about_person={
            "id": is_about_person_identification_id,
            "type": "Identification",
            "target": [{"type": "Person", "id": person_uuid}],
            "some_value": 1,
        },
    )

    assert isinstance(st.is_about_person, identification_person_update_model)
    assert st.is_about_person.target[0].id == person_uuid


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

    is_about_person_field = Statement.Update.model_fields["is_about_person"]
    is_about_person_field_annotation = is_about_person_field.annotation

    assert get_origin(is_about_person_field_annotation) == Union
    is_about_person_args = get_args(is_about_person_field_annotation)

    assert issubclass(is_about_person_args[0], WithProxy.Update)
    assert issubclass(is_about_person_args[1], WithProxy.Create)

    is_about_person_args_0_target_annotation = (
        is_about_person_args[0].model_fields["target"].annotation
    )
    assert get_origin(is_about_person_args_0_target_annotation) is list

    is_about_person_args_0_target_annotation_args = get_args(
        is_about_person_args_0_target_annotation
    )[0]
    assert get_origin(is_about_person_args_0_target_annotation_args) is Annotated
    is_about_person_args_0_target_annotation_args_0 = get_args(
        is_about_person_args_0_target_annotation_args
    )[0]
    assert get_origin(is_about_person_args_0_target_annotation_args_0) == Union

    (
        is_about_person_args_0_target_annotation_args_0_args_0,
        is_about_person_args_0_target_annotation_args_0_args_1,
    ) = get_args(is_about_person_args_0_target_annotation_args_0)

    assert (
        is_about_person_args_0_target_annotation_args_0_args_0.__name__
        == "Identification[Person]Update"
    )

    assert (
        get_origin(
            is_about_person_args_0_target_annotation_args_0_args_0.model_fields[
                "target"
            ].annotation
        )
        is list
    )

    assert (
        get_origin(
            get_args(
                is_about_person_args_0_target_annotation_args_0_args_0.model_fields[
                    "target"
                ].annotation
            )[0]
        )
        == Annotated
    )

    assert (
        get_args(
            get_args(
                is_about_person_args_0_target_annotation_args_0_args_0.model_fields[
                    "target"
                ].annotation
            )[0]
        )[0]
        is Person.ReferenceSet
    )

    assert (
        is_about_person_args_0_target_annotation_args_0_args_1.__name__
        == "Identification[Person]Create"
    )

    is_about_person_args_0_proxy_annotation = (
        is_about_person_args[0].model_fields["proxy"].annotation
    )
    assert get_origin(is_about_person_args_0_proxy_annotation) is list

    is_about_person_args_0_proxy_annotation_args = get_args(
        is_about_person_args_0_proxy_annotation
    )[0]
    assert get_origin(is_about_person_args_0_target_annotation_args) is Annotated
    is_about_person_args_0_proxy_annotation_args_0 = get_args(
        is_about_person_args_0_proxy_annotation_args
    )[0]
    assert get_origin(is_about_person_args_0_proxy_annotation_args_0) == Union

    (
        is_about_person_args_0_proxy_annotation_args_0_args_0,
        is_about_person_args_0_proxy_annotation_args_0_args_1,
    ) = get_args(is_about_person_args_0_proxy_annotation_args_0)

    assert (
        is_about_person_args_0_proxy_annotation_args_0_args_0.__name__
        == "Identification[Person]Update"
    )

    assert (
        get_origin(
            is_about_person_args_0_proxy_annotation_args_0_args_0.model_fields[
                "target"
            ].annotation
        )
        is list
    )

    assert (
        get_origin(
            get_args(
                is_about_person_args_0_proxy_annotation_args_0_args_0.model_fields[
                    "target"
                ].annotation
            )[0]
        )
        == Annotated
    )

    assert (
        get_args(
            get_args(
                is_about_person_args_0_proxy_annotation_args_0_args_0.model_fields[
                    "target"
                ].annotation
            )[0]
        )[0]
        is Person.ReferenceSet
    )

    assert (
        is_about_person_args_0_proxy_annotation_args_0_args_1.__name__
        == "Identification[Person]Create"
    )

    st_update = Statement.Update(
        **{
            "type": "Statement",
            "label": "A Statement",
            "id": uuid7(),
            "is_about_person": {
                "type": "WithProxy",
                "target": [
                    {
                        "type": "Identification",
                        "target": [
                            {"type": "Person", "id": uuid7()},
                        ],
                        "some_value": 1,
                    }
                ],
                "proxy": [
                    {
                        "type": "Identification",
                        "target": [
                            {"type": "Person", "id": uuid7()},
                        ],
                        "some_value": 1,
                    }
                ],
            },
        }
    )

    assert isinstance(st_update.is_about_person, WithProxy.Create)
    assert isinstance(st_update.is_about_person.target[0], Identification.Create)
    assert isinstance(st_update.is_about_person.proxy[0], Identification.Create)

    st_update2 = Statement.Update(
        **{
            "type": "Statement",
            "label": "A Statement",
            "id": uuid7(),
            "is_about_person": {
                "type": "WithProxy",
                "id": uuid7(),
                "target": [
                    {
                        "type": "Identification",
                        "target": [
                            {"type": "Person", "id": uuid7()},
                        ],
                        "some_value": 1,
                    }
                ],
                "proxy": [
                    {
                        "type": "Identification",
                        "target": [
                            {"type": "Person", "id": uuid7()},
                        ],
                        "some_value": 1,
                    }
                ],
            },
        }
    )

    assert isinstance(st_update2.is_about_person, WithProxy.Update)
    assert isinstance(st_update2.is_about_person.target[0], Identification.Create)
    assert isinstance(st_update2.is_about_person.proxy[0], Identification.Create)

    st_update3 = Statement.Update(
        **{
            "type": "Statement",
            "label": "A Statement",
            "id": uuid7(),
            "is_about_person": {
                "type": "WithProxy",
                "id": uuid7(),
                "target": [
                    {
                        "type": "Identification",
                        "id": uuid7(),
                        "target": [
                            {"type": "Person", "id": uuid7()},
                        ],
                        "some_value": 1,
                    }
                ],
                "proxy": [
                    {
                        "type": "Identification",
                        "target": [
                            {"type": "Person", "id": uuid7()},
                        ],
                        "some_value": 1,
                    }
                ],
            },
        }
    )

    assert isinstance(st_update3.is_about_person, WithProxy.Update)
    assert isinstance(st_update3.is_about_person.target[0], Identification.Update)
    assert isinstance(st_update3.is_about_person.proxy[0], Identification.Create)


@no_type_check
def test_relation_with_semantic_space():
    class Negative[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        has_statement: list[Statement | Negative[Statement]]

    class Statement(Document):
        text: str

    initialise()

    statement_field = Factoid.Update.model_fields["has_statement"]
    assert statement_field
    assert get_origin(statement_field.annotation) is list

    assert get_origin(get_args(statement_field.annotation)[0]) is Annotated

    # Having peeled away the list and the Annotated...
    type_union = get_args(get_args(statement_field.annotation)[0])[0]
    assert isinstance(type_union, UnionType)

    type_union_items = get_args(type_union)
    assert set(t.__name__ for t in type_union_items) == set(
        [
            "StatementCreate",
            "Negative[Statement]Create",
            "Negative[Statement]Update",
            "StatementUpdate",
        ]
    )

    Negative_Statement_Update: type[_SemanticSpaceUpdateBase] = [
        c for c in type_union_items if c.__name__ == "Negative[Statement]Update"
    ][0]

    assert issubclass(Negative_Statement_Update, _SemanticSpaceUpdateBase)

    f = Factoid.Update(
        label="A Factoid",
        id=uuid7(),
        has_statement=[
            {
                "type": "Negative",
                "contents": [
                    {
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
    assert isinstance(f.has_statement[0], Negative.Create)
    assert f.has_statement[0].contents[0].type == "Statement"
    assert isinstance(f.has_statement[0].contents[0], Statement.Create)

    f2 = Factoid.Update(
        label="A Factoid",
        id=uuid7(),
        has_statement=[
            {
                "id": uuid7(),
                "type": "Negative",
                "contents": [
                    {
                        "type": "Statement",
                        "label": "Yohoo!",
                        "text": "Woo",
                    }
                ],
            }
        ],
    )

    assert f2.label == "A Factoid"
    assert f2.has_statement[0].type == "Negative"
    assert isinstance(f2.has_statement[0], Negative.Update)
    assert f2.has_statement[0].contents[0].type == "Statement"
    assert isinstance(f2.has_statement[0].contents[0], Statement.Create)

    f3 = Factoid.Update(
        label="A Factoid",
        id=uuid7(),
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

    assert f3.label == "A Factoid"
    assert f3.has_statement[0].type == "Negative"
    assert isinstance(f3.has_statement[0], Negative.Update)
    assert f3.has_statement[0].contents[0].type == "Statement"
    assert isinstance(f3.has_statement[0].contents[0], Statement.Update)


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
    assert "has_statements" in Factoid.Update.model_fields

    # Check the annotation is a Union
    has_statements_field = Factoid.Update.model_fields["has_statements"]
    assert has_statements_field
    annotation = has_statements_field.annotation

    assert isinstance(annotation, UnionType)

    union_items = get_args(annotation)
    assert len(union_items) == 4

    assert set(t.__name__ for t in union_items) == {
        "StatementCreate",
        "StatementUpdate",
        "Causes[Statement, Statement]Create",
        "Causes[Statement, Statement]Update",
    }

    # Check that Causes has a Create model
    assert hasattr(Causes, "Update")
    assert issubclass(Causes.Update, _ConjunctionUpdateBase)

    # Check that the specialized Causes[Statement, Statement] has a Create model

    causes_statement_update = [
        item
        for item in union_items
        if item.__name__ == "Causes[Statement, Statement]Update"
    ][0]  # The Causes[Statement, Statement]Create
    assert issubclass(causes_statement_update, Causes.Update)
    assert "cause" in causes_statement_update.model_fields
    assert "result" in causes_statement_update.model_fields
    assert (
        causes_statement_update.model_fields["cause"].annotation
        == Statement.Create | Statement.Update
    )
    assert (
        causes_statement_update.model_fields["result"].annotation
        == Statement.Create | Statement.Update
    )

    # Create an instance with a Statement
    f1 = Factoid.Update(
        id=uuid7(),
        label="A Factoid",
        has_statements={
            "type": "Statement",
            "label": "A Statement",
        },
    )
    assert f1.label == "A Factoid"
    assert f1.has_statements.type == "Statement"
    assert isinstance(f1.has_statements, Statement.Create)

    f2 = Factoid.Update(
        id=uuid7(),
        label="A Factoid",
        has_statements={
            "id": uuid7(),
            "type": "Statement",
            "label": "A Statement",
        },
    )
    assert f2.label == "A Factoid"
    assert f2.has_statements.type == "Statement"
    assert isinstance(f2.has_statements, Statement.Update)

    # Create an instance with a Causes conjunction
    f3 = Factoid.Update(
        id=uuid7(),
        label="Another Factoid",
        has_statements={
            "id": uuid7(),
            "type": "Causes",
            "cause": {
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
    assert f3.label == "Another Factoid"
    assert f3.has_statements.type == "Causes"
    assert isinstance(f3.has_statements, causes_statement_update)
    assert f3.has_statements.cause.type == "Statement"
    assert isinstance(f3.has_statements.cause, Statement.Create)
    assert f3.has_statements.result.type == "Statement"
    assert isinstance(f3.has_statements.result, Statement.Update)


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

    thing_carried_out_by_field = Statement.Update.model_fields["thing_carried_out_by"]
    assert (
        thing_carried_out_by_field.annotation
        == Person.ReferenceSet
        | Group.ReferenceSet
        | Organisation.ReferenceSet
        | Posse.ReferenceSet
    )

    st = Statement(
        label="A Statement", thing_carried_out_by={"type": "Group", "id": uuid7()}
    )


@no_type_check
def test_annotated_value():
    class WithCertainty[T](AnnotatedValue[T]):
        certainty: int

    class Naming(Document):
        name: WithCertainty[str]

    initialise()

    assert WithCertainty[str].model_fields["value"].annotation is str

    assert Naming.Update.model_fields["name"].annotation == WithCertainty[str]


@no_type_check
def test_db_field_not_in_update_model():

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

    assert "some_field" in Statement.Update.model_fields
    assert "db_int_field" not in Statement.Update.model_fields
    assert "person_field" in Statement.Update.model_fields
    assert "db_person_field" not in Statement.Update.model_fields
    assert "embedded_field" in Statement.Update.model_fields
    assert "db_embedded_field" not in Statement.Update.model_fields


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
        Activity.Update.model_fields["person_responsible"].annotation
        is Person.ReferenceSet
    )

    assert Activity.Update.model_fields["place"].annotation == Place.ReferenceSet | None


def test_update_model_with_field_binding():
    class Action(Document):
        action_when: datetime.date
        action_when_optional: datetime.date | None

    class Statement(Document):
        when: datetime.date
        action: Annotated[
            Action,
            RelationConfig(
                bind_to_child_field=[
                    FieldBinding(
                        bound_field="when",
                        child_fields=["action_when", "action_when_optional"],
                        allowed_type_names=["Action"],
                    )
                ]
            ),
        ]

    initialise()

    action_annotation = Statement.Update.model_fields["action"].annotation
    assert isinstance(action_annotation, UnionType)
    action_annotation_update, action_annotation_create = get_args(action_annotation)

    assert isclass(action_annotation_update) and issubclass(
        action_annotation_update, Action.Update
    )
    assert isclass(action_annotation_create) and issubclass(
        action_annotation_create, Action.Create
    )

    assert (
        action_annotation_update.model_fields["action_when"].annotation
        == datetime.date | None
    )
    assert (
        action_annotation_update.model_fields["action_when_optional"].annotation
        == datetime.date | None
    )


@no_type_check
def test_update_model_with_field_binding_through_intermediate():

    class Action(Document):
        action_when: datetime.date

    class Negative[T](SemanticSpace[T]):
        pass

    class Statement(Document):
        when: datetime.date
        action: Annotated[
            Negative[Action],
            RelationConfig(
                bind_to_child_field=[
                    FieldBinding(
                        bound_field="when",
                        child_fields=["action_when"],
                        allowed_type_names=["Action"],
                    )
                ]
            ),
        ]

    initialise()

    negative_annotation = Statement.Update.model_fields["action"].annotation
    assert isinstance(negative_annotation, UnionType)
    negative_annotation_update, negative_annotation_create = get_args(
        negative_annotation
    )
    assert isclass(negative_annotation_create) and issubclass(
        negative_annotation_create, Negative.Create
    )
    assert isclass(negative_annotation_update) and issubclass(
        negative_annotation_update, Negative.Update
    )
    negative_contents_fields = negative_annotation_update.model_fields["contents"]
    assert get_origin(negative_contents_fields.annotation) is list
    annotated_action_model = get_args(negative_contents_fields.annotation)[0]

    assert get_origin(annotated_action_model) is Annotated
    action_model_union = get_args(annotated_action_model)[0]
    assert action_model_union

    assert isinstance(action_model_union, UnionType)
    action_create, action_update = get_args(action_model_union)
    assert isclass(action_create) and issubclass(action_create, Action.Create)
    assert isclass(action_update) and issubclass(action_update, Action.Update)

    assert action_update.model_fields["action_when"].annotation == datetime.date | None

    st = Statement.Update(
        id=uuid7(),
        label="A Statement",
        when=datetime.date.today(),
        action={
            "type": "Negative",
            "contents": [
                {
                    "type": "Action",
                    "label": "An action",
                }
            ],
        },
    )

    assert st.action.contents[0].action_when == datetime.date.today()


@no_type_check
def test_update_model_with_field_binding_through_intermediate_with_transform():

    class Action(Document):
        action_when: datetime.date

    class Negative[T](SemanticSpace[T]):
        pass

    class Statement(Document):
        when: datetime.date
        action: Annotated[
            Negative[Action],
            RelationConfig(
                bind_to_child_field=[
                    FieldBinding(
                        bound_field="when",
                        child_fields=["action_when"],
                        allowed_type_names=["Action"],
                        converter=lambda x: x + datetime.timedelta(days=1),
                    )
                ]
            ),
        ]

    initialise()

    action_annotation = Statement.Update.model_fields["action"].annotation
    assert isinstance(action_annotation, UnionType)

    bound_negative_update, bound_negative_create = get_args(action_annotation)
    assert isclass(bound_negative_create) and issubclass(
        bound_negative_create, Negative.Create
    )
    assert isclass(bound_negative_update) and issubclass(
        bound_negative_update, Negative.Update
    )

    negative_contents_fields = bound_negative_update.model_fields["contents"]
    assert get_origin(negative_contents_fields.annotation) is list
    annotated_action_model = get_args(negative_contents_fields.annotation)[0]

    assert get_origin(annotated_action_model) is Annotated

    bound_action_union = get_args(annotated_action_model)[0]
    assert isinstance(bound_action_union, UnionType)
    bound_action_create, bound_action_update = get_args(bound_action_union)

    assert isclass(bound_action_create) and issubclass(
        bound_action_create, Action.Create
    )

    assert isclass(bound_action_update) and issubclass(
        bound_action_update, Action.Update
    )

    assert (
        bound_action_create.model_fields["action_when"].annotation
        == datetime.date | None
    )
    assert (
        bound_action_update.model_fields["action_when"].annotation
        == datetime.date | None
    )

    st = Statement.Update(
        id=uuid7(),
        label="A Statement",
        when=datetime.date.today(),
        action={
            "type": "Negative",
            "contents": [
                {
                    "type": "Action",
                    "label": "An action",
                }
            ],
        },
    )

    assert st.action.contents[
        0
    ].action_when == datetime.date.today() + datetime.timedelta(days=1)

    # Check we can convert to DB model, which will be proof of pudding
    # TODO: check this
    # st._to_db_model()


@no_type_check
def test_update_model_with_field_binding_through_intermediate_ignoring_type():

    class Action(Document):
        action_when: datetime.date
        subaction: SubAction

    class SubAction(Document):
        action_when: datetime.date

    class Negative[T](SemanticSpace[T]):
        pass

    class Statement(Document):
        when: datetime.date
        action: Annotated[
            Negative[Action],
            RelationConfig(
                bind_to_child_field=[
                    FieldBinding(
                        bound_field="when",
                        child_fields=["action_when"],
                        allowed_type_names=["SubAction"],
                        converter=lambda x: x + datetime.timedelta(days=1),
                    ),
                ]
            ),
        ]

    initialise()

    action_annotation = Statement.Update.model_fields["action"].annotation
    assert isinstance(action_annotation, UnionType)

    negative_action_update, negative_action_create = get_args(action_annotation)

    assert isclass(negative_action_update) and issubclass(
        negative_action_update, Negative.Update
    )
    assert isclass(negative_action_create) and issubclass(
        negative_action_create, Negative.Create
    )

    bound_negative_contents_field = negative_action_update.model_fields[
        "contents"
    ].annotation
    assert get_origin(bound_negative_contents_field) is list

    arg = get_args(bound_negative_contents_field)[0]
    assert get_origin(arg) is Annotated

    arg = get_args(arg)[0]
    assert isinstance(arg, UnionType)

    bound_action_create, bound_action_update = get_args(arg)

    assert isclass(bound_action_create) and issubclass(
        bound_action_create, Action.Create
    )
    assert isclass(bound_action_update) and issubclass(
        bound_action_update, Action.Update
    )

    assert bound_action_create.model_fields["action_when"].annotation == datetime.date

    # Test that not providing Action.action_when raises error as binding only
    # applied to SubAction
    with pytest.raises(ValidationError):
        Statement.Update(
            id=uuid7(),
            label="A Statement",
            when=datetime.date.today(),
            action={
                "id": uuid7(),
                "type": "Negative",
                "contents": [
                    {
                        "id": uuid7(),
                        "type": "Action",
                        "label": "An action",
                        "subaction": {
                            "type": "SubAction",
                            "label": "A SubAction",
                        },
                    }
                ],
            },
        )

    st = Statement.Update(
        id=uuid7(),
        label="A Statement",
        when=datetime.date.today(),
        action={
            "id": uuid7(),
            "type": "Negative",
            "contents": [
                {
                    "id": uuid7(),
                    "type": "Action",
                    "label": "An action",
                    "action_when": datetime.date.today(),
                    "subaction": {
                        "id": uuid7(),
                        "type": "SubAction",
                        "label": "A SubAction",
                    },
                }
            ],
        },
    )

    assert st.action.contents[0].action_when == datetime.date.today()

    assert st.action.contents[
        0
    ].subaction.action_when == datetime.date.today() + datetime.timedelta(days=1)


""" TESTS FIXED UP TO HERE """


@no_type_check
def test_update_model_with_field_binding_through_intermediate_ignoring_type_does_not_override_given_value():

    class Action(Document):
        action_when: datetime.date
        subaction: SubAction

    class SubAction(Document):
        action_when: datetime.date

    class Negative[T](SemanticSpace[T]):
        pass

    class Statement(Document):
        when: datetime.date
        action: Annotated[
            Negative[Action],
            RelationConfig(
                bind_to_child_field=[
                    FieldBinding(
                        bound_field="when",
                        child_fields=["action_when"],
                        excluded_type_names=["Action"],
                        converter=lambda x: x + datetime.timedelta(days=1),
                    ),
                ]
            ),
        ]

    initialise()

    st = Statement.Update(
        id=uuid7(),
        label="A Statement",
        when=datetime.date.today(),
        action={
            "id": uuid7(),
            "type": "Negative",
            "contents": [
                {
                    "id": uuid7(),
                    "type": "Action",
                    "label": "An action",
                    "action_when": datetime.date.today(),
                    "subaction": {
                        "id": uuid7(),
                        "type": "SubAction",
                        "label": "A SubAction",
                    },
                }
            ],
        },
    )

    assert st.action.contents[0].action_when == datetime.date.today()

    assert st.action.contents[
        0
    ].subaction.action_when == datetime.date.today() + datetime.timedelta(days=1)


@no_type_check
def test_relation_validator():
    class Factoid(Document):
        statements: Annotated[
            list[Action],
            MinLen(1),
        ]

    class Action(Document):
        pass

    initialise()

    statements_field = Factoid._meta.fields["statements"]
    assert isinstance(statements_field, RelationFieldDefinition)

    assert statements_field.validators == [MinLen(1)]

    assert Factoid.Update.model_fields["statements"]
    assert Factoid.Update.model_fields["statements"].metadata == [MinLen(1)]

    with pytest.raises(ValidationError):
        Factoid.Update(id=uuid7(), label="A Factoid", statements=[])


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

    assert Factoid.Update.model_fields["number"]
    assert Factoid.Update.model_fields["number"].metadata == [Gt(1)]

    with pytest.raises(ValidationError):
        Factoid.Update(id=uuid7(), label="A Factoid", number=1)


@no_type_check
def test_list_validators():
    class Factoid(Document):
        numbers: Annotated[list[Annotated[int, Gt(1)]], MinLen(1)]

    initialise()

    statements_field = Factoid._meta.fields["numbers"]
    assert isinstance(statements_field, ListFieldDefinition)

    assert statements_field.validators == [MinLen(1)]
    assert statements_field.inner_type_validators == [Gt(1)]

    assert Factoid.Update.model_fields["numbers"]
    assert Factoid.Update.model_fields["numbers"].metadata == [MinLen(1)]

    with pytest.raises(ValidationError):
        Factoid.Update(id=uuid7(), label="A Factoid", numbers=[])

    with pytest.raises(ValidationError):
        Factoid.Update(id=uuid7(), label="A Factoid", numbers=[1])

    Factoid.Update(id=uuid7(), label="A Factoid", numbers=[2, 2, 2])
