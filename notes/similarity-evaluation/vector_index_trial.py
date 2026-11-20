"""Phase 1's trials by hand (steps 1.3, 1.4 and 1.5 of implementation_docs/similarity-build-plan.md): the DDL of a
vector index on each backend, how each lists one, the search call, what Memgraph does at capacity, a deleted node;
and whether one query module of Memgraph can import another, and what an import error looks like.

On scratch containers only (`pangloss-memgraph-similar` :7702, `pangloss-neo4j-similar` :7703): it deletes nodes
with the label `TrialVector`, drops the index `trial_vectors`, and the module files `pg_trial_*.py`.

    uv run python notes/similarity-evaluation/vector_index_trial.py
"""

import time
import traceback

import neo4j

MEMGRAPH = ("bolt://localhost:7702", ("test", "test"))
NEO4J = ("bolt://localhost:7703", ("neo4j", "test-password"))


def run(driver, cypher, **params):
    # (auto-commit: Memgraph refuses DDL and the module procedures in a transaction of several commands)
    with driver.session() as session:
        return [r.data() for r in session.run(cypher, **params)]


def attempt(title, function):
    print(f"\n--- {title}")
    try:
        result = function()
        if result is not None:
            print("   ", result)
    except Exception as error:
        print(f"    FAILED {type(error).__name__}: {str(error)[:400]}")


def vectors(n, dimension=4):
    # (known, and apart: the i-th leans further from the first axis)
    return [[1.0, i / n, 0.0, 0.0][:dimension] for i in range(n)]


