import datetime
from types import UnionType
from typing import Annotated, Literal, get_args, get_origin, no_type_check
from uuid import UUID, uuid7

import pytest
from annotated_types import Gt, MinLen
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
)
from pangloss_models.model_bases.semantic_space import (
    SemanticSpace,
    _SemanticSpaceCreateDBBase,
)
from pangloss_models.model_bases.trait import NonHeritableTrait, Trait
from pydantic import AnyHttpUrl, ValidationError


@no_type_check
def test_camel_case():
    class Statement(Document):
        some_snake: str

    initialise()

    st = Statement.CreateDB(**dict(label="A statement", someSnake="hello"))
    assert st.some_snake == "hello"


@no_type_check
def test_meta_accessible_through_create():
    class Statement(Document):
        some_snake: str

    initialise()

    assert Statement.CreateDB._meta is Statement._meta


@no_type_check
def test_type_field_is_correct():
    class Statement(Document):
        pass

    initialise()

    assert Statement.CreateDB.model_fields["type"].annotation == Literal["Statement"]


@no_type_check
def test_create_model_for_document_with_no_id():
    class Statement(Document):
        pass

    initialise()

    assert Statement.CreateDB

    assert Statement.CreateDB._owner is Statement

    assert "id" in Statement.CreateDB.model_fields

    st = Statement.CreateDB(label="A Statement")
    assert st.label == "A Statement"


@no_type_check
def test_create_model_for_document_with_id_allowed():
    class Statement(Document):
        _meta = Document.Meta(create_with_id=True)

    initialise()

    assert Statement.CreateDB
    assert "id" in Statement.CreateDB.model_fields

    id_field = Statement.CreateDB.model_fields["id"]

    assert id_field.annotation == UUID | None

    st = Statement.CreateDB(id=uuid7(), create_new=True, label="A Statement")
    assert isinstance(st.id, UUID)
    assert st.create_new
    assert st.label == "A Statement"


@no_type_check
def test_create_model_for_document_with_id_and_url_allowed_and_no_label():
    class Statement(Document):
        _meta = Document.Meta(
            create_with_id=True, accept_url_as_id=True, require_label=False
        )

    initialise()

    assert Statement.CreateDB
    assert "id" in Statement.CreateDB.model_fields

    id_field = Statement.CreateDB.model_fields["id"]

    assert id_field.annotation == UUID | AnyHttpUrl | None

    st = Statement.CreateDB(
        id="http://test.com/statement1",
        create_new=True,
    )
    assert isinstance(st.id, AnyHttpUrl)
    assert st.create_new


@no_type_check
def test_create_model_for_entity():
    class Person(Entity):
        pass

    initialise()

    assert Person.CreateDB

    assert "id" in Person.CreateDB.model_fields
    assert "label" in Person.CreateDB.model_fields


@no_type_check
def test_entity_meta_requires_create_id_if_create_inline():
    with pytest.raises(PanglossMetaError):

        class Fails(Entity):
            _meta = Entity.Meta(create_inline=True)

        initialise()

    class Works(Entity):
        _meta = Entity.Meta(create_inline=True, create_with_id=True)

    initialise()


@no_type_check
def test_create_model_for_entity_with_id():
    class Person(Entity):
        _meta = Entity.Meta(create_with_id=True)

    initialise()

    assert Person.CreateDB

    assert "id" in Person.CreateDB.model_fields
    assert Person.CreateDB.model_fields["id"].annotation == UUID | AnyHttpUrl | None
    assert "label" in Person.CreateDB.model_fields

    p = Person.CreateDB(id=uuid7(), label="John Smith", create_new=True)
    assert p.id

    # With an ID provided, create_new=True must also be set
    with pytest.raises(ValidationError):
        Person.CreateDB(id="http://mything.net/person", label="Toby Jones")

    Person.CreateDB(label="Toby Jones", create_new=True)


@no_type_check
def test_build_base_create_model_for_reified_relation():

    class Identification[TTarget](ReifiedRelation[TTarget]):
        pass

    initialise()

    assert "id" in Identification.CreateDB.model_fields


