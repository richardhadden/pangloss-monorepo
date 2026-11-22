"""The class part (implementation_docs/similarity-build-plan.md, step 2.3; the rules are those of
implementation_docs/graph-embeddings.md, "Similar by class: the hierarchy as part of the vector"): no database."""

import math
import typing
from types import SimpleNamespace
from typing import Annotated, no_type_check

import pytest
from pangloss_core import BaseSettings, DatabaseSettings
from pangloss_core.settings import configure
from pangloss_models import (
    Document,
    Entity,
    FieldSubclassing,
    Fulfils,
    RelationConfig,
    SemanticNonHeritableTrait,
    SemanticTrait,
    Trait,
    initialise,
)
from pangloss_models.exceptions import PanglossInitialisationError
from pangloss_vectors import Part, part
from pangloss_vectors.class_part import PART
from pangloss_vectors.settings import class_decay


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True)) / (
        math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    )


def vector(type_name: str, labels: typing.Iterable[str] = ()) -> list[float]:
    found = PART.vector(type_name, labels)
    assert found is not None, f"{type_name} has no class vector"
    return found


def by_name(values: list[float]) -> dict[str, float]:
    """A vector as its dimensions that are not zero, by name"""
    return {
        name: value
        for name, value in zip(PART.maps().names, values, strict=True)
        if value
    }


@pytest.fixture
def decay(settings):
    """Sets `VECTORS_CLASS_DECAY` (as a project's settings module would), and gives the tests' settings back after"""

    def make(value: typing.Any):
        class Settings(BaseSettings):
            PROJECT_NAME: str = "Test"
            BACKEND_CORS_ORIGINS: list[typing.Any] = []
            INSTALLED_APPS: list[str] = []
            STORAGE: str | None = "pangloss_sdk.storage:api"
            DATABASE: DatabaseSettings = DatabaseSettings()
            AUTHJWT_SECRET_KEY: str = "asdf"
            ENTITY_BASE_URL: typing.Any = "http://test.com/"
            VECTORS_CLASS_DECAY: typing.Any = value

        return Settings()

    yield make
    configure(settings)


@no_type_check
def statements(abstract: bool = False):
    """The demo's hierarchy of creations, written out"""

    class Statement(Document):
        if abstract:
            _meta = Document.Meta(abstract=True)

    class CreationOfPhysicalObject(Statement):
        pass

    class CreationOfArtwork(CreationOfPhysicalObject):
        pass

    class CreationOfPainting(CreationOfArtwork):
        pass

    class Birth(Statement):
        pass

    class Person(Entity):
        pass

    initialise()


# ---------------------------------------------------------------------------
# The part
# ---------------------------------------------------------------------------


def test_the_class_part_is_registered_when_the_package_is_imported():
    assert part("class") is PART
    assert isinstance(PART, Part)
    assert (PART.name, PART.local, PART.requires, PART.weight) == (
        "class",
        True,
        frozenset(),
        0.1,
    )


# ---------------------------------------------------------------------------
# The hierarchy
# ---------------------------------------------------------------------------


def test_a_class_is_nearer_its_parent_than_a_class_that_shares_only_a_grandparent():
    statements()
    painting = vector("CreationOfPainting")
    assert cosine(painting, vector("CreationOfArtwork")) > cosine(
        painting, vector("Birth")
    )
    assert cosine(painting, vector("CreationOfArtwork")) > cosine(
        painting, vector("CreationOfPhysicalObject")
    )
    # (an entity shares nothing with a statement)
    assert cosine(painting, vector("Person")) == 0


def test_each_class_above_counts_at_the_decay_to_the_power_of_its_distance_and_the_vector_has_length_one():
    statements()
    painting = vector("CreationOfPainting")
    assert math.fsum(x * x for x in painting) == pytest.approx(1)
    raw = {
        "CreationOfPainting": 1,
        "CreationOfArtwork": 0.5,
        "CreationOfPhysicalObject": 0.25,
        "Statement": 0.125,
    }
    length = math.sqrt(sum(v * v for v in raw.values()))
    assert by_name(painting) == pytest.approx(
        {name: v / length for name, v in raw.items()}
    )


def test_there_is_a_dimension_for_each_class_abstract_ones_too_in_the_order_of_their_names():
    statements(abstract=True)
    assert PART.maps().names == (
        "Birth",
        "CreationOfArtwork",
        "CreationOfPainting",
        "CreationOfPhysicalObject",
        "Person",
        "Statement",
    )
    assert PART.dimension() == 6
    assert len(vector("Birth")) == 6
    assert PART.vector("NoSuchClass") is None


@no_type_check
def test_a_plain_trait_adds_nothing_and_a_semantic_trait_a_dimension_shared_by_the_classes_that_have_it():
    class Dateable(Trait):
        pass

    class Agent(SemanticTrait):
        pass

    class Person(Entity, Agent, Dateable):
        pass

    class Group(Entity, Agent):
        pass

    class Place(Entity, Dateable):
        pass

    initialise()
    assert PART.maps().names == ("Agent", "Group", "Person", "Place")
    # (a semantic trait as if a parent of the class that has it)
    assert by_name(vector("Person")) == pytest.approx(
        {"Person": 1 / math.sqrt(1.25), "Agent": 0.5 / math.sqrt(1.25)}
    )
    assert cosine(vector("Person"), vector("Group")) == pytest.approx(0.25 / 1.25)
    # (two classes that share only a plain trait share nothing)
    assert cosine(vector("Person"), vector("Place")) == 0


