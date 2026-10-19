from enum import Enum
from typing import TypedDict
from uuid import uuid4

import neo4j
import pytest
from pangloss_memgraph.databases.memgraph.initialise_database import (
    INDEXES,
    TEXT_INDEX_NAME,
    UNIQUE_CONSTRAINTS,
    enum_members,
    enums_in_annotation,
    enums_used_by_models,
    initialise_database,
)
from pangloss_models import initialise
from pangloss_models.exceptions import PanglossInitialisationError
from pangloss_models.model_bases.annotated_value import AnnotatedValue
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.edge_model import EdgeModel
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.helpers import ViaEdge
from pangloss_models.model_registry import ModelRegistry

from .helpers import run

pytestmark = pytest.mark.asyncio(loop_scope="session")


def make_enum(prefix: str, *members: str) -> type[Enum]:
    """An enum with a name no other test has used (Memgraph keeps enums, and
    cannot drop them)"""
    return Enum(f"{prefix}_{uuid4().hex[:8]}", list(members))  # type: ignore


def run_alone(db_driver, statement: str) -> list[dict]:
    """Run a statement that cannot be run inside a transaction (as `run` does)"""
    with db_driver.session(database="memgraph") as session:
        result = session.run(statement)
        rows = result.data()
        result.consume()
        return rows


def indexes(db_driver) -> list[dict]:
    return run_alone(db_driver, "SHOW INDEX INFO")


def constraints(db_driver) -> list[dict]:
    return run_alone(db_driver, "SHOW CONSTRAINT INFO")


def enums(db_driver) -> dict[str, list[str]]:
    return {
        row["Enum Name"]: row["Enum Values"]
        for row in run_alone(db_driver, "SHOW ENUMS")
    }


# ---------------------------------------------------------------------------
# Indexes, constraints and the text index
# ---------------------------------------------------------------------------


async def test_database_has_indexes_constraints_and_text_index(db_driver):
    """(The tests' own set-up has already run `initialise_database`)"""

    existing = indexes(db_driver)
    for label, properties in INDEXES:
        assert any(
            row["index type"] == "label+property"
            and row["label"] == label
            and row["property"] == list(properties)
            for row in existing
        ), f"index on {label}{properties}"

    # Of an id with the id of its head node
    assert any(
        row["label"] == "PGIndexableNode" and row["property"] == ["id", "head_node_id"]
        for row in existing
    )

    assert any(
        row["index type"] == f"label_text (name: {TEXT_INDEX_NAME})"
        and row["label"] == "PGIndexableNode"
        and row["property"] == ["label"]
        for row in existing
    )

    for label, property_name in UNIQUE_CONSTRAINTS:
        assert any(
            row["constraint type"] == "unique"
            and row["label"] == label
            and row["properties"] == [property_name]
            for row in constraints(db_driver)
        ), f"unique constraint on {label}({property_name})"


async def test_initialise_database_can_be_run_again(db_driver):
    first = await initialise_database()
    second = await initialise_database()

    assert second.created == []
    assert len(second.already_present) == len(first.created) + len(first.already_present)
    assert first.created == []  # (it had already been run for the tests)


async def test_initialise_database_recreates_what_is_missing(db_driver):
    run_alone(db_driver, "DROP INDEX ON :HeadNode(id)")
    run_alone(db_driver, f"DROP TEXT INDEX {TEXT_INDEX_NAME}")
    run_alone(db_driver, "DROP CONSTRAINT ON (n:PGUpdate) ASSERT n.id IS UNIQUE")

    setup = await initialise_database()

    assert sorted(setup.created) == sorted(
        [
            "index :HeadNode(id)",
            f"text index {TEXT_INDEX_NAME} on :PGIndexableNode(label)",
            "unique constraint on :PGUpdate(id)",
        ]
    )
    assert any(row["label"] == "HeadNode" for row in indexes(db_driver))
    assert any(
        row["index type"] == f"label_text (name: {TEXT_INDEX_NAME})"
        for row in indexes(db_driver)
    )


@pytest.mark.parametrize("label, property_name", UNIQUE_CONSTRAINTS)
async def test_ids_and_urls_are_unique(db_driver, clear_database, label, property_name):
    run(db_driver, f"CREATE (:{label} {{{property_name}: 'the-same-value'}})")

    with pytest.raises(neo4j.exceptions.ClientError, match="unique constraint"):
        run(db_driver, f"CREATE (:{label} {{{property_name}: 'the-same-value'}})")

    run(db_driver, f"MATCH (n:{label}) DETACH DELETE n")


