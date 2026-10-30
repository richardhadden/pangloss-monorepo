"""Setting up a Neo4j database for Pangloss.

`initialise_database` creates what the queries rely on: uniqueness
constraints for ids, indexes, and the full-text index used for searching labels. It can be run
again at any time: whatever already exists is left alone.

(Enums are not made: a field of an `Enum` type is stored as the value of the member, a
string or a number, like any other property.)
"""

import dataclasses
import importlib
from typing import Any

from pangloss_models.indexes import model_indexes

from pangloss_neo4j.databases.neo4j.database import Database
from pangloss_neo4j.databases.neo4j.schema import (
    TEXT_INDEX_NAME,
    await_indexes,
    create_constraint_statement,
    create_index_statement,
    has_constraint,
    has_index,
    list_constraints,
    list_indexes,
    run_statement,
)

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
    ("PGUndeletion", "id"),
    ("PGUrl", "url"),
    ("PGUser", "username"),
    ("PGUser", "email"),
    ("PGAccessToken", "token_hash"),
    ("PGRevokedSession", "jti"),
    ("PGLock", "key"),
]

# (label, properties). Each unique property is indexed, for finding a node; and an id
# with its head node's id, for finding a node of a particular document; the head node's
# id alone, for the nodes of a document (structured search, in an `EXISTS`: Neo4j 3.14
# uses it there, 3.13 did not); and head nodes, as they are found by id by the queries of
# updates and reads
INDEXES = [
    *[(label, (property_name,)) for label, property_name in UNIQUE_CONSTRAINTS],
    ("PGIndexableNode", ("id", "head_node_id")),
    ("PGIndexableNode", ("head_node_id",)),
    ("HeadNode", ("id",)),
]

TEXT_INDEX = (TEXT_INDEX_NAME, "PGIndexableNode", "label")


# The app whose migrations make this structure: this package (`pangloss_neo4j.migrations`), which
# keeps the users and the records of creation as well. A project that does not install it has the
# structure made by the migrations of its first app.
STRUCTURE_APP = "pangloss_neo4j"


def installed_app_structure() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The indexes and constraints that installed apps ask for, for nodes that are not models (the calendar's days):
    an app with a `structure` module has `INDEXES` and `CONSTRAINTS`, lists of entries as in the snapshot
    (`{"kind": "label+property", "label": "CalendarDay", "properties": ["jdn"]}`). The app's own migrations make them."""
    from pangloss_core import settings as core_settings

    settings = core_settings.__dict__.get("SETTINGS")
    indexes: list[dict[str, Any]] = []
    constraints: list[dict[str, Any]] = []
    for app in getattr(settings, "INSTALLED_APPS", []):
        try:
            module = importlib.import_module(f"{app}.structure")
        except ModuleNotFoundError as error:
            if error.name in (app, f"{app}.structure"):
                continue
            raise
        for source, found in (
            (getattr(module, "INDEXES", []), indexes),
            (getattr(module, "CONSTRAINTS", []), constraints),
        ):
            found += [{**entry, "app": app} for entry in source]
    return indexes, constraints


def structure() -> dict[str, list[dict[str, Any]]]:
    """The indexes and constraints a database needs, as the snapshot of the models has them (so
    that migrations make them, and a change to this list is a migration)"""
    indexes: list[dict[str, Any]] = [
        {"kind": "label+property", "label": label, "properties": list(properties)}
        for label, properties in INDEXES
    ]
    name, label, property_name = TEXT_INDEX
    indexes.append(
        {"kind": "text", "label": label, "properties": [property_name], "name": name}
    )
    constraints = [
        {"kind": "unique", "label": label, "properties": [property_name]}
        for label, property_name in UNIQUE_CONSTRAINTS
    ]
    for entry in [*indexes, *constraints]:
        entry["app"] = STRUCTURE_APP
    extra_indexes, extra_constraints = installed_app_structure()
    indexes += extra_indexes
    constraints += extra_constraints
    # The indexes of the models (a label index for each class, and the fields they ask for): the app
    # of the model makes them, which the planner works out from the model (no `app` here)
    indexes += model_indexes()
    return {"indexes": indexes, "constraints": constraints}


@dataclasses.dataclass
class DatabaseSetup:
    """What `initialise_database` did"""

    created: list[str] = dataclasses.field(default_factory=list)
    already_present: list[str] = dataclasses.field(default_factory=list)


# ---------------------------------------------------------------------------
# Setting up
# ---------------------------------------------------------------------------


def describe_index(entry: dict[str, Any]) -> str:
    if entry["kind"] == "text":
        name = entry.get("name") or TEXT_INDEX_NAME
        return (
            f"text index {name} on :{entry['label']}({', '.join(entry['properties'])})"
        )
    properties = ", ".join(entry["properties"])
    return f"index :{entry['label']}" + (f"({properties})" if properties else "")


async def initialise_database(database: Database | None = None) -> DatabaseSetup:
    """Set up the database: constraints, indexes and the text index.

    Creates, if they do not exist already:

    - for the ids (which are UUIDs) of every kind of node that has one, and for the URLs of entities, a uniqueness
      constraint (which makes an index of its own, so none is made for it);
    - an index of `id` and `head_node_id` together, and one of `id` for head nodes, and of the fields that models ask for
      (the index of a label is there already: every Neo4j database has one);
    - the full-text index `label_text` on the `label` of every `PGIndexableNode`, used for searching.

    The constraints are made first (an index made before one fails it). Uses the default `Database`, unless given one.
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

    # Uniqueness of ids (and the indexes that come with it)
    existing_constraints = await list_constraints(driver, database_name)
    made_with_constraint: set[tuple[str, tuple[str, ...]]] = set()
    for label, property_name in UNIQUE_CONSTRAINTS:
        entry = {"kind": "unique", "label": label, "properties": [property_name]}
        existed = has_constraint(existing_constraints, entry) is not None
        if not existed:
            await run(create_constraint_statement(entry))
            made_with_constraint.add((label, (property_name,)))
        record(f"unique constraint on :{label}({property_name})", existed)

    # Indexes, including the text index
    existing_indexes = await list_indexes(driver, database_name)
    wanted = [
        {"kind": "label+property", "label": label, "properties": list(properties)}
        for label, properties in INDEXES
    ] + model_indexes()
    for entry in wanted:
        description = describe_index(entry)
        key = (entry["label"], tuple(entry["properties"]))
        if entry["kind"] == "label":
            record(
                description, True
            )  # (the lookup index of labels, which is always there)
        elif key in made_with_constraint:
            record(description, False)  # (made with its constraint, just now)
        elif has_index(existing_indexes, entry) is not None:
            record(description, True)
        else:
            statement = create_index_statement(entry)
            if statement is not None:
                await run(statement)
            record(description, False)

    name, label, property_name = TEXT_INDEX
    text = {"kind": "text", "label": label, "properties": [property_name], "name": name}
    existed = has_index(existing_indexes, text) is not None
    if not existed:
        statement = create_index_statement(text)
        assert statement is not None
        await run(statement)
    record(describe_index(text), existed)

    await await_indexes(driver, database_name)
    return setup
