import datetime
from inspect import isclass
from types import UnionType
from typing import Annotated, Literal, get_args, get_origin, no_type_check
from uuid import UUID, uuid7

import pytest
from annotated_types import Gt, MinLen
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
)
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.edge_model import EdgeModel
from pangloss_models.model_bases.embedded import Embedded
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.helpers import DBField, Fulfils, ViaEdge
from pangloss_models.model_bases.reified_relation import (
    ReifiedRelation,
    _ReifiedRelationCreateBase,
)
from pangloss_models.model_bases.semantic_space import (
    SemanticSpace,
    _SemanticSpaceCreateBase,
)
from pangloss_models.model_bases.trait import Trait
from pydantic import AnyHttpUrl, ValidationError


@no_type_check
def test_camel_case():
    class Statement(Document):
        some_snake: str

    initialise()

    st = Statement.Create(**dict(label="A statement", someSnake="hello"))
    assert st.some_snake == "hello"


@no_type_check
def test_meta_accessible_through_create():
    class Statement(Document):
        some_snake: str

    initialise()

    assert Statement.Create._meta is Statement._meta


@no_type_check
def test_type_field_is_correct():
    class Statement(Document):
        pass

    initialise()

    assert Statement.Create.model_fields["type"].annotation == Literal["Statement"]


@no_type_check
def test_create_model_for_document_with_no_id():
    class Statement(Document):
        pass

    initialise()

    assert Statement.Create

    assert Statement.Create._owner is Statement

    assert "id" not in Statement.Create.model_fields

    st = Statement.Create(label="A Statement")
    assert st.label == "A Statement"