@no_type_check
def test_add_fields_to_document_create_model():
    class Statement(Document):
        name: str
        age: int
        numbers: list[int]

    initialise()

    assert "name" in Statement.CreateDB.model_fields
    name_field = Statement.CreateDB.model_fields["name"]
    assert name_field.annotation is str

    assert "age" in Statement.CreateDB.model_fields
    age_field = Statement.CreateDB.model_fields["age"]
    assert age_field.annotation is int

    assert "numbers" in Statement.CreateDB.model_fields
    numbers_field = Statement.CreateDB.model_fields["numbers"]
    assert numbers_field.annotation == list[int]

    st = Statement.CreateDB(label="A Statement", name="John", age=12, numbers=[1, 2, 3])
    assert st.label == "A Statement"
    assert st.name == "John"
    assert st.age == 12
    assert st.numbers == [1, 2, 3]

    with pytest.raises(ValidationError):
        st = Statement.CreateDB(
            label="A Statement", name="John", age=12, numbers="WRONG"
        )


@no_type_check
def test_add_simple_relation_from_document_to_entity():

    class Statement(Document):
        was_carried_out_by: Person

    class Person(Entity):
        pass

    initialise()

    assert Statement.CreateDB
    assert Statement.CreateDB.model_fields["was_carried_out_by"]
    assert (
        Statement.CreateDB.model_fields["was_carried_out_by"].annotation
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

    assert Statement.CreateDB
    assert Statement.CreateDB.model_fields["was_carried_out_by"]
    assert (
        Statement.CreateDB.model_fields["was_carried_out_by"].annotation
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

    assert Statement.CreateDB
    assert Statement.CreateDB.model_fields["was_carried_out_by"]
    assert (
        Statement.CreateDB.model_fields["was_carried_out_by"].annotation
        == Person.ReferenceSet | Dude.ReferenceSet
    )

    st = Statement.CreateDB(
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

    assert Statement.CreateDB
    assert Statement.CreateDB.model_fields["was_carried_out_by"]
    annotation = Statement.CreateDB.model_fields["was_carried_out_by"].annotation
    assert get_args(get_args(annotation)[0])[0] is Person.ReferenceSet

    st = Statement.CreateDB(
        label="A Statement", was_carried_out_by=[{"type": "Person", "id": uuid7()}]
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

    assert Statement.CreateDB
    assert Statement.CreateDB.model_fields["was_carried_out_by"]
    assert (
        Statement.CreateDB.model_fields["was_carried_out_by"].annotation
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
    assert Statement.CreateDB.model_fields["action"]
    assert Statement.CreateDB.model_fields["action"].annotation is Action.CreateDB


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
    assert Statement.CreateDB.model_fields["action"]
    assert (
        Statement.CreateDB.model_fields["action"].annotation
        is Action.CreateDB._via.Certainty
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
        Order.CreateDB.model_fields["thing_ordered"].annotation
        == Order.CreateDB | DeferredOrder.CreateDB | Task.CreateDB | SubTask.CreateDB
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

    assert issubclass(Identification.CreateDB, _ReifiedRelationCreateDBBase)
    assert Identification.CreateDB.model_fields["some_value"].annotation is int

    assert (
        Statement.CreateDB.model_fields["is_about_person"].annotation.__name__
        == "Identification[Person]CreateDB"
    )

    identification_person_create_db_model = Statement.CreateDB.model_fields[
        "is_about_person"
    ].annotation
    assert issubclass(identification_person_create_db_model, Identification.CreateDB)
    assert (
        identification_person_create_db_model.model_fields["some_value"].annotation
        is int
    )
    assert identification_person_create_db_model._owner is Identification

    target_annotation = identification_person_create_db_model.model_fields[
        "target"
    ].annotation
    assert get_origin(target_annotation) is list
    assert get_args(get_args(target_annotation)[0])[0] is Person.ReferenceSet

    st_uuid = uuid7()

    st = Statement.CreateDB(
        label="A Statement",
        is_about_person={
            "type": "Identification",
            "target": [{"type": "Person", "id": st_uuid}],
            "some_value": 1,
        },
    )

    assert isinstance(st.is_about_person, identification_person_create_db_model)
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

    is_about_person_field = Statement.CreateDB.model_fields["is_about_person"]
    assert (
        is_about_person_field.annotation.__name__
        == "WithProxy[Identification[Person], Identification[Person]]CreateDB"
    )
    assert issubclass(is_about_person_field.annotation, WithProxy.CreateDB)
    assert is_about_person_field.annotation.model_fields["target"].annotation
    proxy_target_annotation = is_about_person_field.annotation.model_fields[
        "target"
    ].annotation
    assert get_origin(proxy_target_annotation) is list
    assert get_origin(get_args(proxy_target_annotation)[0]) is Annotated

    proxy_identification_target_annotation = get_args(
        get_args(proxy_target_annotation)[0]
    )[0]
    assert issubclass(proxy_identification_target_annotation, Identification.CreateDB)
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
        is Person.ReferenceSet
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
    assert issubclass(proxy_identification_target_annotation, Identification.CreateDB)
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
        is Person.ReferenceSet
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

    statement_field = Factoid.CreateDB.model_fields["has_statement"]
    assert statement_field
    assert get_origin(statement_field.annotation) is list
    assert get_origin(get_args(statement_field.annotation)[0]) is Annotated
    # Having peeled away the list and the Annotated...
    type_union = get_args(get_args(statement_field.annotation)[0])[0]
    assert isinstance(type_union, UnionType)
    type_union_items = get_args(type_union)
    assert set(t.__name__ for t in type_union_items) == set(
        ["StatementCreateDB", "Negative[Statement]CreateDB"]
    )

    Negative_Statement_Create: type[_SemanticSpaceCreateDBBase] = [
        c for c in type_union_items if c.__name__ == "Negative[Statement]CreateDB"
    ][0]

    assert issubclass(Negative_Statement_Create, _SemanticSpaceCreateDBBase)

    f = Factoid.CreateDB(
        label="A Factoid",
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

    assert isinstance(f.has_statement[0], Negative.CreateDB)
    assert f.has_statement[0].contents[0].type == "Statement"
    assert isinstance(f.has_statement[0].contents[0], Statement.CreateDB)


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
    assert "has_statements" in Factoid.CreateDB.model_fields

    # Check the annotation is a Union
    has_statements_field = Factoid.CreateDB.model_fields["has_statements"]
    assert has_statements_field
    annotation = has_statements_field.annotation

    assert isinstance(annotation, UnionType)
    union_items = get_args(annotation)
    assert len(union_items) == 2
    assert set(t.__name__ for t in union_items) == {
        "StatementCreateDB",
        "Causes[Statement, Statement]CreateDB",
    }

    # Check that Causes has a Create model
    assert hasattr(Causes, "Create")
    assert issubclass(Causes.CreateDB, _ConjunctionCreateDBBase)
    print(union_items)
    # Check that the specialized Causes[Statement, Statement] has a Create model

    causes_statement_create = [
        item
        for item in union_items
        if item.__name__ == "Causes[Statement, Statement]CreateDB"
    ][0]  # The Causes[Statement, Statement]Create
    assert issubclass(causes_statement_create, Causes.CreateDB)
    assert "cause" in causes_statement_create.model_fields
    assert "result" in causes_statement_create.model_fields
    assert (
        causes_statement_create.model_fields["cause"].annotation == Statement.CreateDB
    )
    assert (
        causes_statement_create.model_fields["result"].annotation == Statement.CreateDB
    )

    # Create an instance with a Statement
    f1 = Factoid.CreateDB(
        label="A Factoid",
        has_statements={
            "type": "Statement",
            "label": "A Statement",
        },
    )
    assert f1.label == "A Factoid"
    assert f1.has_statements.type == "Statement"
    assert isinstance(f1.has_statements, Statement.CreateDB)

    # Create an instance with a Causes conjunction
    f2 = Factoid.CreateDB(
        label="Another Factoid",
        has_statements={
            "type": "Causes",
            "cause": {
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
    assert isinstance(f2.has_statements, causes_statement_create)
    assert f2.has_statements.cause.type == "Statement"
    assert isinstance(f2.has_statements.cause, Statement.CreateDB)
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

    thing_carried_out_by_field = Statement.CreateDB.model_fields["thing_carried_out_by"]
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
def test_relation_to_embedded():
    class Date(Embedded):
        when: datetime.datetime

    class Statement(Document):
        date: Date

    initialise()

    assert Date.CreateDB.model_fields["when"].annotation is datetime.datetime
    assert Date.CreateDB.model_fields["type"].annotation == Literal["Date"]

    assert Statement._meta.fields["date"]

    assert Statement.CreateDB.model_fields["date"]

    st = Statement.CreateDB(
        label="A Statement", date={"type": "Date", "when": "2019-01-01"}
    )

    assert st.label == "A Statement"
    assert isinstance(st.date, Date.CreateDB)
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

    assert Naming.CreateDB.model_fields["name"].annotation == WithCertainty[str]


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
        Activity.CreateDB.model_fields["person_responsible"].annotation
        is Person.ReferenceSet
    )

    assert (
        Activity.CreateDB.model_fields["place"].annotation == Place.ReferenceSet | None
    )


@no_type_check
def test_db_field_in_create_db_model():

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

    assert "some_field" in Statement.CreateDB.model_fields
    assert "db_int_field" in Statement.CreateDB.model_fields
    assert "person_field" in Statement.CreateDB.model_fields
    assert "db_person_field" in Statement.CreateDB.model_fields
    assert "embedded_field" in Statement.CreateDB.model_fields
    assert "db_embedded_field" in Statement.CreateDB.model_fields


@no_type_check
def test_can_convert_create_to_create_db_model():
    class Statement(Document):
        name: str
        carried_out_by: Person
        action_carried_out: Action

    class Person(Entity):
        pass

    class Action(Document):
        pass

    initialise()

    st = Statement(
        label="A Statement Label",
        name="A Statement",
        carried_out_by={"type": "Person", "id": uuid7()},
        action_carried_out={"type": "Action", "label": "An Action"},
    )

    st_db = st._to_db_model()

    assert isinstance(st_db, Statement.CreateDB)
    assert st_db.label == "A Statement Label"
    assert st_db.name == "A Statement"
    assert isinstance(st_db.carried_out_by, Person.ReferenceSet)
    assert st_db.carried_out_by.type == "Person"

    assert isinstance(st_db.action_carried_out, Action.CreateDB)
    assert st_db.action_carried_out.type == "Action"


@no_type_check
def test_can_convert_create_to_create_db_model_with_declared_conversion():
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

    initialise()

    st = Statement(
        label="A Statement Label",
        name="A Statement",
        carried_out_by={"type": "Person", "id": uuid7()},
        something_else={"type": "SomethingElse", "label": "somethingelse"},
    )

    assert Statement.CreateDB.model_fields["type"].annotation == Literal["Statement"]

    st_db = st._to_db_model()

    assert isinstance(st_db, Statement.CreateDB)
    assert st_db.label == "A Statement Label"
    assert st_db.name == "A Statement"
    assert isinstance(st_db.carried_out_by, Person.ReferenceSet)
    assert st_db.carried_out_by.type == "Person"

    assert isinstance(st_db.action_carried_out, Action.CreateDB)
    assert st_db.action_carried_out.type == "Action"
    assert st_db.action_carried_out.label == "A Statement action"

    assert isinstance(st_db.something_else, SomethingElse.CreateDB)
    assert st_db.something_else.name == "something else name"


@no_type_check
def test_document_create_db_has_id_field():
    class Statement(Document):
        pass

    initialise()

    st1 = Statement.Create(label="A Statement")

    st1_db = st1._to_db_model()

    assert st1_db.id


@no_type_check
def test_entity_create_db_has_id_field():
    class Person(Entity):
        pass

    initialise()

    p = Person.Create(label="John Smith")

    p_db = p._to_db_model()
    assert isinstance(p_db.id, UUID)


@no_type_check
def test_entity_create_db_retains_provided_id():
    class Person(Entity):
        _meta = Entity.Meta(create_with_id=True)

    initialise()

    given_uuid = uuid7()
    p = Person.Create(id=given_uuid, label="Toby Jones", create_new=True)
    assert p.id

    p_db = p._to_db_model()
    assert p_db.id == given_uuid


@no_type_check
def test_entity_create_db_has_new_id_but_keeps_url_when_provided():
    class Person(Entity):
        _meta = Entity.Meta(create_with_id=True, accept_url_as_id=True)

    initialise()

    p = Person.Create(
        id="http://something.net/Toby_Jones", label="Toby Jones", create_new=True
    )

    p_db = p._to_db_model()
    assert isinstance(p_db.id, UUID)
    assert p_db.urls == set([AnyHttpUrl("http://something.net/Toby_Jones")])


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

    assert Factoid.CreateDB.model_fields["statements"]
    assert Factoid.CreateDB.model_fields["statements"].metadata == [MinLen(1)]

    with pytest.raises(ValidationError):
        Factoid.CreateDB(label="A Factoid", statements=[])


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

    assert Factoid.CreateDB.model_fields["number"]
    assert Factoid.CreateDB.model_fields["number"].metadata == [Gt(1)]

    with pytest.raises(ValidationError):
        Factoid.CreateDB(label="A Factoid", number=1)


@no_type_check
def test_list_validators():
    class Factoid(Document):
        numbers: Annotated[list[Annotated[int, Gt(1)]], MinLen(1)]

    initialise()

    statements_field = Factoid._meta.fields["numbers"]
    assert isinstance(statements_field, ListFieldDefinition)

    assert statements_field.validators == [MinLen(1)]
    assert statements_field.inner_type_validators == [Gt(1)]

    assert Factoid.CreateDB.model_fields["numbers"]
    assert Factoid.CreateDB.model_fields["numbers"].metadata == [MinLen(1)]

    with pytest.raises(ValidationError):
        Factoid.CreateDB(label="A Factoid", numbers=[])

    with pytest.raises(ValidationError):
        Factoid.Create(label="A Factoid", numbers=[1])

    Factoid.CreateDB(label="A Factoid", numbers=[2, 2, 2])


@no_type_check
def test_document_create_db_in_semantic_spaces_propagated():

    class Negative[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        _meta = Document.Meta(use_in_semantic_space_label=False)
        statements: list[Order | Negative[Order]]

    class Action(Document):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid.CreateDB.model_fields["semantic_spaces"]

    assert Factoid.Create

    factoid = Factoid.Create(
        **{
            "label": "A Factoid",
            "statements": [
                {
                    "type": "Negative",
                    "contents": [
                        {
                            "type": "Order",
                            "label": "An Order",
                            "thing_ordered": {
                                "type": "Subjunctive",
                                "contents": [{"type": "Action", "label": "An Action"}],
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

    factoid_db = factoid._to_db_model()
    assert factoid_db.semantic_space_labels == []
    assert factoid_db.statements[0].type == "Negative"
    assert factoid_db.statements[0].semantic_space_labels == []
    assert factoid_db.statements[0].contents[0].type == "Order"
    assert factoid_db.statements[0].contents[0].semantic_space_labels == ["Negative"]
    assert factoid_db.statements[0].contents[0].thing_ordered.type == "Subjunctive"
    assert (
        factoid_db.statements[0].contents[0].thing_ordered.semantic_space_labels == []
    )
    assert (
        factoid_db.statements[0].contents[0].thing_ordered.contents[0].type == "Action"
    )
    assert factoid_db.statements[0].contents[0].thing_ordered.contents[
        0
    ].semantic_space_labels == ["Negative", "Order -> Subjunctive"]


@no_type_check
def test_labels_simple():
    class Animal(Entity):
        pass

    class Mammal(Animal):
        pass

    class Cat(Mammal):
        pass

    initialise()

    c = Cat.CreateDB(label="A Cat", id=uuid7())

    assert c._labels == ["Cat", "Mammal", "Animal", "Entity"]


@no_type_check
def test_labels_with_trait():
    class CanBite(Trait):
        pass

    class Animal(Entity, CanBite):
        pass

    class Mammal(Animal):
        pass

    class Cat(Mammal):
        pass

    initialise()

    c = Cat.CreateDB(label="A Cat", id=uuid7())
    assert c.__metatype__ == "Entity"
    assert c._labels == ["Cat", "Mammal", "Animal", "CanBite", "Entity"]


@no_type_check
def test_labels_with_non_heritable_trait_not_included_when_not_directly_applied():
    class CanBite(NonHeritableTrait):
        pass

    class Animal(Entity, CanBite):
        pass

    class Mammal(Animal):
        pass

    class Cat(Mammal):
        pass

    initialise()

    c = Cat.CreateDB(label="A Cat", id=uuid7())
    assert c.__metatype__ == "Entity"
    assert c._labels == ["Cat", "Mammal", "Animal", "Entity"]


@no_type_check
def test_labels_with_non_heritable_trait_included_when_directly_applied():
    class CanBite(NonHeritableTrait):
        pass

    class Animal(Entity):
        pass

    class Mammal(Animal):
        pass

    class Cat(Mammal, CanBite):
        pass

    initialise()

    c = Cat.CreateDB(label="A Cat", id=uuid7())
    assert c.__metatype__ == "Entity"
    assert c._labels == ["Cat", "Mammal", "Animal", "CanBite", "Entity"]


@no_type_check
def test_fulfils():
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
        Activity.CreateDB.model_fields["person_responsible"].annotation
        is Person.ReferenceSet
    )

    assert (
        Activity.CreateDB.model_fields["place"].annotation == Place.ReferenceSet | None
    )

    assert Activity.CreateDB.model_fields["place"].default is None

    a = Activity.Create(
        label="An Activity",
        person_responsible={"type": "Person", "id": uuid7()},
        place={"type": "Place", "id": uuid7()},
    )
    a_db = a._to_db_model()
    assert a_db.place.type == "Place"
    assert a_db.person_responsible.type == "Person"
    assert a_db.located_person.type == "Person"

    assert a_db._fulfils_classes == [PersonInPlace]
    assert isinstance(a_db, PersonInPlace.CreateDB)
    assert isinstance(a_db, Activity.CreateDB)

    a2 = Activity.Create(
        label="An Activity",
        person_responsible={"type": "Person", "id": uuid7()},
    )
    a2_db = a2._to_db_model()

    assert a2_db.place is None

    assert a2_db._fulfils_classes == []

    assert isinstance(a2_db, Activity.CreateDB)
    assert not isinstance(a2_db, PersonInPlace.CreateDB)


@no_type_check
def test_fulfils_on_subclass():
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

    class SubActivity(Activity):
        pass

    class Person(Entity):
        pass

    class Place(Entity):
        pass

    initialise()

    assert (
        SubActivity.CreateDB.model_fields["person_responsible"].annotation
        is Person.ReferenceSet
    )

    assert (
        SubActivity.CreateDB.model_fields["place"].annotation
        == Place.ReferenceSet | None
    )

    assert SubActivity.CreateDB.model_fields["place"].default is None

    a = SubActivity.Create(
        label="An Activity",
        person_responsible={"type": "Person", "id": uuid7()},
        place={"type": "Place", "id": uuid7()},
    )
    a_db = a._to_db_model()
    assert a_db.place.type == "Place"
    assert a_db.person_responsible.type == "Person"
    assert a_db.located_person.type == "Person"

    assert a_db._fulfils_classes == [PersonInPlace]
    assert isinstance(a_db, PersonInPlace.CreateDB)
    assert isinstance(a_db, SubActivity.CreateDB)

    a2 = SubActivity.Create(
        label="An Activity",
        person_responsible={"type": "Person", "id": uuid7()},
    )
    a2_db = a2._to_db_model()

    assert a2_db.place is None

    assert a2_db._fulfils_classes == []

    assert isinstance(a2_db, SubActivity.CreateDB)
    assert not isinstance(a2_db, PersonInPlace.CreateDB)
