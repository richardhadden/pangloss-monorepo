"""Helpers shared by the tests"""



def run(db_driver, cypher: str, **params) -> list[dict]:
    """Run a query against the test database and return each record as a dict"""
    records, _, _ = db_driver.execute_query(cypher, parameters_=params)
    return [r.data() for r in records]


def labels_of(db_driver, node_id) -> set[str]:
    rows = run(db_driver, "MATCH (n {id: $id}) RETURN labels(n) AS l", id=str(node_id))
    assert len(rows) == 1, f"expected exactly one node with id {node_id}"
    return set(rows[0]["l"])


def count_nodes(db_driver, label: str) -> int:
    return run(db_driver, f"MATCH (n:{label}) RETURN count(n) AS c")[0]["c"]


def native(value):
    """Convert neo4j temporal types to Python natives"""
    return value.to_native() if hasattr(value, "to_native") else value


def mg_enum(value: str) -> dict:
    """How the driver gives a Memgraph enum value, e.g. `mg_enum("Colour::RED")`"""
    return {"__type": "mg_enum", "__value": value}