def memgraph():
    driver = neo4j.GraphDatabase.driver(MEMGRAPH[0], auth=MEMGRAPH[1])
    print("=== Memgraph", run(driver, "SHOW VERSION"))
    return_ = None  # noqa: F841
    run(driver, "MATCH (n:TrialVector) DETACH DELETE n")
    attempt("drop (none there)", lambda: run(driver, "DROP VECTOR INDEX trial_vectors"))
    attempt(
        "create",
        lambda: run(
            driver,
            'CREATE VECTOR INDEX trial_vectors ON :TrialVector(vector) '
            'WITH CONFIG {"dimension": 4, "capacity": 16, "metric": "cos"}',
        ),
    )
    attempt(
        "create again",
        lambda: run(
            driver,
            'CREATE VECTOR INDEX trial_vectors ON :TrialVector(vector) '
            'WITH CONFIG {"dimension": 4, "capacity": 16, "metric": "cos"}',
        ),
    )
    attempt("SHOW INDEX INFO", lambda: run(driver, "SHOW INDEX INFO"))
    attempt("SHOW VECTOR INDEX INFO", lambda: run(driver, "SHOW VECTOR INDEX INFO"))
    attempt(
        "vector_search.show_index_info",
        lambda: run(driver, "CALL vector_search.show_index_info() YIELD * RETURN *"),
    )
    run(
        driver,
        "UNWIND range(0, 9) AS i CREATE (:TrialVector {of: i, vector: $vectors[i]})",
        vectors=vectors(10),
    )
    attempt(
        "search, nearest 3 to the first",
        lambda: run(
            driver,
            "CALL vector_search.search('trial_vectors', 3, $v) YIELD node, similarity, distance "
            "RETURN node.of AS of, similarity, distance",
            v=[1.0, 0.0, 0.0, 0.0],
        ),
    )
    attempt(
        "search, the vector as a parameter in a subquery after a MATCH",
        lambda: run(
            driver,
            "MATCH (q:TrialVector {of: 9}) WITH q.vector AS v "
            "CALL vector_search.search('trial_vectors', 3, v) YIELD node, similarity "
            "RETURN node.of AS of, similarity",
        ),
    )

    def deleted():
        run(driver, "MATCH (n:TrialVector {of: 0}) DETACH DELETE n")
        return run(
            driver,
            "CALL vector_search.search('trial_vectors', 3, $v) YIELD node, similarity "
            "RETURN node.of AS of, similarity",
            v=[1.0, 0.0, 0.0, 0.0],
        )

    attempt("a node deleted, then searched in another transaction", deleted)

    def deleted_in_one():
        with driver.session() as session:
            with session.begin_transaction() as tx:
                tx.run("MATCH (n:TrialVector {of: 1}) DETACH DELETE n").consume()
                rows = [
                    r.data()
                    for r in tx.run(
                        "CALL vector_search.search('trial_vectors', 3, $v) YIELD node, similarity "
                        "RETURN node.of AS of, similarity",
                        v=[1.0, 0.0, 0.0, 0.0],
                    )
                ]
                tx.commit()
                return rows

    attempt("a node deleted and searched in one transaction", deleted_in_one)

    def past_capacity():
        run(
            driver,
            "UNWIND range(100, 139) AS i CREATE (:TrialVector {of: i, vector: [0.0, 1.0, toFloat(i) / 100, 0.0]})",
        )
        return (
            run(driver, "MATCH (n:TrialVector) RETURN count(n) AS nodes"),
            run(driver, "CALL vector_search.show_index_info() YIELD * RETURN *"),
            len(
                run(
                    driver,
                    "CALL vector_search.search('trial_vectors', 100, $v) YIELD node RETURN node.of AS of",
                    v=[0.0, 1.0, 1.2, 0.0],
                )
            ),
        )

    attempt("40 more nodes, past the capacity of 16", past_capacity)
    attempt(
        "a vector of the wrong dimension",
        lambda: run(driver, "CREATE (:TrialVector {of: 999, vector: [1.0, 2.0]})"),
    )
    attempt(
        "a vector that is a list of integers",
        lambda: run(driver, "CREATE (:TrialVector {of: 998, vector: [1, 2, 3, 4]})"),
    )
    attempt(
        "reading the indexed property back",
        lambda: run(driver, "MATCH (n:TrialVector {of: 5}) RETURN n.vector AS vector, properties(n) AS p"),
    )
    attempt(
        "setting a vector in place, then searching",
        lambda: (
            run(driver, "MATCH (n:TrialVector {of: 5}) SET n.vector = [0.0, 0.0, 0.0, 1.0]"),
            run(
                driver,
                "CALL vector_search.search('trial_vectors', 1, $v) YIELD node, similarity "
                "RETURN node.of AS of, similarity",
                v=[0.0, 0.0, 0.0, 1.0],
            ),
        ),
    )
    attempt("drop", lambda: run(driver, "DROP VECTOR INDEX trial_vectors"))
    attempt("drop again", lambda: run(driver, "DROP VECTOR INDEX trial_vectors"))
    run(driver, "MATCH (n:TrialVector) DETACH DELETE n")

    # --- 1.5: query modules ---
    print("\n=== Memgraph: query modules")
    maths = "def double(x):\n    return 2 * x\n"
    main = (
        "import mgp\nimport pg_trial_maths\n\n"
        "@mgp.read_proc\n"
        "def twice(ctx: mgp.ProcCtx, x: int) -> mgp.Record(result=int):\n"
        "    return mgp.Record(result=pg_trial_maths.double(x))\n"
    )
    broken = "import mgp\nimport no_such_module_at_all\n"
    attempt(
        "the files that are there",
        lambda: [
            r
            for r in run(driver, "CALL mg.get_module_files() YIELD path, is_editable RETURN path, is_editable")
            if "pg_" in r["path"] or r["is_editable"]
        ][:8],
    )
    for name in ("pg_trial_maths.py", "pg_trial_main.py", "pg_trial_broken.py"):
        for row in run(driver, "CALL mg.get_module_files() YIELD path RETURN path"):
            if row["path"].endswith("/" + name):
                attempt(f"delete the old {name}", lambda p=row["path"]: run(driver, "CALL mg.delete_module_file($p)", p=p))
    attempt(
        "create the maths module",
        lambda: run(driver, "CALL mg.create_module_file('pg_trial_maths.py', $c) YIELD path RETURN path", c=maths),
    )
    attempt(
        "create the module that imports it",
        lambda: run(driver, "CALL mg.create_module_file('pg_trial_main.py', $c) YIELD path RETURN path", c=main),
    )
    attempt("call it at once", lambda: run(driver, "CALL pg_trial_main.twice(21) YIELD result RETURN result"))
    attempt("mg.load, then call", lambda: (run(driver, "CALL mg.load('pg_trial_main')"), run(driver, "CALL pg_trial_main.twice(21) YIELD result RETURN result")))

    def read_back():
        path = next(
            r["path"]
            for r in run(driver, "CALL mg.get_module_files() YIELD path RETURN path")
            if r["path"].endswith("/pg_trial_main.py")
        )
        return run(driver, "CALL mg.get_module_file($p) YIELD content RETURN content", p=path)[0]["content"] == main

    attempt("its text read back is the text written", read_back)

    def update_maths():
        path = next(
            r["path"]
            for r in run(driver, "CALL mg.get_module_files() YIELD path RETURN path")
            if r["path"].endswith("/pg_trial_maths.py")
        )
        run(driver, "CALL mg.update_module_file($p, $c)", p=path, c="def double(x):\n    return 3 * x\n")
        first = run(driver, "CALL pg_trial_main.twice(21) YIELD result RETURN result")
        run(driver, "CALL mg.load('pg_trial_main')")
        second = run(driver, "CALL pg_trial_main.twice(21) YIELD result RETURN result")
        run(driver, "CALL mg.load_all()")
        third = run(driver, "CALL pg_trial_main.twice(21) YIELD result RETURN result")
        return {"after update": first, "after mg.load(main)": second, "after mg.load_all": third}

    attempt("the imported module changed: when the importer sees it", update_maths)
    attempt(
        "a module whose import fails: create",
        lambda: run(driver, "CALL mg.create_module_file('pg_trial_broken.py', $c) YIELD path RETURN path", c=broken),
    )
    attempt("a module whose import fails: mg.load", lambda: run(driver, "CALL mg.load('pg_trial_broken')"))
    attempt("a module whose import fails: call", lambda: run(driver, "CALL pg_trial_broken.x() YIELD y RETURN y"))
    attempt(
        "numpy and scipy in the database's Python",
        lambda: (
            run(
                driver,
                "CALL mg.create_module_file('pg_trial_numpy.py', $c) YIELD path RETURN path",
                c="import mgp\nimport numpy, scipy\n\n@mgp.read_proc\ndef versions(ctx: mgp.ProcCtx) -> mgp.Record(numpy=str, scipy=str):\n"
                "    return mgp.Record(numpy=numpy.__version__, scipy=scipy.__version__)\n",
            ),
            run(driver, "CALL pg_trial_numpy.versions() YIELD numpy, scipy RETURN numpy, scipy"),
        ),
    )
    for row in run(driver, "CALL mg.get_module_files() YIELD path RETURN path"):
        if "/pg_trial_" in row["path"]:
            run(driver, "CALL mg.delete_module_file($p)", p=row["path"])
    driver.close()


