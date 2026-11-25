"""What a write does, worked out from the instance with no database and no Cypher (`pangloss_cypher.write_plan`): the
nodes and their labels, the relations and the names of their edges, the references and the entities written in a
document"""

import datetime
import typing
import uuid
from typing import Annotated, no_type_check

import pytest
from pangloss_core import BaseSettings, DatabaseSettings
from pangloss_core import settings as core_settings
from pangloss_cypher.write_plan import (
    ExistingEntity,
    InlineEntity,
    PlannedNode,
    ReferenceToExisting,
    WritePlan,
    plan_create,
    plan_update,
)
from pangloss_models import (
    AnnotatedValue,
    Creator,
    Document,
    EdgeModel,
    Embedded,
    Entity,
    FieldSubclassing,
    Fulfils,
    KeepOnMerge,
    LabelTemplate,
    ModelRegistry,
    ReifiedRelation,
    RelationConfig,
    SemanticSpace,
    ViaEdge,
    hooks,
    initialise,
)
from pangloss_models.creators import writing_as
from pangloss_users import current_request_username
from pydantic import AnyHttpUrl


@pytest.fixture(autouse=True)
def models_without_a_database():
    """Settings that need no database (for the models to be initialised), and a registry of models of this test only;
    whatever settings there were are put back"""
    previous = getattr(core_settings, "SETTINGS", None)

    class Settings(BaseSettings):
        PROJECT_NAME: str = "Plans"
        BACKEND_CORS_ORIGINS: list[typing.Any] = []
        INSTALLED_APPS: list[str] = []
        STORAGE: str | None = "pangloss_sdk.storage:api"
        DATABASE: DatabaseSettings = DatabaseSettings()
        INTERFACE_LANGUAGES: list[str] = []
        DEFAULT_INTERFACE_LANGUAGE: str = "en"
        AUTHJWT_SECRET_KEY: str = "a secret for the tests, of a decent length"
        ENTITY_BASE_URL: AnyHttpUrl = AnyHttpUrl("http://test.com/")

    Settings()
    ModelRegistry._reset()
    yield
    ModelRegistry._reset()
    if previous is not None:
        core_settings.configure(previous)


def U(n: int) -> uuid.UUID:
    return uuid.UUID(int=n)


def targets(node: PlannedNode) -> list[typing.Any]:
    return [relation.target for relation in node.relations]


@no_type_check
def test_a_nested_document_is_a_node_below_the_head_node_with_a_pair_of_edges():
    class Action(Document):
        text: str

    class Order(Document):
        thing: list[Action]

    initialise()

    plan = plan_create(
        Order.Create(
            label="An order",
            thing=[{"type": "Action", "label": "Do", "text": "it"}],
        )._to_db_model()
    )

    assert not plan.is_update
    assert plan.head.labels[0] == "Order" and "Document" in plan.head.labels
    [relation] = plan.head.relations
    assert relation.edges == (("thing", "thing_reverse"),)
    action = relation.target
    assert isinstance(action, PlannedNode)
    assert action.properties["text"] == "it"
    assert action.properties["head_node_id"] == plan.head.id
    assert action.properties["head_node_type"] == "Order"
    assert action.properties["meta"]["created_by"]
    assert [n.id for n in plan.nodes_to_write()] == [action.id]


@no_type_check
def test_a_relation_that_subclasses_a_parent_field_has_the_edges_of_both_with_its_edge_properties():
    class Certainty(EdgeModel):
        number: int

    class Person(Entity):
        pass

    class Statement(Document):
        concerns_person: ViaEdge[Person, Certainty]

    class Action(Statement):
        carried_out_by: Annotated[
            ViaEdge[Person, Certainty],
            RelationConfig(
                subclasses_parent_fields=[
                    FieldSubclassing(
                        field_name="concerns_person", field_on_model=Statement
                    )
                ]
            ),
        ]

    initialise()

    plan = plan_create(
        Action.Create(
            label="An action",
            carried_out_by={
                "type": "Person",
                "id": U(1),
                "edge_properties": {"number": 9},
            },
        )._to_db_model()
    )

    [relation] = plan.head.relations
    assert relation.edges == (
        ("carried_out_by", "carried_out_by_reverse"),
        ("concerns_person", "concerns_person_reverse"),
    )
    # (the values of the edge, and the name of the edge model they are of)
    assert relation.edge_properties == {"number": 9, "pg_edge_model": "Certainty"}
    assert relation.target == ReferenceToExisting(
        value=str(U(1)),
        is_url=False,
        allowed_types=("Person",),
        field_name="carried_out_by",
    )


