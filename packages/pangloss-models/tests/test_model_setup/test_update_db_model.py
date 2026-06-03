import datetime
from inspect import isclass
from types import UnionType
from typing import Annotated, Literal, get_args, get_origin, no_type_check
from uuid import UUID, uuid7

import pytest
from annotated_types import Gt, MinLen
from pydantic import AnyHttpUrl, ValidationError

from pangloss_models import initialise
from pangloss_models.exceptions import PanglossMetaError
from pangloss_models.field_definitions import (
    FieldSubclassing,
    ListFieldDefinition,
    LiteralFieldDefinition,
    RelationFieldDefinition,
)
from pangloss_models.model_bases.annotated_value import AnnotatedValue
from pangloss_models.model_bases.configs import RelationConfig
from pangloss_models.model_bases.conjunction import (
    Conjunction,
    _ConjunctionCreateDBBase,
    _ConjunctionUpdateDBBase,
)
from pangloss_models.model_bases.document import (
    Document,
)
from pangloss_models.model_bases.edge_model import EdgeModel
from pangloss_models.model_bases.embedded import Embedded
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.helpers import DBField, Fulfils, ViaEdge
from pangloss_models.model_bases.reified_relation import (
    ReifiedRelation,
    _ReifiedRelationCreateDBBase,
    _ReifiedRelationUpdateDBBase,
)
from pangloss_models.model_bases.semantic_space import (
    SemanticSpace,
    _SemanticSpaceCreateDBBase,
    _SemanticSpaceUpdateDBBase,
)
from pangloss_models.model_bases.trait import Trait


@no_type_check
def test_camel_case():
    class Statement(Document):
        some_snake: str

    initialise()

    st = Statement.UpdateDB(**dict(id=uuid7(), label="A statement", someSnake="hello"))
    assert st.some_snake == "hello"


@no_type_check
def test_meta_accessible_through_update():
    class Statement(Document):
        some_snake: str

    initialise()

    assert Statement.UpdateDB._meta is Statement._meta


@no_type_check
def test_type_field_is_correct():
    class Statement(Document):
        pass

    initialise()

    assert Statement.UpdateDB.model_fields["type"].annotation == Literal["Statement"]


@no_type_check
def test_update_model_for_document_with_no_id():
    class Statement(Document):
        pass

    initialise()

    assert Statement.UpdateDB

    assert Statement.UpdateDB._owner is Statement

    assert "id" in Statement.UpdateDB.model_fields

    st = Statement.UpdateDB(id=uuid7(), label="A Statement")
    assert st.label == "A Statement"


@no_type_check
def test_update_model_for_document_with_id_allowed():
    class Statement(Document):
        _meta = Document.Meta(create_with_id=True)

    initialise()

    assert Statement.UpdateDB
    assert "id" in Statement.UpdateDB.model_fields

    id_field = Statement.UpdateDB.model_fields["id"]

    assert id_field.annotation == UUID | None

    st = Statement.UpdateDB(id=uuid7(), create_new=True, label="A Statement")
    assert isinstance(st.id, UUID)
    assert st.create_new
    assert st.label == "A Statement"


@no_type_check
def test_update_model_for_document_with_id_and_url_allowed_and_no_label():
    class Statement(Document):
        _meta = Document.Meta(
            create_with_id=True, accept_url_as_id=True, require_label=False
        )

    initialise()

    assert Statement.UpdateDB
    assert "id" in Statement.UpdateDB.model_fields

    id_field = Statement.UpdateDB.model_fields["id"]

    assert id_field.annotation == UUID | AnyHttpUrl | None

    st = Statement.UpdateDB(
        id="http://test.com/statement1",
    )
    assert isinstance(st.id, AnyHttpUrl)


@no_type_check
def test_update_model_for_entity():
    class Person(Entity):
        pass

    initialise()

    assert Person.UpdateDB

    assert "id" in Person.UpdateDB.model_fields
    assert "label" in Person.UpdateDB.model_fields


@no_type_check
def test_build_base_update_model_for_reified_relation():

    class Identification[TTarget](ReifiedRelation[TTarget]):
        pass

    initialise()

    assert "id" in Identification.UpdateDB.model_fields


