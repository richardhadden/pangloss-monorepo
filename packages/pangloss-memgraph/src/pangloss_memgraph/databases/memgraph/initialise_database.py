"""Setting up a Memgraph database for Pangloss.

`initialise_database` creates what the queries rely on: indexes, uniqueness
constraints for ids, the text index used for searching labels, and an enum type
for each `Enum` used by the models. It can be run again at any time: whatever
already exists is left alone (and enums gain any new members).

Call `pangloss_models.initialise()` first, so that the models, and so the enums
they use, are known.
"""

import dataclasses
import re
from enum import Enum
from types import UnionType
from typing import Any, Union, get_args, get_origin, get_type_hints, is_typeddict

import neo4j
from pangloss_models.exceptions import PanglossInitialisationError
from pangloss_models.field_definitions import (
    AnnotatedValueFieldDefinition,
    ListFieldDefinition,
    LiteralFieldDefinition,
)
from pangloss_models.model_registry import ModelRegistry

from pangloss_memgraph.databases.memgraph.database import Database

TEXT_INDEX_NAME = "label_text"

# (label, property). Every node of a document, entity and so on has `PGIndexableNode`
# as a label, and the ids of all of them are unique; so are those of the records of
# creation, update and deletion of a head node. A URL (`PGUrl`) belongs to one
# entity: it is a node so that this can be a constraint, however many are written at
# once.
UNIQUE_CONSTRAINTS = [
    ("PGIndexableNode", "id"),
    ("PGCreation", "id"),
    ("PGUpdate", "id"),
    ("PGDeletion", "id"),
    ("PGUrl", "url"),
]

# (label, properties). Each unique property is indexed, for finding a node; and an id
# with its head node's id, for finding a node of a particular document; and head
# nodes, as they are found by id by the queries of updates and reads
INDEXES = [
    *[(label, (property_name,)) for label, property_name in UNIQUE_CONSTRAINTS],
    ("PGIndexableNode", ("id", "head_node_id")),
    ("HeadNode", ("id",)),
]

TEXT_INDEX = (TEXT_INDEX_NAME, "PGIndexableNode", "label")

# Memgraph's names for types and their values
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclasses.dataclass
class DatabaseSetup:
    """What `initialise_database` did"""

    created: list[str] = dataclasses.field(default_factory=list)
    already_present: list[str] = dataclasses.field(default_factory=list)


# ---------------------------------------------------------------------------
# Enums used by the models
# ---------------------------------------------------------------------------


def enums_in_annotation(annotation: Any) -> set[type[Enum]]:
    """The enums used in a type: itself, in a list or optional, or in a TypedDict"""
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return {annotation}

    if isinstance(annotation, type) and is_typeddict(annotation):
        enums: set[type[Enum]] = set()
        for value_type in get_type_hints(annotation).values():
            enums |= enums_in_annotation(value_type)
        return enums

    if get_origin(annotation) in (list, Union, UnionType):
        enums = set()
        for argument in get_args(annotation):
            enums |= enums_in_annotation(argument)
        return enums

    return set()


def enums_used_by_models() -> list[type[Enum]]:
    """Every enum that is the type of a field of a registered model (including edge
    models and annotated values, and enums in lists and TypedDicts)"""
    enums: set[type[Enum]] = set()

    for model in ModelRegistry.all_models().values():
        fields = model._meta.fields  # type: ignore
        for field_definition in fields.values():
            match field_definition:
                case LiteralFieldDefinition() | ListFieldDefinition():
                    enums |= enums_in_annotation(field_definition.annotated_type)
                case AnnotatedValueFieldDefinition():
                    annotated_value = field_definition.annotated_type
                    # What the value is (`WithCertainty[Colour]`), and its extra fields
                    for argument in annotated_value.__pydantic_generic_metadata__[
                        "args"
                    ]:
                        enums |= enums_in_annotation(argument)
                    for extra in annotated_value._meta.fields.values():
                        if isinstance(
                            extra, LiteralFieldDefinition | ListFieldDefinition
                        ):
                            enums |= enums_in_annotation(extra.annotated_type)

    return sorted(enums, key=lambda enum: enum.__qualname__)