def neo4j_trial():
    driver = neo4j.GraphDatabase.driver(NEO4J[0], auth=NEO4J[1])
    for _ in range(60):
        try:
            driver.verify_connectivity()
            break
        except Exception:
            time.sleep(2)
    print("\n\n=== Neo4j", run(driver, "CALL dbms.components() YIELD versions, edition RETURN versions, edition"))
    run(driver, "MATCH (n:TrialVector) DETACH DELETE n")
    attempt("drop (none there)", lambda: run(driver, "DROP INDEX trial_vectors IF EXISTS"))
    create = (
        "CREATE VECTOR INDEX trial_vectors IF NOT EXISTS FOR (n:TrialVector) ON (n.vector) "
        "OPTIONS {indexConfig: {`vector.dimensions`: 4, `vector.similarity_function`: 'cosine'}}"
    )
    attempt("create", lambda: run(driver, create))
    attempt("create again", lambda: run(driver, create))
    attempt("await", lambda: run(driver, "CALL db.awaitIndexes(60)"))
    attempt(
        "SHOW INDEXES",
        lambda: run(
            driver,
            "SHOW INDEXES YIELD name, type, entityType, labelsOrTypes, properties, options, state "
            "WHERE type = 'VECTOR' RETURN *",
        ),
    )
    run(
        driver,
        "UNWIND range(0, 9) AS i CREATE (:TrialVector {of: i, vector: $vectors[i]})",
        vectors=vectors(10),
    )
    attempt(
        "db.index.vector.queryNodes, nearest 3 to the first",
        lambda: run(
            driver,
            "CALL db.index.vector.queryNodes('trial_vectors', 3, $v) YIELD node, score RETURN node.of AS of, score",
            v=[1.0, 0.0, 0.0, 0.0],
        ),
    )
    attempt(
        "the SEARCH clause",
        lambda: run(
            driver,
            "MATCH (node:TrialVector) SEARCH node IN (VECTOR INDEX trial_vectors FOR $v LIMIT 3) SCORE AS score "
            "RETURN node.of AS of, score",
            v=[1.0, 0.0, 0.0, 0.0],
        ),
    )

    def deleted_in_one():
        with driver.session() as session:
            with session.begin_transaction() as tx:
                tx.run("MATCH (n:TrialVector {of: 1}) DETACH DELETE n").consume()
                rows = [
                    r.data()
                    for r in tx.run(
                        "CALL db.index.vector.queryNodes('trial_vectors', 3, $v) YIELD node, score "
                        "RETURN node.of AS of, score",
                        v=[1.0, 0.0, 0.0, 0.0],
                    )
                ]
                tx.commit()
                return rows

    attempt(
        "a node deleted, then searched in another transaction",
        lambda: (
            run(driver, "MATCH (n:TrialVector {of: 0}) DETACH DELETE n"),
            run(
                driver,
                "CALL db.index.vector.queryNodes('trial_vectors', 3, $v) YIELD node, score RETURN node.of AS of, score",
                v=[1.0, 0.0, 0.0, 0.0],
            ),
        ),
    )
    attempt("a node deleted and searched in one transaction", deleted_in_one)
    attempt(
        "a vector of the wrong dimension",
        lambda: run(driver, "CREATE (:TrialVector {of: 999, vector: [1.0, 2.0]})"),
    )
    attempt(
        "set in place, then searched at once (the index is eventually consistent)",
        lambda: (
            run(driver, "MATCH (n:TrialVector {of: 5}) SET n.vector = [0.0, 0.0, 0.0, 1.0]"),
            run(
                driver,
                "CALL db.index.vector.queryNodes('trial_vectors', 1, $v) YIELD node, score RETURN node.of AS of, score",
                v=[0.0, 0.0, 0.0, 1.0],
            ),
        ),
    )
    attempt("drop", lambda: run(driver, "DROP INDEX trial_vectors"))
    attempt("drop again", lambda: run(driver, "DROP INDEX trial_vectors"))
    run(driver, "MATCH (n:TrialVector) DETACH DELETE n")
    driver.close()


for trial in (memgraph,) if "--memgraph" in __import__("sys").argv else (memgraph, neo4j_trial):
    try:
        trial()
    except Exception:
        traceback.print_exc()
