"""Step 2.2's trials by hand on the scratch Memgraph (`:7702`): a vector index dropped and made again under the same
name with another dimension, and a vector index after a snapshot is recovered.

    uv run python notes/similarity-evaluation/vector_index_trial_3.py
"""

import neo4j

d = neo4j.GraphDatabase.driver("bolt://localhost:7702", auth=("test", "test"))


def run(q, **p):
    with d.session() as s:
        return [r.data() for r in s.run(q, **p)]


def attempt(said, q, **p):
    try:
        print(said, "->", run(q, **p))
    except Exception as error:  # noqa: BLE001
        print(said, "-> REFUSED:", str(error)[:160])


def info():
    return [(r["index_name"], r["dimension"], r["size"]) for r in run("SHOW VECTOR INDEX INFO")]


def make(dimension):
    attempt(f"create({dimension})", 'CREATE VECTOR INDEX pg_t ON :PGT(v) WITH CONFIG {"dimension": %d, "capacity": 64, "metric": "cos"}' % dimension)


run("DROP VECTOR INDEX pg_t")
run("MATCH (n:PGT) DETACH DELETE n")
run("FREE MEMORY")
print("== 1. drop, delete the nodes, make again with dimension 3")
make(2)
run("UNWIND range(1, 5) AS i CREATE (:PGT {i: i, v: [1.0, toFloat(i)]})")
print(info())
run("DROP VECTOR INDEX pg_t")
print("after drop:", info())
run("MATCH (n:PGT) DETACH DELETE n")
make(3)
print("after create(3), the deleted nodes not yet collected:", info())
run("FREE MEMORY")
make(3)
print("after FREE MEMORY and create(3):", info())
attempt("write of 3", "CREATE (:PGT {i: 9, v: [1.0, 2.0, 3.0]})")

print("== 2. the same, the nodes left in place with their vectors of 2")
run("DROP VECTOR INDEX pg_t")
run("MATCH (n:PGT) DETACH DELETE n")
run("FREE MEMORY")
make(2)
run("UNWIND range(1, 5) AS i CREATE (:PGT {i: i, v: [1.0, toFloat(i)]})")
run("DROP VECTOR INDEX pg_t")
attempt("create(3) over nodes of 2", 'CREATE VECTOR INDEX pg_t ON :PGT(v) WITH CONFIG {"dimension": 3, "capacity": 64, "metric": "cos"}')
print(info())
attempt("remove the property", "MATCH (n:PGT) REMOVE n.v")
make(3)
print(info())
attempt("write of 3", "CREATE (:PGT {i: 9, v: [1.0, 2.0, 3.0]})")
attempt("set a node of 2 to 3", "MATCH (n:PGT {i: 1}) SET n.v = [1.0, 2.0, 3.0]")
print(info())

print("== 3. a snapshot recovered")
run("DROP VECTOR INDEX pg_t")
run("MATCH (n:PGT) DETACH DELETE n")
run("FREE MEMORY")
make(2)
run("UNWIND range(1, 5) AS i CREATE (:PGT {i: i, v: [1.0, toFloat(i)]})")
snapshot = run("CREATE SNAPSHOT")
print(snapshot)
run("CREATE (:PGT {i: 6, v: [1.0, 6.0]})")
path = snapshot[0].get("path") if snapshot else None
attempt("recover", f'RECOVER SNAPSHOT "{path}" FORCE')
print(info())
attempt("search", "CALL vector_search.search('pg_t', 3, [1.0, 5.0]) YIELD node, distance RETURN node.i AS i, distance")
attempt("write after", "CREATE (:PGT {i: 7, v: [1.0, 7.0]})")
print(info())
run("DROP VECTOR INDEX pg_t")
run("MATCH (n:PGT) DETACH DELETE n")
