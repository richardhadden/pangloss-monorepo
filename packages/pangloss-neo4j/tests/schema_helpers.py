"""Looking at the indexes and constraints of the test database (Neo4j's `SHOW INDEXES` and `SHOW CONSTRAINTS`)"""

from typing import Any

INDEXES = (
    "SHOW INDEXES YIELD name, type, entityType, labelsOrTypes, properties, owningConstraint "
    "WHERE type <> 'LOOKUP' AND entityType = 'NODE' RETURN *"
)
CONSTRAINTS = (
    "SHOW CONSTRAINTS YIELD name, type, entityType, labelsOrTypes, properties "
    "WHERE entityType = 'NODE' RETURN *"
)


def show(db_driver, statement: str) -> list[dict[str, Any]]:
    with db_driver.session() as session:  # (not in a transaction)
        return session.run(statement).data()


def indexes(db_driver) -> list[dict[str, Any]]:
    return show(db_driver, INDEXES)


def has_index(db_driver, entry: dict) -> bool:
    """Whether the index of an entry of the snapshot is there. A label has an index in every database, always: `True`"""
    if entry["kind"] == "label":
        return True
    rows = indexes(db_driver)
    if entry["kind"] == "text":
        return any(r["type"] == "FULLTEXT" and r["name"] == entry["name"] for r in rows)
    return any(
        r["type"] == "RANGE"
        and r["labelsOrTypes"] == [entry["label"]]
        and r["properties"] == list(entry["properties"])
        for r in rows
    )


def has_constraint(db_driver, entry: dict) -> bool:
    return any(
        "UNIQUENESS" in r["type"]
        and r["labelsOrTypes"] == [entry["label"]]
        and sorted(r["properties"]) == sorted(entry["properties"])
        for r in show(db_driver, CONSTRAINTS)
    )


def drop_indexes_of(db_driver, labels: set[str]) -> None:
    """Drop the indexes (that are not a constraint's) of nodes with these labels"""
    with db_driver.session() as session:
        for row in indexes(db_driver):
            if (
                row["owningConstraint"] is None
                and set(row["labelsOrTypes"] or ()) & labels
            ):
                session.run(f"DROP INDEX `{row['name']}`").consume()
