"""Setting up a Memgraph database for Pangloss.

`initialise_database` creates what the queries rely on: indexes, uniqueness
constraints for ids, and the text index used for searching labels. It can be run
again at any time: whatever already exists is left alone.

(Enums are not made: a field of an `Enum` type is stored as the value of the member, a
string or a number, like any other property.)
"""

import dataclasses
from typing import Any

import neo4j

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
    ("PGUndeletion", "id"),
    ("PGUrl", "url"),
    ("PGUser", "username"),
    ("PGUser", "email"),
    ("PGAccessToken", "token_hash"),
    ("PGRevokedSession", "jti"),
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


# The app whose migrations make this structure: this package (`pangloss_memgraph.migrations`), which
# keeps the users and the records of creation as well. A project that does not install it has the
# structure made by the migrations of its first app.
STRUCTURE_APP = "pangloss_memgraph"


def structure() -> dict[str, list[dict[str, Any]]]:
    """The indexes and constraints a database needs, as the snapshot of the models has them (so
    that migrations make them, and a change to this list is a migration)"""
    indexes: list[dict[str, Any]] = [
        {"kind": "label+property", "label": label, "properties": list(properties)}
        for label, properties in INDEXES
    ]
    name, label, property_name = TEXT_INDEX
    indexes.append({"kind": "text", "label": label, "properties": [property_name], "name": name})
    constraints = [
        {"kind": "unique", "label": label, "properties": [property_name]}
        for label, property_name in UNIQUE_CONSTRAINTS
    ]
    for entry in [*indexes, *constraints]:
        entry["app"] = STRUCTURE_APP
    return {"indexes": indexes, "constraints": constraints}


@dataclasses.dataclass
class DatabaseSetup:
    """What `initialise_database` did"""

    created: list[str] = dataclasses.field(default_factory=list)
    already_present: list[str] = dataclasses.field(default_factory=list)


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
    """Set up the database: indexes, constraints and the text index.

    Creates, if they do not exist already:

    - for the ids (which are UUIDs) of every kind of node that has one, and for
      the URLs of entities, an index and a uniqueness constraint;
    - an index of `id` and `head_node_id` together, and one of `id` for head nodes;
    - the text index `label_text` on the `label` of every `PGIndexableNode`, used
      for searching.

    Uses the default `Database`, unless given one.
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

    return setup
