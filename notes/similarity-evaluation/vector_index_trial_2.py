"""More of phase 1's trials on Memgraph (:7702): a deleted node in a vector search, and the capacity. See
`vector_index_trial.py`."""

import neo4j

driver = neo4j.GraphDatabase.driver("bolt://localhost:7702", auth=("test", "test"))


def run(cypher, **params):
    with driver.session() as session:
        return [r.data() for r in session.run(cypher, **params)]


def attempt(title, function):
    print(f"\n--- {title}")
    try:
        print("   ", function())
    except Exception as error:
        print(f"    FAILED {type(error).__name__}: {str(error)[:300]}")


V = [1.0, 0.0, 0.0, 0.0]
run("MATCH (n:TrialVector) DETACH DELETE n")
run("DROP VECTOR INDEX trial_vectors")
run('CREATE VECTOR INDEX trial_vectors ON :TrialVector(vector) WITH CONFIG {"dimension": 4, "capacity": 16, "metric": "cos"}')
run("UNWIND range(0, 9) AS i CREATE (:TrialVector {of: i, vector: [1.0, toFloat(i) / 10, 0.0, 0.0]})")
run("MATCH (n:TrialVector {of: 0}) DETACH DELETE n")
SEARCH = "CALL vector_search.search('trial_vectors', 3, $v) YIELD node, similarity "
attempt("deleted: a property of the node", lambda: run(SEARCH + "RETURN node.of AS of, similarity", v=V))
attempt("deleted: only the similarity", lambda: run(SEARCH + "RETURN similarity", v=V))
attempt("deleted: id(node)", lambda: run(SEARCH + "RETURN id(node) AS i, similarity", v=V))
attempt("deleted: labels(node)", lambda: run(SEARCH + "RETURN labels(node) AS l, similarity", v=V))
attempt(
    "deleted: matched again by id",
    lambda: run(SEARCH + "WITH id(node) AS i, similarity MATCH (n) WHERE id(n) = i RETURN n.of AS of, similarity", v=V),
)
attempt("the index's size", lambda: run("SHOW VECTOR INDEX INFO"))
attempt("FREE MEMORY, then a property", lambda: (run("FREE MEMORY"), run(SEARCH + "RETURN node.of AS of, similarity", v=V)))
import time

time.sleep(3)
attempt("three seconds later", lambda: run(SEARCH + "RETURN node.of AS of, similarity", v=V))
attempt("the index's size", lambda: run("SHOW VECTOR INDEX INFO"))

run("MATCH (n:TrialVector) DETACH DELETE n")
run("FREE MEMORY")
attempt(
    "100 nodes into a capacity of 16 (64)",
    lambda: run("UNWIND range(0, 99) AS i CREATE (:TrialVector {of: i, vector: [0.0, 1.0, toFloat(i) / 100, 0.0]})"),
)
attempt("the index after", lambda: run("SHOW VECTOR INDEX INFO"))
attempt("found of 100 asked", lambda: len(run("CALL vector_search.search('trial_vectors', 100, $v) YIELD node, similarity RETURN similarity", v=[0.0, 1.0, 0.5, 0.0])))
attempt(
    "5,000 more",
    lambda: run("UNWIND range(100, 5099) AS i CREATE (:TrialVector {of: i, vector: [0.0, 1.0, toFloat(i) / 100, 0.0]})"),
)
attempt("the index after", lambda: run("SHOW VECTOR INDEX INFO"))
attempt("unset the vector of one: still found?", lambda: (run("MATCH (n:TrialVector {of: 50}) REMOVE n.vector"), run("SHOW VECTOR INDEX INFO")))
attempt("label removed", lambda: (run("MATCH (n:TrialVector {of: 51}) REMOVE n:TrialVector"), run("SHOW VECTOR INDEX INFO")))
attempt("a second index on the same label and property", lambda: run('CREATE VECTOR INDEX trial_vectors_2 ON :TrialVector(vector) WITH CONFIG {"dimension": 4, "capacity": 16, "metric": "cos"}'))
attempt("the same name, another label", lambda: run('CREATE VECTOR INDEX trial_vectors ON :TrialOther(vector) WITH CONFIG {"dimension": 4, "capacity": 16}'))
attempt("indexes", lambda: run("SHOW VECTOR INDEX INFO"))
run("MATCH (n:TrialVector) DETACH DELETE n")
run("DROP VECTOR INDEX trial_vectors")
run("DROP VECTOR INDEX trial_vectors_2")

# a module that does not import: what the caller can find out
run("CALL mg.create_module_file('pg_trial_broken.py', 'import mgp\nimport no_such_module_at_all\n') YIELD path RETURN path")
attempt("procedures of the broken module", lambda: run("CALL mg.procedures() YIELD name WITH name WHERE name STARTS WITH 'pg_trial' RETURN name"))
attempt("mg.load_all", lambda: run("CALL mg.load_all()"))
for row in run("CALL mg.get_module_files() YIELD path RETURN path"):
    if "/pg_trial_" in row["path"]:
        run("CALL mg.delete_module_file($p)", p=row["path"])
driver.close()
