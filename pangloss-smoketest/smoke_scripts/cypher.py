"""Run a read-only Cypher query on the smoke test's Memgraph (:7697) and print the rows"""

import sys
import time

from neo4j import GraphDatabase

q = sys.argv[1]
with GraphDatabase.driver("bolt://localhost:7697", auth=("test", "test")) as d:
    t = time.perf_counter()
    rows, summary, keys = d.execute_query(q, database_="memgraph")
    took = time.perf_counter() - t
    for r in rows[:50]:
        print(dict(r))
    print(f"({len(rows)} rows, {took * 1000:.0f} ms)")