@no_type_check
def test_create_model_for_document_with_id_allowed():
    class Statement(Document):
        _meta = Document.Meta(create_with_id=True)

    initialise()

    assert Statement.Create
    assert "id" in Statement.Create.model_fields

    id_field = Statement.Create.model_fields["id"]

    assert id_field.annotation == UUID | None

    st = Statement.Create(id=uuid7(), create_new=True, label="A Statement")
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

    assert Statement.Create
    assert "id" in Statement.Create.model_fields

    id_field = Statement.Create.model_fields["id"]

    assert id_field.annotation == UUID | AnyHttpUrl | None

    st = Statement.Create(
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

    assert Person.Create

    assert "id" not in Person.Create.model_fields
    assert "label" in Person.Create.model_fields


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

    assert Person.Create

    assert "id" in Person.Create.model_fields
    assert Person.Create.model_fields["id"].annotation == UUID | AnyHttpUrl | None
    assert "label" in Person.Create.model_fields

    p = Person.Create(id=uuid7(), label="John Smith", create_new=True)
    assert p.id

    # With an ID provided, create_new=True must also be set
    with pytest.raises(ValidationError):
        Person.Create(id="http://mything.net/person", label="Toby Jones")

    # With create_new=True set, an ID must also be provided
    with pytest.raises(ValidationError):
        Person.Create(label="Toby Jones", create_new=True)


@no_type_check
def test_build_base_create_model_for_reified_relation():

    class Identification[TTarget](ReifiedRelation[TTarget]):
        pass

    initialise()

    assert "id" not in Identification.Create.model_fields


@no_type_check
def test_add_fields_to_document_create_model():
    class Statement(Document):
        name: str
        age: int
        numbers: list[int]

    initialise()

    assert "name" in Statement.Create.model_fields
    name_field = Statement.Create.model_fields["name"]
    assert name_field.annotation is str

    assert "age" in Statement.Create.model_fields
    age_field = Statement.Create.model_fields["age"]
    assert age_field.annotation is int

    assert "numbers" in Statement.Create.model_fields
    numbers_field = Statement.Create.model_fields["numbers"]
    assert numbers_field.annotation == list[int]

    st = Statement.Create(label="A Statement", name="John", age=12, numbers=[1, 2, 3])
    assert st.label == "A Statement"
    assert st.name == "John"
    assert st.age == 12
    assert st.numbers == [1, 2, 3]

    with pytest.raises(ValidationError):
        st = Statement.Create(label="A Statement", name="John", age=12, numbers="WRONG")


@no_type_check
def test_add_simple_relation_from_document_to_entity():

    class Statement(Document):
        was_carried_out_by: Person

    class Person(Entity):
        pass

    initialise()

    assert Statement.Create
    assert Statement.Create.model_fields["was_carried_out_by"]
    assert (
        Statement.Create.model_fields["was_carried_out_by"].annotation
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

    assert Statement.Create
    assert Statement.Create.model_fields["was_carried_out_by"]
    assert (
        Statement.Create.model_fields["was_carried_out_by"].annotation
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

    assert Statement.Create
    assert Statement.Create.model_fields["was_carried_out_by"]
    assert (
        Statement.Create.model_fields["was_carried_out_by"].annotation
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

    assert Statement.Create
    assert Statement.Create.model_fields["was_carried_out_by"]
    annotation = Statement.Create.model_fields["was_carried_out_by"].annotation
    assert get_args(get_args(annotation)[0])[0] is Person.ReferenceSet

    st = Statement.Create(
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

    assert Statement.Create
    assert Statement.Create.model_fields["was_carried_out_by"]
    assert (
        Statement.Create.model_fields["was_carried_out_by"].annotation
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
    assert Statement.Create.model_fields["action"]
    assert Statement.Create.model_fields["action"].annotation is Action.Create


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
    assert Statement.Create.model_fields["action"]
    assert (
        Statement.Create.model_fields["action"].annotation
        is Action.Create._via.Certainty
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
        Order.Create.model_fields["thing_ordered"].annotation
        == Order.Create | DeferredOrder.Create | Task.Create | SubTask.Create
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

    assert issubclass(Identification.Create, _ReifiedRelationCreateBase)
    assert Identification.Create.model_fields["some_value"].annotation is int

    assert (
        Statement.Create.model_fields["is_about_person"].annotation.__name__
        == "Identification[Person]Create"
    )

    identification_person_create_model = Statement.Create.model_fields[
        "is_about_person"
    ].annotation
    assert issubclass(identification_person_create_model, Identification.Create)
    assert (
        identification_person_create_model.model_fields["some_value"].annotation is int
    )
    assert identification_person_create_model._owner is Identification

    target_annotation = identification_person_create_model.model_fields[
        "target"
    ].annotation
    assert get_origin(target_annotation) is list
    assert get_args(get_args(target_annotation)[0])[0] is Person.ReferenceSet

    st_uuid = uuid7()

    st = Statement.Create(
        label="A Statement",
        is_about_person={
            "type": "Identification",
            "target": [{"type": "Person", "id": st_uuid}],
            "some_value": 1,
        },
    )

    assert isinstance(st.is_about_person, identification_person_create_model)
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

    is_about_person_field = Statement.Create.model_fields["is_about_person"]
    assert (
        is_about_person_field.annotation.__name__
        == "WithProxy[Identification[Person], Identification[Person]]Create"
    )
    assert issubclass(is_about_person_field.annotation, WithProxy.Create)
    assert is_about_person_field.annotation.model_fields["target"].annotation
    proxy_target_annotation = is_about_person_field.annotation.model_fields[
        "target"
    ].annotation
    assert get_origin(proxy_target_annotation) is list
    assert get_origin(get_args(proxy_target_annotation)[0]) is Annotated

    proxy_identification_target_annotation = get_args(
        get_args(proxy_target_annotation)[0]
    )[0]
    assert issubclass(proxy_identification_target_annotation, Identification.Create)
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
    assert issubclass(proxy_identification_target_annotation, Identification.Create)
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

    statement_field = Factoid.Create.model_fields["has_statement"]
    assert statement_field
    assert get_origin(statement_field.annotation) is list
    assert get_origin(get_args(statement_field.annotation)[0]) is Annotated
    # Having peeled away the list and the Annotated...
    type_union = get_args(get_args(statement_field.annotation)[0])[0]
    assert isinstance(type_union, UnionType)
    type_union_items = get_args(type_union)
    assert set(t.__name__ for t in type_union_items) == set(
        ["StatementCreate", "Negative[Statement]Create"]
    )

    Negative_Statement_Create: type[_SemanticSpaceCreateBase] = [
        c for c in type_union_items if c.__name__ == "Negative[Statement]Create"
    ][0]

    assert issubclass(Negative_Statement_Create, _SemanticSpaceCreateBase)

    f = Factoid(
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
    assert isinstance(f.has_statement[0], Negative.Create)
    assert f.has_statement[0].contents[0].type == "Statement"
    assert isinstance(f.has_statement[0].contents[0], Statement.Create)


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
    assert "has_statements" in Factoid.Create.model_fields

    # Check the annotation is a Union
    has_statements_field = Factoid.Create.model_fields["has_statements"]
    assert has_statements_field
    annotation = has_statements_field.annotation

    assert isinstance(annotation, UnionType)
    union_items = get_args(annotation)
    assert len(union_items) == 2
    assert set(t.__name__ for t in union_items) == {
        "StatementCreate",
        "Causes[Statement, Statement]Create",
    }

    # Check that Causes has a Create model
    assert hasattr(Causes, "Create")
    assert issubclass(Causes.Create, _ConjunctionCreateBase)

    # Check that the specialized Causes[Statement, Statement] has a Create model

    causes_statement_create = [
        item
        for item in union_items
        if item.__name__ == "Causes[Statement, Statement]Create"
    ][0]  # The Causes[Statement, Statement]Create
    assert issubclass(causes_statement_create, Causes.Create)
    assert "cause" in causes_statement_create.model_fields
    assert "result" in causes_statement_create.model_fields
    assert causes_statement_create.model_fields["cause"].annotation == Statement.Create
    assert causes_statement_create.model_fields["result"].annotation == Statement.Create

    # Create an instance with a Statement
    f1 = Factoid.Create(
        label="A Factoid",
        has_statements={
            "type": "Statement",
            "label": "A Statement",
        },
    )
    assert f1.label == "A Factoid"
    assert f1.has_statements.type == "Statement"
    assert isinstance(f1.has_statements, Statement.Create)

    # Create an instance with a Causes conjunction
    f2 = Factoid.Create(
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
    assert isinstance(f2.has_statements.cause, Statement.Create)
    assert f2.has_statements.result.type == "Statement"
    assert isinstance(f2.has_statements.result, Statement.Create)


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

    thing_carried_out_by_field = Statement.Create.model_fields["thing_carried_out_by"]
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

    assert Date.Create.model_fields["when"].annotation is datetime.datetime
    assert Date.Create.model_fields["type"].annotation == Literal["Date"]

    assert Statement._meta.fields["date"]

    assert Statement.Create.model_fields["date"]

    st = Statement(label="A Statement", date={"type": "Date", "when": "2019-01-01"})

    assert st.label == "A Statement"
    assert isinstance(st.date, Date.Create)
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

    assert Naming.Create.model_fields["name"].annotation == WithCertainty[str]


@no_type_check
def test_db_field_not_in_create_model():

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

    assert "some_field" in Statement.Create.model_fields
    assert "db_int_field" not in Statement.Create.model_fields
    assert "person_field" in Statement.Create.model_fields
    assert "db_person_field" not in Statement.Create.model_fields
    assert "embedded_field" in Statement.Create.model_fields
    assert "db_embedded_field" not in Statement.Create.model_fields


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
        Activity.Create.model_fields["person_responsible"].annotation
        is Person.ReferenceSet
    )

    assert Activity.Create.model_fields["place"].annotation == Place.ReferenceSet | None


def test_create_model_with_field_binding():
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

    action_model = Statement.Create.model_fields["action"].annotation
    assert isclass(action_model) and issubclass(action_model, Action.Create)
    assert action_model.model_fields["action_when"].annotation == datetime.date | None
    assert (
        action_model.model_fields["action_when_optional"].annotation
        == datetime.date | None
    )


@no_type_check
def test_create_model_with_field_binding_through_intermediate():

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

    negative_model = Statement.Create.model_fields["action"].annotation
    assert isclass(negative_model) and issubclass(negative_model, Negative.Create)

    negative_contents_fields = negative_model.model_fields["contents"]
    assert get_origin(negative_contents_fields.annotation) is list
    annotated_action_model = get_args(negative_contents_fields.annotation)[0]

    assert get_origin(annotated_action_model) is Annotated
    action_model = get_args(annotated_action_model)[0]
    assert action_model
    assert isclass(action_model) and issubclass(action_model, Action.Create)

    assert action_model.model_fields["action_when"].annotation == datetime.date | None

    st = Statement.Create(
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
def test_create_model_with_field_binding_through_intermediate_with_transform():

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

    negative_model = Statement.Create.model_fields["action"].annotation
    assert isclass(negative_model) and issubclass(negative_model, Negative.Create)

    negative_contents_fields = negative_model.model_fields["contents"]
    assert get_origin(negative_contents_fields.annotation) is list
    annotated_action_model = get_args(negative_contents_fields.annotation)[0]

    assert get_origin(annotated_action_model) is Annotated
    action_model = get_args(annotated_action_model)[0]
    assert action_model
    assert isclass(action_model) and issubclass(action_model, Action.Create)

    assert action_model.model_fields["action_when"].annotation == datetime.date | None

    st = Statement.Create(
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
    st._to_db_model()


@no_type_check
def test_create_model_with_field_binding_through_intermediate_ignoring_type():

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

    negative_model = Statement.Create.model_fields["action"].annotation
    assert isclass(negative_model) and issubclass(negative_model, Negative.Create)

    negative_contents_fields = negative_model.model_fields["contents"]
    assert get_origin(negative_contents_fields.annotation) is list
    annotated_action_model = get_args(negative_contents_fields.annotation)[0]

    assert get_origin(annotated_action_model) is Annotated
    action_model = get_args(annotated_action_model)[0]
    assert action_model
    assert isclass(action_model) and issubclass(action_model, Action.Create)

    assert action_model.model_fields["action_when"].annotation == datetime.date

    # Test that not providing Action.action_when raises error as binding only
    # applied to SubAction
    with pytest.raises(ValidationError):
        Statement.Create(
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

    st = Statement.Create(
        label="A Statement",
        when=datetime.date.today(),
        action={
            "type": "Negative",
            "contents": [
                {
                    "type": "Action",
                    "label": "An action",
                    "action_when": datetime.date.today(),
                    "subaction": {
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
def test_create_model_with_field_binding_through_intermediate_ignoring_type_does_not_override_given_value():

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
                        allowed_type_names=["Action", "SubAction"],
                        converter=lambda x: x + datetime.timedelta(days=1),
                    ),
                ]
            ),
        ]

    initialise()

    negative_model = Statement.Create.model_fields["action"].annotation
    assert isclass(negative_model) and issubclass(negative_model, Negative.Create)

    negative_contents_fields = negative_model.model_fields["contents"]
    assert get_origin(negative_contents_fields.annotation) is list
    annotated_action_model = get_args(negative_contents_fields.annotation)[0]

    assert get_origin(annotated_action_model) is Annotated
    action_model = get_args(annotated_action_model)[0]
    assert action_model
    assert isclass(action_model) and issubclass(action_model, Action.Create)

    assert action_model.model_fields["action_when"].annotation == datetime.date | None

    st = Statement.Create(
        label="A Statement",
        when=datetime.date.today(),
        action={
            "type": "Negative",
            "contents": [
                {
                    "type": "Action",
                    "label": "An action",
                    "action_when": datetime.date.today(),
                    "subaction": {
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

    assert Factoid.Create.model_fields["statements"]
    assert Factoid.Create.model_fields["statements"].metadata == [MinLen(1)]

    with pytest.raises(ValidationError):
        Factoid.Create(label="A Factoid", statements=[])


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

    assert Factoid.Create.model_fields["number"]
    assert Factoid.Create.model_fields["number"].metadata == [Gt(1)]

    with pytest.raises(ValidationError):
        Factoid.Create(label="A Factoid", number=1)


@no_type_check
def test_list_validators():
    class Factoid(Document):
        numbers: Annotated[list[Annotated[int, Gt(1)]], MinLen(1)]

    initialise()

    statements_field = Factoid._meta.fields["numbers"]
    assert isinstance(statements_field, ListFieldDefinition)

    assert statements_field.validators == [MinLen(1)]
    assert statements_field.inner_type_validators == [Gt(1)]

    assert Factoid.Create.model_fields["numbers"]
    assert Factoid.Create.model_fields["numbers"].metadata == [MinLen(1)]

    with pytest.raises(ValidationError):
        Factoid.Create(label="A Factoid", numbers=[])

    with pytest.raises(ValidationError):
        Factoid.Create(label="A Factoid", numbers=[1])

    Factoid.Create(label="A Factoid", numbers=[2, 2, 2])
