"""What a write does, worked out from the instance with no database and no Cypher (`pangloss_cypher.write_plan`): the
nodes and their labels, the relations and the names of their edges, the references and the entities written in a
document"""

import typing
import uuid
from typing import Annotated, no_type_check

import pytest
from pangloss_core import settings as core_settings
from pangloss_core.settings import BaseSettings, DatabaseSettings
from pangloss_cypher.write_plan import (
    ExistingEntity,
    InlineEntity,
    PlannedNode,
    ReferenceToExisting,
    WritePlan,
    plan_create,
    plan_update,
)
from pangloss_models import initialise
from pangloss_models.field_definitions import FieldSubclassing
from pangloss_models.model_bases.configs import RelationConfig
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.edge_model import EdgeModel
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.helpers import Fulfils, ViaEdge
from pangloss_models.model_bases.semantic_space import SemanticSpace
from pangloss_models.model_registry import ModelRegistry
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
    assert relation.edge_properties == {"number": 9}
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
