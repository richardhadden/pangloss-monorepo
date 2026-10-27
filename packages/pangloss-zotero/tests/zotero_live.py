"""A live Memgraph (the test one on :7687, as the other packages' tests use), if there is one"""

import neo4j
import pytest

MEMGRAPH_URI = "bolt://localhost:7687"
MEMGRAPH_AUTH = ("test", "test")
MEMGRAPH_DATABASE = "memgraph"


def reachable() -> bool:
    driver = neo4j.GraphDatabase.driver(MEMGRAPH_URI, auth=MEMGRAPH_AUTH)
    try:
        driver.verify_connectivity()
        return True
    except Exception:
        return False
    finally:
        driver.close()


needs_memgraph = pytest.mark.skipif(
    not reachable(), reason="no test Memgraph on localhost:7687"
)