def enum_members(enums: list[type[Enum]]) -> dict[str, list[str]]:
    """The names (and the member names) of the enums, as Memgraph would have them"""
    members: dict[str, list[str]] = {}
    for enum in enums:
        names = [member.name for member in enum]
        if not IDENTIFIER.match(enum.__name__) or not all(
            IDENTIFIER.match(name) for name in names
        ):
            raise PanglossInitialisationError(
                f"Enum {enum.__qualname__} cannot be made in Memgraph: its name and "
                "the names of its members must be identifiers"
            )
        if enum.__name__ in members and members[enum.__name__] != names:
            raise PanglossInitialisationError(
                f"There are different enums called {enum.__name__}, which Memgraph "
                "cannot tell apart"
            )
        members[enum.__name__] = names
    return members


# ---------------------------------------------------------------------------
# Setting up
# ---------------------------------------------------------------------------


async def run_statement(
    driver: neo4j.AsyncDriver, database_name: str, statement: str
) -> list[dict[str, Any]]:
    """Run a statement on its own: Memgraph does not allow changing indexes,
    constraints or enums inside a transaction"""
    async with driver.session(database=database_name) as session:
        result = await session.run(statement)  # type: ignore
        rows = await result.data()
        await result.consume()
        return rows


async def initialise_database(database: Database | None = None) -> DatabaseSetup:
    """Set up the database: indexes, constraints, the text index and enums.

    Creates, if they do not exist already:

    - for the ids (which are UUIDs) of every kind of node that has one, and for
      the URLs of entities, an index and a uniqueness constraint;
    - an index of `id` and `head_node_id` together, and one of `id` for head nodes;
    - the text index `label_text` on the `label` of every `PGIndexableNode`, used
      for searching; and
    - an enum for each `Enum` used by a model. Members are added to one that exists
      (Memgraph cannot remove them).

    Uses the default `Database`, unless given one. Models must be initialised
    first, for their enums to be known.
    """
    database = database or Database.default
    if not hasattr(database, "driver"):
        await database._initialise_driver()
    driver = database.driver
    database_name = database.settings.DATABASE.DATABASE_NAME

    async def run(statement: str) -> list[dict[str, Any]]:
        return await run_statement(driver, database_name, statement)

    setup = DatabaseSetup()

    def record(description: str, existed: bool) -> None:
        (setup.already_present if existed else setup.created).append(description)

    # Indexes, including the text index
    existing_indexes = await run("SHOW INDEX INFO")
    for label, properties in INDEXES:
        description = f"index :{label}({', '.join(properties)})"
        existed = any(
            row["index type"] == "label+property"
            and row["label"] == label
            and row["property"] == list(properties)
            for row in existing_indexes
        )
        if not existed:
            await run(f"CREATE INDEX ON :{label}({', '.join(properties)})")
        record(description, existed)

    name, label, property_name = TEXT_INDEX
    existed = any(
        row["index type"] == f"label_text (name: {name})" for row in existing_indexes
    )
    if not existed:
        await run(f"CREATE TEXT INDEX {name} ON :{label}({property_name})")
    record(f"text index {name} on :{label}({property_name})", existed)

    # Uniqueness of ids
    existing_constraints = await run("SHOW CONSTRAINT INFO")
    for label, property_name in UNIQUE_CONSTRAINTS:
        existed = any(
            row["constraint type"] == "unique"
            and row["label"] == label
            and row["properties"] == [property_name]
            for row in existing_constraints
        )
        if not existed:
            await run(
                f"CREATE CONSTRAINT ON (n:{label}) ASSERT n.{property_name} IS UNIQUE"
            )
        record(f"unique constraint on :{label}({property_name})", existed)

    # Enums
    existing_enums = {
        row["Enum Name"]: row["Enum Values"] for row in await run("SHOW ENUMS")
    }
    for enum_name, names in enum_members(enums_used_by_models()).items():
        if enum_name not in existing_enums:
            await run(f"CREATE ENUM {enum_name} VALUES {{ {', '.join(names)} }}")
            record(f"enum {enum_name}", False)
            continue
        missing = [name for name in names if name not in existing_enums[enum_name]]
        for name in missing:
            await run(f"ALTER ENUM {enum_name} ADD VALUE {name}")
        if missing:
            setup.created.append(f"enum {enum_name}: added {', '.join(missing)}")
        else:
            record(f"enum {enum_name}", True)

    return setup
