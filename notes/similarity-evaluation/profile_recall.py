"""Step 2.4's question (implementation_docs/similarity-build-plan.md): one vector index over whole vectors, searched
with a query whose parts a profile has rescaled or zeroed; does the index still find the nearest?

Each item's stored vector is its parts end to end, each of length one. Then the cosine of a query (its parts scaled
by the profile's weights) with a stored vector is, up to a constant, the weighted sum of the cosines of the parts: so
an exact search ranks rightly. What is measured is the index, which is approximate (HNSW), on queries unlike what it
holds.

Made-up data: a "graph" part of 128 dimensions in clusters, and a "class" part as the class part of step 2.3 makes
it (a class is itself 1, its parent `decay`, and so on, on a tree of classes).

    uv run --with numpy python notes/similarity-evaluation/profile_recall.py memgraph bolt://localhost:7702 test test
    uv run --with numpy python notes/similarity-evaluation/profile_recall.py neo4j bolt://localhost:7703 neo4j test-password

It makes nodes of the label `PGRecall` and an index `pg_recall`, and removes both. A scratch database only.
"""

import os
import sys
import time

import neo4j
import numpy as np

KIND, URI, USER, PASSWORD = sys.argv[1:5]
N = int(sys.argv[5]) if len(sys.argv) > 5 else 100_000
if URI.endswith((":7687", ":7688")):
    sys.exit("Not the tests' database nor the demo's: a scratch one")

GRAPH_D, CLUSTERS, QUERIES, K = 128, 2000, 200, 10
OVERFETCH = (1, 4, 10)
PROFILES = {
    "graph 1, class 0.1": (1.0, 0.1),
    "graph 1, class 1": (1.0, 1.0),
    "graph only": (1.0, 0.0),
    "class only": (0.0, 1.0),
    "graph 0.1, class 1": (0.1, 1.0),
}
rng = np.random.default_rng(7)


def unit(a):
    return a / np.linalg.norm(a, axis=-1, keepdims=True)


def class_vectors(decay=0.5):
    """A tree: 3 roots, 4 children each, 4 under each of those (63 classes); items are of the 48 leaves and the 12
    in the middle"""
    parent = {}
    names = []
    for r in range(3):
        names.append((r,))
        for c in range(4):
            names.append((r, c))
            parent[(r, c)] = (r,)
            for g in range(4):
                names.append((r, c, g))
                parent[(r, c, g)] = (r, c)
    index = {name: i for i, name in enumerate(names)}
    vectors = np.zeros((len(names), len(names)))
    for name in names:
        at, weight = name, 1.0
        while at is not None:
            vectors[index[name], index[at]] = weight
            at, weight = parent.get(at), weight * decay
    usable = [index[n] for n in names if len(n) > 1]
    return unit(vectors), usable


def data():
    centres = rng.normal(size=(CLUSTERS, GRAPH_D))
    graph = unit(centres[rng.integers(0, CLUSTERS, N)] + 0.6 * rng.normal(size=(N, GRAPH_D)))
    classes, usable = class_vectors()
    # (a few classes hold most items, as people and statements do)
    weights = rng.dirichlet(np.full(len(usable), 0.3))
    of_class = rng.choice(usable, size=N, p=weights)
    return graph, classes[of_class]