async def test_the_text_index_is_used_for_searching(db_driver, clear_database):
    run(db_driver, "CREATE (:PGIndexableNode {id: 'a', label: 'A Gazetteer'})")
    run(db_driver, "CREATE (:PGIndexableNode {id: 'b', label: 'Something else'})")

    rows = run(
        db_driver,
        f'CALL text_search.regex_search("{TEXT_INDEX_NAME}", ".*Gazetteer.*") '
        "YIELD node RETURN node.id AS id",
    )
    assert rows == [{"id": "a"}]


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


async def test_enums_used_by_models_are_created(db_driver):
    Status = make_enum("Status", "GOOD", "BAD")
    Colour = make_enum("Colour", "RED", "BLUE")
    Size = make_enum("Size", "SMALL", "LARGE")
    Weight = make_enum("Weight", "LIGHT", "HEAVY")
    Shape = make_enum("Shape", "ROUND", "SQUARE")
    Mood = make_enum("Mood", "HAPPY", "SAD")
    Unused = make_enum("Unused", "NEVER", "USED")

    class Dimensions(TypedDict):
        size: Size  # type: ignore

    class Certainty(EdgeModel):
        weight: Weight  # type: ignore

    class WithMood[T](AnnotatedValue[T]):
        mood: Mood  # type: ignore

    class Person(Entity):
        pass

    class Statement(Document):
        status: Status
        colours: list[Colour]
        maybe_status: Status | None
        dimensions: Dimensions
        concerns: ViaEdge[Person, Certainty]
        name: WithMood[Shape]

    initialise()

    used = enums_used_by_models()
    assert set(used) == {Status, Colour, Size, Weight, Shape, Mood}
    assert Unused not in used

    setup = await initialise_database()

    existing = enums(db_driver)
    for enum in (Status, Colour, Size, Weight, Shape, Mood):
        assert existing[enum.__name__] == [member.name for member in enum]
        assert f"enum {enum.__name__}" in setup.created
    assert Unused.__name__ not in existing

    again = await initialise_database()
    assert again.created == []
    assert f"enum {Status.__name__}" in again.already_present


async def test_members_added_to_an_enum_are_added_to_the_database(db_driver):
    Status = make_enum("Status", "GOOD", "BAD")

    class Statement(Document):
        status: Status

    initialise()
    await initialise_database()
    assert enums(db_driver)[Status.__name__] == ["GOOD", "BAD"]

    # The enum gains a member (it has the same name, as the code has been edited)
    ModelRegistry._reset()
    Extended = Enum(Status.__name__, ["GOOD", "BAD", "UGLY"])  # type: ignore

    class StatementAgain(Document):
        status: Extended

    initialise()
    setup = await initialise_database()

    assert enums(db_driver)[Status.__name__] == ["GOOD", "BAD", "UGLY"]
    assert setup.created == [f"enum {Status.__name__}: added UGLY"]


async def test_no_enums_to_create(db_driver):
    class Statement(Document):
        text: str

    initialise()

    assert enums_used_by_models() == []
    assert (await initialise_database()).created == []


# ---------------------------------------------------------------------------
# Finding the enums
# ---------------------------------------------------------------------------


class Colour(Enum):
    RED = "red"
    BLUE = "blue"


class Inner(TypedDict):
    colour: Colour


class Outer(TypedDict):
    inner: Inner
    colours: list[Colour]


async def test_enums_in_annotation():
    assert enums_in_annotation(Colour) == {Colour}
    assert enums_in_annotation(Colour | None) == {Colour}
    assert enums_in_annotation(list[Colour]) == {Colour}
    assert enums_in_annotation(list[Colour | None]) == {Colour}
    assert enums_in_annotation(Outer) == {Colour}
    assert enums_in_annotation(list[Outer]) == {Colour}
    assert enums_in_annotation(str) == set()
    assert enums_in_annotation(list[int]) == set()
    assert enums_in_annotation(dict) == set()


async def test_enum_names_must_be_identifiers():
    Bad = Enum("Bad", ["fine", "not-fine"])  # type: ignore
    with pytest.raises(PanglossInitialisationError, match="identifiers"):
        enum_members([Bad])  # type: ignore


async def test_different_enums_with_the_same_name_are_refused():
    First = Enum("Clash", ["A", "B"])  # type: ignore
    Second = Enum("Clash", ["A", "C"])  # type: ignore
    with pytest.raises(PanglossInitialisationError, match="Clash"):
        enum_members([First, Second])  # type: ignore

    # (the same enum twice is fine)
    assert enum_members([First, First]) == {"Clash": ["A", "B"]}  # type: ignore
