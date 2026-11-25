"""Looking underneath, in the database of the backend under test (`pangloss_testing.backends.under_test`): the Cypher the
conformance tests run beside the models. Written as for Memgraph, where a node has a `meta` map; on Neo4j, which keeps it
as flat properties, `run` translates the query and nests the maps of the result again."""

import re
from typing import Any

from pangloss_testing.backends import under_test

# The name of the test database (for the driver's `database=`)
DATABASE_NAME = under_test().database


def memgraph_meta(cypher: str) -> str:
    """Cypher written as for Memgraph, for the backend under test. On Neo4j a node has flat properties (`meta.created_by`...)
    for its `meta`: `n.meta AS meta` is the map made of them, `n.meta.semantic_spaces` the property, and
    `n.meta.context_labels AS x` the list (which `run` nests again)"""
    if under_test().name != "neo4j":
        return cypher
    from pangloss_neo4j.databases.neo4j.properties import meta_map

    cypher = re.sub(
        r"\b(\w+)\.meta\.(context_labels|path)\b(\s+AS\s+)(\w+)",
        r"\1.`meta.\2#json`\3`\4#json`",
        cypher,
    )
    cypher = re.sub(r"\b(\w+)\.meta\.(\w+)", r"\1.`meta.\2`", cypher)
    return re.sub(r"\b(\w+)\.meta(\s+AS\b)", lambda m: meta_map(m[1]) + m[2], cypher)


def decoded(row: dict[str, Any]) -> dict[str, Any]:
    if under_test().name != "neo4j":
        return row
    from pangloss_neo4j.databases.neo4j.properties import decode

    return decode(row)


def run(db_driver, cypher: str, **params) -> list[dict]:
    """Run a query against the test database and return each record as a dict (a node as its properties, with its maps as
    the backend gives them). `n.meta` may be asked for as it is in Memgraph."""
    records, _, _ = db_driver.execute_query(
        memgraph_meta(cypher), parameters_=params, database_=DATABASE_NAME
    )
    return [decoded(r.data()) for r in records]


def labels_of(db_driver, node_id) -> set[str]:
    rows = run(db_driver, "MATCH (n {id: $id}) RETURN labels(n) AS l", id=str(node_id))
    assert len(rows) == 1, f"expected exactly one node with id {node_id}"
    return set(rows[0]["l"])


def count_nodes(db_driver, label: str) -> int:
    return run(db_driver, f"MATCH (n:{label}) RETURN count(n) AS c")[0]["c"]


def native(value):
    """Convert neo4j temporal types to Python natives"""
    return value.to_native() if hasattr(value, "to_native") else value


def index_labels(db_driver) -> set[str]:
    """The labels that have an index of their own (not those of a constraint)"""
    with db_driver.session(database=DATABASE_NAME) as session:  # (not in a transaction)
        if under_test().name == "neo4j":
            rows = session.run(
                "SHOW INDEXES YIELD type, entityType, labelsOrTypes, owningConstraint "
                "WHERE type <> 'LOOKUP' AND entityType = 'NODE' RETURN labelsOrTypes"
            ).data()
            return {label for r in rows for label in r["labelsOrTypes"] or []}
        return {r["label"] for r in session.run("SHOW INDEX INFO").data()}


def assert_paths_true(db_driver) -> None:
    """Every node below a head in the database has the path its place gives it: its parent's path and its parent,
    by the field that holds it, with the semantic spaces of that path (`pangloss_models.context`). Looked at
    underneath, from the edges alone, so it holds for what the models wrote and for what a migration left"""
    rows = run(
        db_driver,
        """
        MATCH (p)-[e]->(n)
        WHERE n.head_node_id IS NOT NULL AND n.meta.created_by IS NOT NULL
          AND NOT coalesce(e.reverse, false)
          AND (p.id = n.head_node_id OR p.head_node_id = n.head_node_id)
        RETURN n.id AS id, n.type AS type, n.meta.path AS path, n.meta.semantic_spaces AS spaces,
               p.id AS parent, p.type AS parent_type, type(e) AS field, p.meta.path AS parent_path
        """,
    )
    nodes: dict[str, list[dict]] = {}
    for row in rows:
        nodes.setdefault(row["id"], []).append(row)
    for id, held_by in nodes.items():
        path = held_by[0]["path"]
        assert path, f"{held_by[0]['type']} {id} has no path"
        assert any(
            path[:-1] == (row["parent_path"] or [])
            and path[-1]["id"] == row["parent"]
            and path[-1]["type"] == row["parent_type"]
            and path[-1]["field"] == row["field"]
            for row in held_by
        ), (
            f"{held_by[0]['type']} {id} has the path {path}, and is held by "
            f"{[(row['parent_type'], row['field'], row['parent_path']) for row in held_by]}"
        )
        assert (held_by[0]["spaces"] or []) == [
            entry["type"] for entry in path if entry["kind"] == "space"
        ], (
            f"{held_by[0]['type']} {id}: {held_by[0]['spaces']} is not the spaces of {path}"
        )