def main():
    graph, klass = data()
    whole = np.hstack([graph, klass]).astype(np.float32)
    dimension = whole.shape[1]
    driver = neo4j.GraphDatabase.driver(URI, auth=(USER, PASSWORD))

    def run(cypher, **params):
        with driver.session() as session:
            return [r.data() for r in session.run(cypher, **params)]

    def clean():
        run("DROP VECTOR INDEX pg_recall" if KIND == "memgraph" else "DROP INDEX pg_recall IF EXISTS")
        while run("MATCH (n:PGRecall) WITH n LIMIT 20000 DETACH DELETE n RETURN count(*) AS c")[0]["c"]:
            pass

    if os.environ.get("ONLY") == "profile":  # (the third way alone)
        by_profile(run, graph, klass, rng.choice(N, QUERIES, replace=False))
        return
    clean()
    if KIND == "memgraph":
        run(
            'CREATE VECTOR INDEX pg_recall ON :PGRecall(v) WITH CONFIG {"dimension": %d, "capacity": %d, '
            '"metric": "cos"}' % (dimension, N)
        )
        search = (
            "CALL vector_search.search('pg_recall', $k, $v) YIELD node, distance "
            "RETURN node.i AS i, 1 - distance AS score"
        )
    else:
        run(
            "CREATE VECTOR INDEX pg_recall IF NOT EXISTS FOR (n:PGRecall) ON (n.v) OPTIONS {indexConfig: "
            "{`vector.dimensions`: %d, `vector.similarity_function`: 'cosine'}}" % dimension
        )
        search = (
            "CALL db.index.vector.queryNodes('pg_recall', $k, $v) YIELD node, score "
            "RETURN node.i AS i, 2 * score - 1 AS score"
        )
    started = time.perf_counter()
    for at in range(0, N, 5000):
        rows = [{"i": i, "v": whole[i].tolist()} for i in range(at, min(at + 5000, N))]
        run("UNWIND $rows AS row CREATE (:PGRecall {i: row.i, v: row.v})", rows=rows)
    if KIND == "neo4j":
        run("CALL db.awaitIndexes(600)")
    print(f"{KIND}: {N} vectors of {dimension} written and indexed in {time.perf_counter() - started:.0f} s")

    queries = rng.choice(N, QUERIES, replace=False)
    print(f"\nrecall of the {K} nearest (a hit is any item as near as the {K}th true one), {QUERIES} queries")
    print(f"{'profile':22}" + "".join(f"  k x {o:<3} ms    " for o in OVERFETCH))
    for name, (wg, wc) in PROFILES.items():
        line = f"{name:22}"
        for over in OVERFETCH:
            hits, took = 0, 0.0
            for q in queries:
                query = np.hstack([wg * graph[q], wc * klass[q]])
                true = wg * (graph @ graph[q]) + wc * (klass @ klass[q])
                true[q] = -np.inf
                kth = np.partition(true, -K)[-K]
                began = time.perf_counter()
                found = run(search, k=K * over + 1, v=query.tolist())
                took += time.perf_counter() - began
                best = sorted((true[r["i"]] for r in found if r["i"] != q), reverse=True)[:K]
                hits += sum(1 for score in best if score >= kth - 1e-6)
            line += f"  {hits / (K * QUERIES):.3f} {1000 * took / QUERIES:5.1f}    "
        print(line)
    clean()
    by_part(run, graph, klass, queries)
    by_profile(run, graph, klass, queries)
    driver.close()


def by_profile(run, graph, klass, queries):
    """A third way: an index for each profile, of vectors whose parts are already scaled by the profile's weights.
    The query is then of the same making as what the index holds. (On Neo4j also with quantization off)"""

    # (a label and a name for each profile: on Memgraph 3.14 an index dropped and made again under the same name
    # with another dimension kept the old dimension, seen 2026-11-21)
    def clean(p="p"):
        run(f"DROP VECTOR INDEX pg_recall_{p}" if KIND == "memgraph" else f"DROP INDEX pg_recall_{p} IF EXISTS")
        while run(f"MATCH (n:PGRecall_{p}) WITH n LIMIT 20000 DETACH DELETE n RETURN count(*) AS c")[0]["c"]:
            pass

    ways = [("", "")] if KIND == "memgraph" else [("", ""), (" (no quantization)", ", `vector.quantization.enabled`: false")]
    for said, option in ways:
        print(f"\nan index for each profile, vectors scaled before they are stored{said}: recall of the {K} nearest")
        print(f"{'profile':22}" + "".join(f"  k x {o:<3} ms    " for o in OVERFETCH))
        for number, (name, (wg, wc)) in enumerate(PROFILES.items()):
            p = f"p{number}"
            scaled = np.hstack([wg * graph, wc * klass]).astype(np.float32)
            scaled = scaled[:, np.abs(scaled).sum(axis=0) > 0]
            d = scaled.shape[1]
            clean(p)
            if KIND == "memgraph":
                run(
                    'CREATE VECTOR INDEX pg_recall_%s ON :PGRecall_%s(v) WITH CONFIG {"dimension": %d, "capacity": %d, '
                    '"metric": "cos"}' % (p, p, d, N)
                )
                call = "CALL vector_search.search('pg_recall_%s', $k, $v) YIELD node RETURN node.i AS i" % p
            else:
                run(
                    "CREATE VECTOR INDEX pg_recall_%s IF NOT EXISTS FOR (n:PGRecall_%s) ON (n.v) OPTIONS {indexConfig: "
                    "{`vector.dimensions`: %d, `vector.similarity_function`: 'cosine'%s}}" % (p, p, d, option)
                )
                call = "CALL db.index.vector.queryNodes('pg_recall_%s', $k, $v) YIELD node RETURN node.i AS i" % p
            for at in range(0, N, 5000):
                rows = [{"i": i, "v": scaled[i].tolist()} for i in range(at, min(at + 5000, N))]
                run("UNWIND $rows AS row CREATE (:PGRecall_" + p + " {i: row.i, v: row.v})", rows=rows)
            if KIND == "neo4j":
                run("CALL db.awaitIndexes(600)")
            line = f"{name:22}"
            for over in OVERFETCH:
                hits, took = 0, 0.0
                for q in queries:
                    true = wg * (graph @ graph[q]) + wc * (klass @ klass[q])
                    true[q] = -np.inf
                    kth = np.partition(true, -K)[-K]
                    began = time.perf_counter()
                    found = {r["i"] for r in run(call, k=K * over + 1, v=scaled[q].tolist())}
                    took += time.perf_counter() - began
                    best = sorted((true[i] for i in found if i != q), reverse=True)[:K]
                    hits += sum(1 for score in best if score >= kth - 1e-6)
                line += f"  {hits / (K * QUERIES):.3f} {1000 * took / QUERIES:5.1f}    "
            print(line)
            clean(p)


