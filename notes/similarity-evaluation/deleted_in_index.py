"""Step 2.4: how long a deleted node keeps its place among the `k` of a vector search on Memgraph (`:7702`), with
nothing done to hurry the database (no `FREE MEMORY`).

    uv run python notes/similarity-evaluation/deleted_in_index.py
"""

import time

import neo4j

d = neo4j.GraphDatabase.driver("bolt://localhost:7702", auth=("test", "test"))


def run(q, **p):
    with d.session() as s:
        return [r.data() for r in s.run(q, **p)]


SEARCH = (
    "CALL vector_search.search('pg_gone', $k, [1.0, 0.0]) YIELD node AS hit, distance "
    "WITH id(hit) AS i, distance MATCH (n) WHERE id(n) = i RETURN count(n) AS found"
)
run("DROP VECTOR INDEX pg_gone")
run("MATCH (n:PGGone) DETACH DELETE n")
run("FREE MEMORY")
run('CREATE VECTOR INDEX pg_gone ON :PGGone(v) WITH CONFIG {"dimension": 2, "capacity": 1024, "metric": "cos"}')
# (the 150 nearest the query are the ones deleted)
run("UNWIND range(1, 200) AS i CREATE (:PGGone {i: i, v: [1.0, toFloat(i) / 100]})")
print("before:", run(SEARCH, k=10)[0]["found"], "of 10")
run("MATCH (n:PGGone) WHERE n.i <= 150 DETACH DELETE n")
began = time.perf_counter()
last = None
while time.perf_counter() - began < 120:
    found = run(SEARCH, k=10)[0]["found"]
    if found != last:
        print(f"{time.perf_counter() - began:6.1f} s after the delete: {found} of 10 (asking for 40: "
              f"{run(SEARCH, k=40)[0]['found']}, for 200: {run(SEARCH, k=200)[0]['found']})")
        last = found
    if found == 10:
        break
    time.sleep(0.5)
print(run("SHOW VECTOR INDEX INFO"))
run("DROP VECTOR INDEX pg_gone")
run("MATCH (n:PGGone) DETACH DELETE n")