@no_type_check
def test_a_reference_by_url_is_one_by_url():
    class Place(Entity):
        pass

    class Letter(Document):
        sent_to: Place

    initialise()

    plan = plan_create(
        Letter.Create(
            label="A letter", sent_to={"type": "Place", "id": "http://example.com/p"}
        )._to_db_model()
    )

    [reference] = plan.references()
    assert reference.is_url and reference.value == "http://example.com/p"


@no_type_check
def test_a_semantic_space_is_a_node_with_its_contents_below_it():
    class Negative[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    class Statement(Document):
        thing: list[Action | Negative[Action]]

    initialise()

    plan = plan_create(
        Statement.Create(
            label="S",
            thing=[
                {
                    "type": "Negative",
                    "contents": [{"type": "Action", "label": "Not done"}],
                }
            ],
        )._to_db_model()
    )

    [negative] = targets(plan.head)
    assert negative.labels[0] == "Negative"
    [action] = targets(negative)
    assert action.properties["label"] == "Not done"
    # (each node of the tree knows the head node, however deep)
    assert action.properties["head_node_id"] == plan.head.id
    assert action.properties["head_node_type"] == "Statement"
    assert action.properties["meta"]["semantic_spaces"]


@no_type_check
def test_a_node_that_fulfils_a_class_has_its_labels():
    class Person(Entity):
        pass

    class Place(Entity):
        pass

    class Dated(Document):
        who: Person
        place: Place

    class Meeting(Document, Fulfils[Dated]):
        attendee: Annotated[
            Person,
            RelationConfig(
                subclasses_parent_fields=[FieldSubclassing("who", field_on_model=Dated)]
            ),
        ]

    initialise()

    def plan_of(**fields) -> WritePlan:
        return plan_create(
            Meeting.Create(
                label="M", attendee={"type": "Person", "id": U(1)}, **fields
            )._to_db_model()
        )

    assert "Dated" in plan_of(place={"type": "Place", "id": U(2)}).head.labels
    assert "Dated" not in plan_of().head.labels


@no_type_check
def test_an_entity_written_in_a_document_is_planned_once_and_created_only_if_it_is_not_there():
    class Person(Entity):
        _meta = Entity.Meta(create_inline=True, create_with_id=True)

    class Statement(Document):
        concerns: list[Person]

    initialise()

    person = {"type": "Person", "id": U(7), "label": "Inline", "create_new": True}
    by_url = {
        "type": "Person",
        "id": "http://example.com/people/1",
        "label": "By URL",
        "create_new": True,
    }
    plan = plan_create(
        Statement.Create(label="S", concerns=[person, by_url, person])._to_db_model()
    )

    entities = plan.inline_entities
    assert [e.key for e in entities] == [
        ("id", str(U(7))),
        ("url", "http://example.com/people/1"),
        ("id", str(U(7))),
    ]
    assert all(isinstance(e, InlineEntity) for e in entities)
    assert "HeadNode" not in entities[0].node.labels  # (the renderer adds it)
    assert "head_node_id" not in entities[0].node.properties  # (it is a head node)
    assert plan.urls_to_write() == ["http://example.com/people/1"]
    assert len(plan.created_entities()) == 2

    # (one that exists is related to, not written: neither it nor its URLs)
    there = {
        ("url", "http://example.com/people/1"): ExistingEntity(
            id="someone", labels=frozenset({"Person", "Entity"}), deleted=False
        )
    }
    assert plan.urls_to_write(there) == []
    assert [str(e.id) for e in plan.created_entities(there)] == [str(U(7))]


@no_type_check
def test_an_update_plans_the_tree_and_keeps_the_creation_of_its_nodes():
    class Action(Document):
        pass

    class Order(Document):
        thing: list[Action]

    initialise()

    plan = plan_update(
        Order.Update(
            id=U(1),
            label="An order",
            thing=[{"type": "Action", "id": U(2), "label": "Kept"}],
        )._to_db_model(),
        previous_meta={str(U(2)): {"created_by": "earlier", "created_when": None}},
    )

    assert plan.is_update and plan.head_id == U(1)
    assert plan.urls_to_write() == []
    [action] = targets(plan.head)
    assert action.properties["meta"]["created_by"] == "earlier"


@no_type_check
def test_a_nested_node_has_its_whole_meta_and_the_head_node_does_not():
    class Action(Document):
        pass

    class Order(Document):
        thing: list[Action]

    initialise()

    token = current_request_username.set("ann")
    try:
        with writing_as((Creator(username="bob"),)):
            plan = plan_create(
                Order.Create(
                    label="An order", thing=[{"type": "Action", "label": "Do"}]
                )._to_db_model()
            )
    finally:
        current_request_username.reset(token)

    assert plan.head.type == "Order"
    assert set(plan.head.properties) == {"id", "type", "label"}
    assert plan.head.properties["id"] == plan.head.id == str(plan.head_id)
    [action] = targets(plan.head)
    assert action.type == "Action" and action.labels[0] == "Action"
    assert action.properties["id"] == action.id
    meta = action.properties["meta"]
    # (made by those the write is made as; updated by the user making the request)
    assert meta["created_by"] == "bob"
    assert meta["updated_by"] == "ann"
    assert meta["created_when"] == meta["updated_when"]
    assert meta["created_when"].tzinfo is datetime.UTC
    assert meta["semantic_spaces"] == []
    assert meta["path"] == [
        {"kind": "document", "type": "Order", "id": plan.head.id, "field": "thing"}
    ]
    # (the older record of a node's place is not written)
    assert "context_labels" not in meta


@no_type_check
def test_without_creators_a_nested_node_is_made_by_the_user_of_the_request():
    class Action(Document):
        pass

    class Order(Document):
        thing: list[Action]

    initialise()

    token = current_request_username.set("ann")
    try:
        plan = plan_create(
            Order.Create(
                label="An order", thing=[{"type": "Action", "label": "Do"}]
            )._to_db_model()
        )
    finally:
        current_request_username.reset(token)

    [action] = targets(plan.head)
    assert action.properties["meta"]["created_by"] == "ann"


@no_type_check
def test_what_installed_apps_ask_for_is_on_a_new_head_node_with_the_review_status_the_document_asks_for():
    class Order(Document):
        pass

    initialise()

    def asked(model):
        return {"for": model.__name__, "status": hooks.requested_review_status.get()}

    hooks.new_head_properties.append(asked)
    try:
        plan = plan_create(
            Order.Create(label="An order", review_status="checked")._to_db_model()
        )
        unasked = plan_create(Order.Create(label="An order")._to_db_model())
    finally:
        hooks.new_head_properties.remove(asked)

    assert plan.head.properties["for"] == "Order"
    # (`checked` is the earlier name of `published`)
    assert plan.head.properties["status"] == "published"
    assert unasked.head.properties["status"] is None
    assert plan.head.properties["label"] == "An order"


@no_type_check
def test_a_new_entity_has_its_urls_in_order_and_an_update_writes_none():
    class Person(Entity):
        name: str

    initialise()

    plan = plan_create(
        Person.Create(
            label="P",
            name="Ann",
            urls=["http://example.com/b", "http://example.com/a"],
        )._to_db_model()
    )
    assert plan.head.urls == ("http://example.com/a", "http://example.com/b")
    assert plan.urls_to_write() == ["http://example.com/a", "http://example.com/b"]
    assert plan.head.properties["name"] == "Ann"

    updated = plan_update(Person.Update(id=U(1), label="P", name="Ann")._to_db_model())
    assert updated.head.type == "Person" and updated.head.labels[0] == "Person"
    assert updated.head.properties == {}
    assert updated.urls_to_write() == []


@no_type_check
def test_an_updated_node_keeps_when_it_was_created_and_its_head_node_is_the_one_updated():
    class Action(Document):
        pass

    class Order(Document):
        thing: list[Action]

    initialise()

    then = datetime.datetime(2020, 1, 1, tzinfo=datetime.UTC)
    plan = plan_update(
        Order.Update(
            id=U(1),
            label="An order",
            thing=[
                {"type": "Action", "id": U(2), "label": "Kept"},
                {"type": "Action", "id": U(3), "label": "New"},
            ],
        )._to_db_model(),
        previous_meta={str(U(2)): {"created_by": "earlier", "created_when": then}},
    )

    kept, new = targets(plan.head)
    assert kept.properties["meta"]["created_when"] == then
    assert new.properties["meta"]["created_when"] > then
    assert new.properties["meta"]["created_by"] != "earlier"
    assert kept.properties["head_node_id"] == str(U(1))
    assert kept.properties["head_node_type"] == "Order"


@no_type_check
def test_an_embedded_object_is_a_node_below_the_head_node_with_a_pair_of_edges():
    class Date(Embedded):
        year: int

    class Event(Document):
        date: Date
        end: Date | None
        other_date: Date

    initialise()

    plan = plan_create(
        Event.Create(
            label="E",
            date={"type": "Date", "year": 1500},
            end=None,
            other_date={"type": "Date", "year": 1502},
        )._to_db_model()
    )

    relations = plan.head.relations
    assert [r.edges for r in relations] == [
        (("date", "date_reverse"),),
        (("other_date", "other_date_reverse"),),
    ]
    assert [r.target.properties["year"] for r in relations] == [1500, 1502]
    assert all(r.edge_properties is None for r in relations)
    date = relations[0].target
    assert date.type == "Date" and date.labels[0] == "Date"
    assert date.properties["head_node_id"] == plan.head.id
    assert date.properties["head_node_type"] == "Event"
    assert date.properties["meta"]["created_by"]
    assert [n.id for n in plan.nodes_to_write()] == [r.target.id for r in relations]


@no_type_check
def test_an_annotated_value_is_written_as_a_map_and_a_list_of_them_as_a_list_of_maps():
    class WithCertainty[T](AnnotatedValue[T]):
        certainty: int

    class Action(Document):
        name: WithCertainty[str]
        names: list[WithCertainty[str]]

    class Order(Document):
        thing: list[Action]

    initialise()

    action = {
        "type": "Action",
        "label": "A",
        "name": {"value": "John", "certainty": 2},
        "names": [
            {"value": "Jack", "certainty": 1},
            {"value": "Jo", "certainty": 3},
        ],
    }
    plan = plan_create(Order.Create(label="O", thing=[action])._to_db_model())
    [node] = targets(plan.head)
    assert node.properties["name"] == {"value": "John", "certainty": 2}
    assert node.properties["names"] == [
        {"value": "Jack", "certainty": 1},
        {"value": "Jo", "certainty": 3},
    ]

    head = plan_create(Action.Create(**action)._to_db_model())
    assert head.head.properties["name"] == {"value": "John", "certainty": 2}


@no_type_check
def test_a_label_worked_out_by_a_template_is_marked_so():
    class Person(Entity):
        _meta = Entity.Meta(label_template=LabelTemplate("{name}"))
        name: str

    initialise()

    # (the label is worked out before the plan is made: `label_templates.fill_labels`)
    plan = plan_create(
        Person.Create(name="Ann", label="Ann", label_auto=True)._to_db_model()
    )
    assert plan.head.properties["label"] == "Ann"
    assert plan.head.properties["label_auto"] is True
    unmarked = plan_create(Person.Create(name="Ann", label="Mine")._to_db_model())
    assert "label_auto" not in unmarked.head.properties


@no_type_check
def test_a_generic_wrapper_points_at_what_the_field_gives_its_type_variable():
    class Person(Entity):
        pass

    class Place(Entity):
        pass

    class Identification[T](ReifiedRelation[T]):
        pass

    class Proxy[T](ReifiedRelation[T]):
        pass

    class Statement(Document):
        who: list[Proxy[Place] | Identification[Person]]

    initialise()

    plan = plan_create(
        Statement.Create(
            label="S",
            who=[
                {"type": "Identification", "target": [{"type": "Person", "id": U(1)}]},
                {"type": "Proxy", "target": [{"type": "Place", "id": U(2)}]},
            ],
        )._to_db_model()
    )

    identification, proxy = targets(plan.head)
    [person] = targets(identification)
    [place] = targets(proxy)
    assert identification.relations[0].edges[0][0] == "target"
    assert person == ReferenceToExisting(
        value=str(U(1)), is_url=False, allowed_types=("Person",), field_name="target"
    )
    assert place.allowed_types == ("Place",)
    assert identification.properties["head_node_id"] == plan.head.id


@no_type_check
def test_a_relation_marked_keep_on_merge_says_so_for_a_reference_and_an_entity_written_in_it():
    class Person(Entity):
        _meta = Entity.Meta(create_inline=True, create_with_id=True)

    class Statement(Document):
        kept: Annotated[list[Person], KeepOnMerge()]
        followed: list[Person]

    initialise()

    plan = plan_create(
        Statement.Create(
            label="S",
            kept=[
                {"type": "Person", "id": U(1)},
                {"type": "Person", "id": U(2), "label": "New", "create_new": True},
            ],
            followed=[
                {"type": "Person", "id": U(1)},
                {"type": "Person", "id": U(3), "label": "New", "create_new": True},
            ],
        )._to_db_model()
    )

    reference, entity, other_reference, other_entity = targets(plan.head)
    assert reference.keep_on_merge and entity.keep_on_merge
    assert not other_reference.keep_on_merge and not other_entity.keep_on_merge
    assert entity.field_name == "kept" and other_entity.field_name == "followed"
    assert entity.type == "Person" and entity.allowed_types == ("Person",)
    assert other_reference.field_name == "followed"


@no_type_check
def test_each_reference_to_a_node_is_first_once_and_each_node_of_the_document_always():
    class Person(Entity):
        pass

    class Action(Document):
        pass

    class Statement(Document):
        concerns: list[Person]
        thing: list[Action]

    initialise()

    plan = plan_create(
        Statement.Create(
            label="S",
            concerns=[
                {"type": "Person", "id": U(1)},
                {"type": "Person", "id": U(2)},
                {"type": "Person", "id": U(1)},
            ],
            thing=[{"type": "Action", "label": "A"}, {"type": "Action", "label": "B"}],
        )._to_db_model()
    )

    assert [first for _, _, first in plan.walk()] == [True, True, False, True, True]
    assert [r.value for r in plan.references()] == [str(U(1)), str(U(2)), str(U(1))]


@no_type_check
def test_an_entity_written_in_a_document_has_its_own_tree_written_only_where_it_is_new():
    class Date(Embedded):
        year: int

    class Place(Entity):
        pass

    class Person(Entity):
        _meta = Entity.Meta(create_inline=True, create_with_id=True)
        born: Date
        born_in: list[Place]

    class Statement(Document):
        concerns: list[Person]
        also: list[Person]

    initialise()

    person = {
        "type": "Person",
        "id": U(7),
        "label": "P",
        "create_new": True,
        "born": {"type": "Date", "year": 1500},
        "born_in": [{"type": "Place", "id": U(9)}],
        "urls": ["http://example.com/z", "http://example.com/a"],
    }
    other = {**person, "id": U(8), "urls": ["http://example.com/o"]}
    plan = plan_create(
        Statement.Create(
            label="S", concerns=[person], also=[person, other]
        )._to_db_model()
    )

    first, again, second = plan.inline_entities
    assert first.key == ("url", "http://example.com/a")
    assert first.node.urls == ("http://example.com/a", "http://example.com/z")
    assert first.node.id == str(U(7)) and first.node.type == "Person"
    assert "meta" not in first.node.properties  # (it is a head node)
    place, date = targets(first.node)
    # (what is below the entity belongs to it, not to the document)
    assert date.properties["head_node_id"] == str(U(7))
    assert date.properties["head_node_type"] == "Person"
    assert place.field_name == "born_in"

    # (the second time it is given, it is related to, and its tree is not written again)
    assert [first for _, _, first in plan.walk()] == [
        True,
        True,
        True,
        False,
        True,
        False,
        True,
    ]
    # (each node of an entity's tree knows its head node, however deep)
    assert plan.urls_to_write() == [
        "http://example.com/a",
        "http://example.com/z",
        "http://example.com/o",
    ]
    # (the place is matched once, but each reference to it is checked)
    assert [r.value for r in plan.references()] == [str(U(9)), str(U(9))]
    assert len(plan.nodes_to_write()) == 2

    # (one that exists has nothing written below it)
    there = {
        first.key: ExistingEntity(
            id=str(U(7)), labels=frozenset({"Person", "Entity"}), deleted=False
        )
    }
    assert [n.id for n in plan.nodes_to_write(there)] == [targets(second.node)[1].id]
    assert [r.value for r in plan.references(there)] == [str(U(9))]
    assert plan.urls_to_write(there) == ["http://example.com/o"]