@no_type_check
def test_a_semantic_trait_below_another_puts_the_other_further_up():
    class Agent(SemanticTrait):
        pass

    class Collective(Agent):
        pass

    class Group(Entity, Collective):
        pass

    initialise()
    raw = {"Group": 1, "Collective": 0.5, "Agent": 0.25}
    length = math.sqrt(sum(v * v for v in raw.values()))
    assert by_name(vector("Group")) == pytest.approx(
        {name: v / length for name, v in raw.items()}
    )


@no_type_check
def test_a_semantic_trait_of_a_parent_class_counts_one_step_further_up():
    class Agent(SemanticTrait):
        pass

    class Person(Entity, Agent):
        pass

    class Saint(Person):
        pass

    initialise()
    found = by_name(vector("Saint"))
    assert found["Person"] / found["Saint"] == pytest.approx(0.5)
    assert found["Agent"] / found["Saint"] == pytest.approx(0.25)


@no_type_check
def test_a_non_heritable_semantic_trait_counts_only_for_the_class_that_names_it():
    class Named(SemanticNonHeritableTrait):
        pass

    class Person(Entity, Named):
        pass

    class Child(Person):
        pass

    initialise()
    assert "Named" in PART.maps().names
    assert set(by_name(vector("Person"))) == {"Person", "Named"}
    assert set(by_name(vector("Child"))) == {"Child", "Person"}


@no_type_check
def test_of_two_ways_up_to_a_dimension_the_nearest_counts():
    class Agent(SemanticTrait):
        pass

    class Person(Entity, Agent):
        pass

    # (Agent is one step up by the class's own trait, and two by its parent's)
    class Saint(Person, Agent):
        pass

    initialise()
    found = by_name(vector("Saint"))
    assert found["Agent"] / found["Saint"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Fulfilled classes
# ---------------------------------------------------------------------------


@no_type_check
def fulfilling():
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


def test_a_fulfilled_class_counts_only_for_a_node_with_its_label():
    fulfilling()
    assert set(PART.maps().fulfilled) == {"Dated"}
    # (a node that does not fulfil it: its class alone)
    assert by_name(vector("Meeting", ["Meeting", "Document"])) == {"Meeting": 1.0}
    # (one that does: the fulfilled class as a parent, at the decay)
    length = math.sqrt(1.25)
    assert by_name(vector("Meeting", ["Meeting", "Dated", "Document"])) == (
        pytest.approx({"Meeting": 1 / length, "Dated": 0.5 / length})
    )
    # (any other label is ignored)
    assert by_name(vector("Meeting", ["Meeting", "E5_Event", "Place"])) == {
        "Meeting": 1.0
    }


@pytest.mark.asyncio
async def test_overlay_gives_the_vector_of_the_plan_s_head_with_the_labels_the_plan_gives_it():
    fulfilling()
    plan = SimpleNamespace(
        head=SimpleNamespace(
            id="m1", type="Meeting", labels=("Meeting", "Dated", "Document")
        )
    )
    assert await PART.overlay(plan) == {"m1": vector("Meeting", ["Meeting", "Dated"])}
    plan.head.type = "NoSuchClass"
    assert await PART.overlay(plan) == {}


@pytest.mark.asyncio
@no_type_check
async def test_an_unknown_has_the_vector_of_its_class_an_abstract_one_its_own_and_a_name_of_no_class_none():
    from pangloss_vectors.parts import Unknown

    class Agent(Entity):
        _meta = Entity.Meta(abstract=True)

    class Person(Agent):
        pass

    class Saint(Person):
        pass

    class Group(Agent):
        pass

    initialise()
    found = await PART.unknown(
        None,
        [
            Unknown("p", "Person", "Ann"),
            Unknown("s", "Saint", "Bob"),
            Unknown("a", "Agent", "Cat"),
            Unknown("x", "NoSuchClass", "Dan"),
        ],
    )
    # (a class with classes below it is its own; the plan is not read)
    assert found == {
        "p": vector("Person", ["Person", "Agent", "Entity"]),
        "s": vector("Saint"),
        "a": vector("Agent"),
    }
    # (an abstract class is as near each class below it)
    assert cosine(found["a"], vector("Person")) == pytest.approx(
        cosine(found["a"], vector("Group"))
    )


# ---------------------------------------------------------------------------
# Signature, dimension and the decay
# ---------------------------------------------------------------------------


@no_type_check
def test_a_class_added_changes_the_signature_and_the_dimension():
    from pangloss_models import ModelRegistry

    statements()
    before = (PART.signature(), PART.dimension())
    ModelRegistry._reset()
    statements()
    assert (PART.signature(), PART.dimension()) == before

    ModelRegistry._reset()

    class Death(Document):
        pass

    statements()
    after = (PART.signature(), PART.dimension())
    assert after[1] == before[1] + 1
    assert after[0] != before[0]


def test_the_decay_setting_changes_the_vectors_and_the_signature(decay):
    statements()
    before = (PART.signature(), vector("CreationOfPainting"))
    decay(0.8)
    assert class_decay() == 0.8
    after = (PART.signature(), vector("CreationOfPainting"))
    assert after[0] != before[0]
    found = by_name(after[1])
    assert found["CreationOfArtwork"] / found["CreationOfPainting"] == pytest.approx(
        0.8
    )


def test_a_decay_of_zero_gives_each_class_a_dimension_of_its_own(decay):
    statements()
    decay(0)
    for name in ("CreationOfPainting", "Birth", "Statement"):
        assert by_name(vector(name)) == {name: 1.0}
    assert cosine(vector("CreationOfPainting"), vector("CreationOfArtwork")) == 0


@pytest.mark.parametrize("value", [-0.1, 1.5, "half", True, None])
def test_a_decay_that_is_not_a_number_from_0_to_1_is_refused(decay, value):
    decay(value)
    with pytest.raises(PanglossInitialisationError, match="VECTORS_CLASS_DECAY"):
        class_decay()