@no_type_check
def test_add_fields_to_document_update_model():
    class Statement(Document):
        name: str
        age: int
        numbers: list[int]

    initialise()

    assert "name" in Statement.UpdateDB.model_fields
    name_field = Statement.UpdateDB.model_fields["name"]
    assert name_field.annotation is str

    assert "age" in Statement.UpdateDB.model_fields
    age_field = Statement.UpdateDB.model_fields["age"]
    assert age_field.annotation is int

    assert "numbers" in Statement.UpdateDB.model_fields
    numbers_field = Statement.UpdateDB.model_fields["numbers"]
    assert numbers_field.annotation == list[int]

    st = Statement.UpdateDB(
        id=uuid7(), label="A Statement", name="John", age=12, numbers=[1, 2, 3]
    )
    assert st.label == "A Statement"
    assert st.name == "John"
    assert st.age == 12
    assert st.numbers == [1, 2, 3]

    with pytest.raises(ValidationError):
        st = Statement.CreateDB(
            id=uuid7(), label="A Statement", name="John", age=12, numbers="WRONG"
        )


@no_type_check
def test_add_simple_relation_from_document_to_entity():

    class Statement(Document):
        was_carried_out_by: Person

    class Person(Entity):
        pass

    initialise()

    assert Statement.UpdateDB
    assert Statement.UpdateDB.model_fields["was_carried_out_by"]
    assert (
        Statement.UpdateDB.model_fields["was_carried_out_by"].annotation
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

    assert Statement.UpdateDB
    assert Statement.UpdateDB.model_fields["was_carried_out_by"]
    assert (
        Statement.UpdateDB.model_fields["was_carried_out_by"].annotation
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

    assert Statement.UpdateDB
    assert Statement.UpdateDB.model_fields["was_carried_out_by"]
    assert (
        Statement.UpdateDB.model_fields["was_carried_out_by"].annotation
        == Person.ReferenceSet | Dude.ReferenceSet
    )

    st = Statement.UpdateDB(
        id=uuid7(),
        label="A Statement",
        was_carried_out_by={"type": "Dude", "id": uuid7()},
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

    assert Statement.UpdateDB
    assert Statement.UpdateDB.model_fields["was_carried_out_by"]
    annotation = Statement.UpdateDB.model_fields["was_carried_out_by"].annotation
    assert get_args(get_args(annotation)[0])[0] is Person.ReferenceSet

    st = Statement.UpdateDB(
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

    assert Statement.UpdateDB
    assert Statement.UpdateDB.model_fields["was_carried_out_by"]
    assert (
        Statement.UpdateDB.model_fields["was_carried_out_by"].annotation
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
    assert Statement.UpdateDB.model_fields["action"]
    assert get_args(Statement.UpdateDB.model_fields["action"].annotation) == (
        Action.UpdateDB,
        Action.CreateDB,
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
    assert Statement.UpdateDB.model_fields["action"]
    assert isinstance(Statement.UpdateDB.model_fields["action"].annotation, UnionType)
    update_db_type, create_db_type = get_args(
        Statement.UpdateDB.model_fields["action"].annotation
    )
    assert create_db_type is Action.CreateDB._via.Certainty
    assert update_db_type is Action.UpdateDB._via.Certainty


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
        Order.UpdateDB.model_fields["thing_ordered"].annotation
        == Order.CreateDB
        | Order.UpdateDB
        | DeferredOrder.CreateDB
        | DeferredOrder.UpdateDB
        | Task.CreateDB
        | Task.UpdateDB
        | SubTask.CreateDB
        | SubTask.UpdateDB
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

    assert issubclass(Identification.UpdateDB, _ReifiedRelationUpdateDBBase)
    assert Identification.UpdateDB.model_fields["some_value"].annotation is int

    assert isinstance(
        Statement.UpdateDB.model_fields["is_about_person"].annotation, UnionType
    )

    update_identification_type, create_identification_type = get_args(
        Statement.UpdateDB.model_fields["is_about_person"].annotation
    )
    assert create_identification_type.__name__ == "Identification[Person]CreateDB"
    assert update_identification_type.__name__ == "Identification[Person]UpdateDB"

    assert issubclass(create_identification_type, Identification.CreateDB)
    assert issubclass(update_identification_type, Identification.UpdateDB)

    assert update_identification_type.model_fields["some_value"].annotation is int
    assert update_identification_type._owner is Identification

    target_annotation = update_identification_type.model_fields["target"].annotation
    assert get_origin(target_annotation) is list
    assert get_args(get_args(target_annotation)[0])[0] is Person.ReferenceSet

    st_uuid = uuid7()

    st = Statement.UpdateDB(
        id=uuid7(),
        label="A Statement",
        is_about_person={
            "id": uuid7(),
            "type": "Identification",
            "target": [{"type": "Person", "id": st_uuid}],
            "some_value": 1,
        },
    )

    assert st.is_about_person.id
    assert isinstance(st.is_about_person, update_identification_type)
    assert st.is_about_person.target[0].id == st_uuid


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

    is_about_person_field = Statement.UpdateDB.model_fields["is_about_person"]
    assert isinstance(is_about_person_field.annotation, UnionType)
    with_proxy_update_db, with_proxy_create_db = get_args(
        is_about_person_field.annotation
    )
    assert (
        with_proxy_update_db.__name__
        == "WithProxy[Identification[Person], Identification[Person]]UpdateDB"
    )
    assert (
        with_proxy_create_db.__name__
        == "WithProxy[Identification[Person], Identification[Person]]CreateDB"
    )

    assert issubclass(with_proxy_update_db, WithProxy.UpdateDB)
    assert issubclass(with_proxy_create_db, WithProxy.CreateDB)

    assert with_proxy_update_db.model_fields["target"].annotation

    with_proxy_update_target = with_proxy_update_db.model_fields["target"].annotation

    assert get_origin(with_proxy_update_target) is list

    assert get_origin(get_args(with_proxy_update_target)[0]) is Annotated

    union_type, fieldinfo = get_args(get_args(with_proxy_update_target)[0])

    assert isinstance(union_type, UnionType)

    identification_update_db, identification_create_db = get_args(union_type)

    assert isclass(identification_update_db) and issubclass(
        identification_update_db, Identification.UpdateDB
    )
    assert isclass(identification_create_db) and issubclass(
        identification_create_db, Identification.CreateDB
    )

    assert (
        get_origin(identification_update_db.model_fields["target"].annotation) is list
    )

    assert (
        get_origin(
            get_args(identification_update_db.model_fields["target"].annotation)[0]
        )
        is Annotated
    )
    assert (
        get_args(
            get_args(identification_update_db.model_fields["target"].annotation)[0]
        )[0]
        is Person.ReferenceSet
    )

    with_proxy_update_proxy = with_proxy_update_db.model_fields["proxy"].annotation

    assert get_origin(with_proxy_update_proxy) is list

    assert get_origin(get_args(with_proxy_update_proxy)[0]) is Annotated

    union_type, fieldinfo = get_args(get_args(with_proxy_update_proxy)[0])

    assert isinstance(union_type, UnionType)

    identification_update_db, identification_create_db = get_args(union_type)

    assert isclass(identification_update_db) and issubclass(
        identification_update_db, Identification.UpdateDB
    )
    assert isclass(identification_create_db) and issubclass(
        identification_create_db, Identification.CreateDB
    )

    assert (
        get_origin(identification_update_db.model_fields["target"].annotation) is list
    )

    assert (
        get_origin(
            get_args(identification_update_db.model_fields["target"].annotation)[0]
        )
        is Annotated
    )
    assert (
        get_args(
            get_args(identification_update_db.model_fields["target"].annotation)[0]
        )[0]
        is Person.ReferenceSet
    )

    st1 = Statement.Update(
        id=uuid7(),
        label="A Statement",
        is_about_person={
            "id": uuid7(),
            "type": "WithProxy",
            "target": [
                {
                    "id": uuid7(),
                    "target": [
                        {"id": uuid7(), "type": "Person"},
                    ],
                    "some_value": 1,
                },
            ],
            "proxy": [
                {
                    "id": uuid7(),
                    "target": [
                        {"id": uuid7(), "type": "Person"},
                    ],
                    "some_value": 2,
                }
            ],
        },
    )

    st1_db = st1._to_db_model()

    assert isinstance(st1_db, Statement.UpdateDB)
    assert isinstance(st1_db.is_about_person, WithProxy.UpdateDB)
    assert isinstance(st1_db.is_about_person.target[0], Identification.UpdateDB)


@no_type_check
def test_relation_with_semantic_space():
    class Negative[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        has_statement: list[Statement | Negative[Statement]]

    class Statement(Document):
        text: str

    initialise()

    statement_field = Factoid.UpdateDB.model_fields["has_statement"]
    assert statement_field
    assert get_origin(statement_field.annotation) is list
    assert get_origin(get_args(statement_field.annotation)[0]) is Annotated

    type_union = get_args(get_args(statement_field.annotation)[0])[0]
    assert isinstance(type_union, UnionType)
    type_union_items = get_args(type_union)

    assert set(t.__name__ for t in type_union_items) == set(
        [
            "StatementCreateDB",
            "StatementUpdateDB",
            "Negative[Statement]CreateDB",
            "Negative[Statement]UpdateDB",
        ]
    )

    NegativeStatementUpdateDB: type[_SemanticSpaceUpdateDBBase] = [
        c for c in type_union_items if c.__name__ == "Negative[Statement]UpdateDB"
    ][0]

    assert issubclass(NegativeStatementUpdateDB, _SemanticSpaceUpdateDBBase)

    f = Factoid.UpdateDB(
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

    assert isinstance(f.has_statement[0], Negative.UpdateDB)
    assert f.has_statement[0].contents[0].type == "Statement"
    assert isinstance(f.has_statement[0].contents[0], Statement.UpdateDB)


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

    # Check that Factoid.CreateDB has the has_statements field
    assert "has_statements" in Factoid.UpdateDB.model_fields

    # Check the annotation is a Union
    has_statements_field = Factoid.UpdateDB.model_fields["has_statements"]
    assert has_statements_field
    annotation = has_statements_field.annotation

    assert isinstance(annotation, UnionType)
    union_items = get_args(annotation)

    assert len(union_items) == 4
    assert set(t.__name__ for t in union_items) == {
        "StatementCreateDB",
        "StatementUpdateDB",
        "Causes[Statement, Statement]CreateDB",
        "Causes[Statement, Statement]UpdateDB",
    }

    # Check that Causes has an Update model
    assert hasattr(Causes, "UpdateDB")
    assert issubclass(Causes.UpdateDB, _ConjunctionUpdateDBBase)

    # Check that the specialized Causes[Statement, Statement] has an UpdateDB model

    causes_statement_update_db = [
        item
        for item in union_items
        if item.__name__ == "Causes[Statement, Statement]UpdateDB"
    ][0]  # The Causes[Statement, Statement]Create
    assert issubclass(causes_statement_update_db, Causes.UpdateDB)

    assert "cause" in causes_statement_update_db.model_fields
    assert "result" in causes_statement_update_db.model_fields
    assert (
        causes_statement_update_db.model_fields["cause"].annotation
        == Statement.UpdateDB | Statement.CreateDB
    )
    assert (
        causes_statement_update_db.model_fields["result"].annotation
        == Statement.UpdateDB | Statement.CreateDB
    )

    # Create an instance with a Statement
    f1 = Factoid.UpdateDB(
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
    assert isinstance(f1.has_statements, Statement.UpdateDB)

    # Create an instance with a Causes conjunction
    f2 = Factoid.UpdateDB(
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
                "type": "Statement",
                "label": "Result Statement",
            },
        },
    )
    assert f2.label == "Another Factoid"
    assert f2.has_statements.type == "Causes"

    assert isinstance(f2.has_statements, causes_statement_update_db)
    assert f2.has_statements.cause.type == "Statement"
    assert isinstance(f2.has_statements.cause, Statement.UpdateDB)
    assert f2.has_statements.result.type == "Statement"
    assert isinstance(f2.has_statements.result, Statement.CreateDB)


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

    thing_carried_out_by_field = Statement.UpdateDB.model_fields["thing_carried_out_by"]
    assert (
        thing_carried_out_by_field.annotation
        == Person.ReferenceSet
        | Group.ReferenceSet
        | Organisation.ReferenceSet
        | Posse.ReferenceSet
    )

    st = Statement.UpdateDB(
        id=uuid7(),
        label="A Statement",
        thing_carried_out_by={"type": "Group", "id": uuid7()},
    )


@no_type_check
def test_relation_to_embedded():
    class Date(Embedded):
        when: datetime.datetime

    class Statement(Document):
        date: Date

    initialise()

    assert Date.UpdateDB.model_fields["when"].annotation is datetime.datetime
    assert Date.UpdateDB.model_fields["type"].annotation == Literal["Date"]

    assert Statement._meta.fields["date"]

    assert Statement.UpdateDB.model_fields["date"]

    st = Statement.UpdateDB(
        id=uuid7(), label="A Statement", date={"type": "Date", "when": "2019-01-01"}
    )

    assert st.label == "A Statement"
    assert isinstance(st.date, Date.CreateDB)
    assert st.date.type == "Date"
    assert isinstance(st.date.when, datetime.datetime)
    assert st.date.when == datetime.datetime(2019, 1, 1)

    st2 = Statement.UpdateDB(
        id=uuid7(),
        label="A Statement",
        date={"type": "Date", "when": "2019-01-01", "id": uuid7()},
    )

    assert st2.label == "A Statement"
    assert isinstance(st2.date, Date.UpdateDB)
    assert st2.date.type == "Date"
    assert isinstance(st2.date.when, datetime.datetime)
    assert st2.date.when == datetime.datetime(2019, 1, 1)


@no_type_check
def test_annotated_value():
    class WithCertainty[T](AnnotatedValue[T]):
        certainty: int

    class Naming(Document):
        name: WithCertainty[str]

    initialise()

    assert WithCertainty[str].model_fields["value"].annotation is str

    assert Naming.UpdateDB.model_fields["name"].annotation == WithCertainty[str]


"""Tests fixed up to here"""


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
                    FieldSubclassing(
                        field_name="located_person", field_on_model=PersonInPlace
                    )
                ]
            ),
        ]

    class Person(Entity):
        pass

    class Place(Entity):
        pass

    initialise()

    assert (
        Activity.UpdateDB.model_fields["person_responsible"].annotation
        is Person.ReferenceSet
    )

    assert (
        Activity.UpdateDB.model_fields["place"].annotation == Place.ReferenceSet | None
    )


@no_type_check
def test_db_field_in_update_db_model():

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

    assert "some_field" in Statement.UpdateDB.model_fields
    assert "db_int_field" in Statement.UpdateDB.model_fields
    assert "person_field" in Statement.UpdateDB.model_fields
    assert "db_person_field" in Statement.UpdateDB.model_fields
    assert "embedded_field" in Statement.UpdateDB.model_fields
    assert "db_embedded_field" in Statement.UpdateDB.model_fields


@no_type_check
def test_can_convert_create_to_update_db_model():
    class Statement(Document):
        name: str
        carried_out_by: Person
        action_carried_out: Action

    class Person(Entity):
        pass

    class Action(Document):
        pass

    initialise()

    st = Statement.Update(
        id=uuid7(),
        label="A Statement Label",
        name="A Statement",
        carried_out_by={"type": "Person", "id": uuid7()},
        action_carried_out={"type": "Action", "label": "An Action", "id": uuid7()},
    )

    st_db = st._to_db_model()

    assert isinstance(st_db, Statement.UpdateDB)
    assert st_db.label == "A Statement Label"
    assert st_db.name == "A Statement"
    assert isinstance(st_db.carried_out_by, Person.ReferenceSet)
    assert st_db.carried_out_by.type == "Person"

    assert isinstance(st_db.action_carried_out, Action.UpdateDB)
    assert st_db.action_carried_out.type == "Action"


@no_type_check
def test_can_convert_update_to_update_db_model_with_declared_conversion():
    class Statement(Document):
        name: str
        carried_out_by: Person
        action_carried_out: Annotated[Action, DBField]
        something_else: SomethingElse

        @staticmethod
        def to_db(incoming_data):

            incoming_data.action_carried_out = Action(
                label=incoming_data.name + " action",  # type: ignore
            )
            return incoming_data

    class Person(Entity):
        pass

    class Action(Document):
        pass

    class SomethingElse(Document):
        name: Annotated[str, DBField]

        @staticmethod
        def to_db_create(incoming_data):
            name = "something else name"

            return {**incoming_data.model_dump(), "name": name}

        @staticmethod
        def to_db_update(incoming_data):
            name = "something else update name"

            return {**incoming_data.model_dump(), "name": name}

    initialise()

    st = Statement.Update(
        id=uuid7(),
        label="A Statement Label",
        name="A Statement",
        carried_out_by={"type": "Person", "id": uuid7()},
        something_else={"type": "SomethingElse", "label": "somethingelse"},
    )

    assert Statement.Update.model_fields["type"].annotation == Literal["Statement"]

    st_db = st._to_db_model()

    assert isinstance(st_db, Statement.UpdateDB)
    assert st_db.label == "A Statement Label"
    assert st_db.name == "A Statement"
    assert isinstance(st_db.carried_out_by, Person.ReferenceSet)
    assert st_db.carried_out_by.type == "Person"

    assert isinstance(st_db.action_carried_out, Action.CreateDB)
    assert st_db.action_carried_out.type == "Action"
    assert st_db.action_carried_out.label == "A Statement action"

    assert isinstance(st_db.something_else, SomethingElse.CreateDB)
    assert st_db.something_else.name == "something else name"

    st = Statement.Update(
        id=uuid7(),
        label="A Statement Label",
        name="A Statement",
        carried_out_by={"type": "Person", "id": uuid7()},
        something_else={
            "type": "SomethingElse",
            "label": "somethingelse",
            "id": uuid7(),
        },
    )

    assert Statement.CreateDB.model_fields["type"].annotation == Literal["Statement"]

    st_db = st._to_db_model()

    assert isinstance(st_db, Statement.UpdateDB)
    assert st_db.label == "A Statement Label"
    assert st_db.name == "A Statement"
    assert isinstance(st_db.carried_out_by, Person.ReferenceSet)
    assert st_db.carried_out_by.type == "Person"

    assert isinstance(st_db.action_carried_out, Action.CreateDB)
    assert st_db.action_carried_out.type == "Action"
    assert st_db.action_carried_out.label == "A Statement action"

    assert isinstance(st_db.something_else, SomethingElse.UpdateDB)
    assert st_db.something_else.name == "something else update name"


"""Tests fixed up to here"""


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

    assert Factoid.UpdateDB.model_fields["statements"]
    assert Factoid.UpdateDB.model_fields["statements"].metadata == [MinLen(1)]

    with pytest.raises(ValidationError):
        Factoid.UpdateDB(label="A Factoid", statements=[])


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

    assert Factoid.UpdateDB.model_fields["number"]
    assert Factoid.UpdateDB.model_fields["number"].metadata == [Gt(1)]

    with pytest.raises(ValidationError):
        Factoid.UpdateDB(label="A Factoid", number=1)


@no_type_check
def test_list_validators():
    class Factoid(Document):
        numbers: Annotated[list[Annotated[int, Gt(1)]], MinLen(1)]

    initialise()

    statements_field = Factoid._meta.fields["numbers"]
    assert isinstance(statements_field, ListFieldDefinition)

    assert statements_field.validators == [MinLen(1)]
    assert statements_field.inner_type_validators == [Gt(1)]

    assert Factoid.UpdateDB.model_fields["numbers"]
    assert Factoid.UpdateDB.model_fields["numbers"].metadata == [MinLen(1)]

    with pytest.raises(ValidationError):
        Factoid.UpdateDB(label="A Factoid", numbers=[])

    with pytest.raises(ValidationError):
        Factoid.UpdateDB(label="A Factoid", numbers=[1])

    Factoid.UpdateDB(id=uuid7(), label="A Factoid", numbers=[2, 2, 2])


@no_type_check
def test_document_update_db_in_semantic_spaces_propagated():

    class Negative[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Order | Negative[Order]]

    class Action(Document):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid.UpdateDB.model_fields["semantic_spaces"]

    assert Factoid.Update

    factoid = Factoid.Update(
        **{
            "id": uuid7(),
            "label": "A Factoid",
            "statements": [
                {
                    "id": uuid7(),
                    "type": "Negative",
                    "contents": [
                        {
                            "id": uuid7(),
                            "type": "Order",
                            "label": "An Order",
                            "thing_ordered": {
                                "id": uuid7(),
                                "type": "Subjunctive",
                                "contents": [
                                    {
                                        "id": uuid7(),
                                        "type": "Action",
                                        "label": "An Action",
                                    }
                                ],
                            },
                        }
                    ],
                }
            ],
        }
    )

    factoid_db = factoid._to_db_model()
    assert factoid_db.semantic_spaces == []
    assert factoid_db.statements[0].type == "Negative"
    assert factoid_db.statements[0].semantic_spaces == []
    assert factoid_db.statements[0].contents[0].type == "Order"
    assert factoid_db.statements[0].contents[0].semantic_spaces == ["Negative"]
    assert factoid_db.statements[0].contents[0].thing_ordered.type == "Subjunctive"
    assert factoid_db.statements[0].contents[0].thing_ordered.semantic_spaces == []
    assert (
        factoid_db.statements[0].contents[0].thing_ordered.contents[0].type == "Action"
    )
    assert factoid_db.statements[0].contents[0].thing_ordered.contents[
        0
    ].semantic_spaces == ["Negative", "Subjunctive"]
