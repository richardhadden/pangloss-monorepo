"""Helpers shared by the tests"""

import re

from pangloss_neo4j.databases.neo4j.properties import decode, meta_map


def memgraph_meta(cypher: str) -> str:
    """Cypher written as for Memgraph, where a node has a `meta` map, as Cypher for Neo4j, where it has flat properties
    (`meta.created_by`...): `n.meta AS meta` is the map made of them, `n.meta.semantic_spaces` the property, and
    `n.meta.context_labels AS x` the list (the helper nests it again)"""
    cypher = re.sub(
        r"\b(\w+)\.meta\.context_labels\b(\s+AS\s+)(\w+)",
        r"\1.`meta.context_labels#json`\2`\3#json`",
        cypher,
    )
    cypher = re.sub(r"\b(\w+)\.meta\.(\w+)", r"\1.`meta.\2`", cypher)
    return re.sub(r"\b(\w+)\.meta(\s+AS\b)", lambda m: meta_map(m[1]) + m[2], cypher)


def run(db_driver, cypher: str, **params) -> list[dict]:
    """Run a query against the test database and return each record as a dict (a node as its properties, with the
    maps that Neo4j keeps flat nested again, as the backend gives them). `n.meta` may be asked for as it is in Memgraph."""
    records, _, _ = db_driver.execute_query(memgraph_meta(cypher), parameters_=params)
    return [decode(r.data()) for r in records]


def labels_of(db_driver, node_id) -> set[str]:
    rows = run(db_driver, "MATCH (n {id: $id}) RETURN labels(n) AS l", id=str(node_id))
    assert len(rows) == 1, f"expected exactly one node with id {node_id}"
    return set(rows[0]["l"])


def count_nodes(db_driver, label: str) -> int:
    return run(db_driver, f"MATCH (n:{label}) RETURN count(n) AS c")[0]["c"]


def native(value):
    """Convert neo4j temporal types to Python natives"""
    return value.to_native() if hasattr(value, "to_native") else value


# The Neo4j of its own that the bulk load tests use (see `conftest.bulk_neo4j`)
BULK_URI = "bolt://localhost:7694"