def by_part(run, graph, klass, queries):
    """The other way: an index for each part, each asked for k x overfetch with its own part of the query, the
    candidates of all of them scored exactly (the weighted sum of the cosines of the parts)"""
    parts = {"g": graph.astype(np.float32), "c": klass.astype(np.float32)}

    def clean():
        for name in parts:
            run(f"DROP VECTOR INDEX pg_recall_{name}" if KIND == "memgraph" else f"DROP INDEX pg_recall_{name} IF EXISTS")
            while run(f"MATCH (n:PGRecall_{name}) WITH n LIMIT 20000 DETACH DELETE n RETURN count(*) AS c")[0]["c"]:
                pass

    clean()
    for name, vectors in parts.items():
        d = vectors.shape[1]
        if KIND == "memgraph":
            run(
                'CREATE VECTOR INDEX pg_recall_%s ON :PGRecall_%s(v) WITH CONFIG {"dimension": %d, "capacity": %d, '
                '"metric": "cos"}' % (name, name, d, N)
            )
        else:
            run(
                "CREATE VECTOR INDEX pg_recall_%s IF NOT EXISTS FOR (n:PGRecall_%s) ON (n.v) OPTIONS {indexConfig: "
                "{`vector.dimensions`: %d, `vector.similarity_function`: 'cosine'}}" % (name, name, d)
            )
        for at in range(0, N, 5000):
            rows = [{"i": i, "v": vectors[i].tolist()} for i in range(at, min(at + 5000, N))]
            run(f"UNWIND $rows AS row CREATE (:PGRecall_{name} {{i: row.i, v: row.v}})", rows=rows)
    if KIND == "neo4j":
        run("CALL db.awaitIndexes(600)")
    call = (
        "CALL vector_search.search('pg_recall_%s', $k, $v) YIELD node RETURN node.i AS i"
        if KIND == "memgraph"
        else "CALL db.index.vector.queryNodes('pg_recall_%s', $k, $v) YIELD node RETURN node.i AS i"
    )
    print(f"\nan index for each part, merged: recall of the {K} nearest")
    print(f"{'profile':22}" + "".join(f"  k x {o:<3} ms    " for o in OVERFETCH))
    for name, (wg, wc) in PROFILES.items():
        line = f"{name:22}"
        for over in OVERFETCH:
            hits, took = 0, 0.0
            for q in queries:
                true = wg * (graph @ graph[q]) + wc * (klass @ klass[q])
                true[q] = -np.inf
                kth = np.partition(true, -K)[-K]
                began = time.perf_counter()
                found = set()
                for part, weight in (("g", wg), ("c", wc)):
                    if weight:
                        found |= {r["i"] for r in run(call % part, k=K * over + 1, v=parts[part][q].tolist())}
                took += time.perf_counter() - began
                best = sorted((true[i] for i in found if i != q), reverse=True)[:K]
                hits += sum(1 for score in best if score >= kth - 1e-6)
            line += f"  {hits / (K * QUERIES):.3f} {1000 * took / QUERIES:5.1f}    "
        print(line)
    clean()


main()
