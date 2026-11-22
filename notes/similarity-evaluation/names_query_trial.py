"""Step 8.3: the query that reads the names for a rebuild of the name part, tried at size with its plan (the class
part's page query with the classes that have names and their fields), and the names of some ids for a refresh.

    uv run python notes/similarity-evaluation/names_query_trial.py memgraph bolt://localhost:7706
    uv run python notes/similarity-evaluation/names_query_trial.py neo4j bolt://localhost:7707
"""

import sys
import time

import neo4j

BACKEND, URL = sys.argv[1], sys.argv[2]
AUTH = {"memgraph": ("test", "test"), "neo4j": ("neo4j", "test-password")}[BACKEND]
TYPES = ["Person", "Group", "Place"]
FIELDS = ["label"]
# (the head of a nested node, as `fragments.head_of` finds it; deleted and merged as `fragments` say them)
PAGE = """
MATCH (n:PGIndexableNode) WHERE n.id > $after AND n.type IN $types
WITH n ORDER BY n.id LIMIT $limit
OPTIONAL MATCH (h:HeadNode {id: n.head_node_id})
RETURN collect([n.id, n.type, [f IN $fields | n[f]],
    (n.head_node_id IS NULL OR h IS NOT NULL) AND NOT coalesce(coalesce(h, n).deleted, false)
    AND n.merged_into IS NULL]) AS rows
"""
ITEMS = """
UNWIND $ids AS id MATCH (n:PGIndexableNode {id: id}) WHERE n.type IN $types
OPTIONAL MATCH (h:HeadNode {id: n.head_node_id})
WITH n, h WHERE (n.head_node_id IS NULL OR h IS NOT NULL) AND NOT coalesce(coalesce(h, n).deleted, false)
    AND n.merged_into IS NULL
RETURN n.id AS id, n.type AS type, [f IN $fields | n[f]] AS names
"""

with neo4j.GraphDatabase.driver(URL, auth=AUTH) as driver, driver.session() as session:
    began = time.perf_counter()
    after, count, pages, slowest = "", 0, 0, 0.0
    ids = []
    while True:
        at = time.perf_counter()
        rows = session.run(PAGE, after=after, types=TYPES, fields=FIELDS, limit=10_000).single()["rows"]
        slowest = max(slowest, time.perf_counter() - at)
        pages += 1
        count += len(rows)
        ids += [row[0] for row in rows[:20]]
        if len(rows) < 10_000:
            break
        after = max(row[0] for row in rows)
    print(f"{BACKEND}: {count:,} names read in {pages} pages, {time.perf_counter() - began:.1f} s "
          f"(the slowest page {slowest:.2f} s); the last row {rows[-1]}")
    at = time.perf_counter()
    found = session.run(ITEMS, ids=ids, types=TYPES, fields=FIELDS).data()
    print(f"the names of {len(ids)} ids: {len(found)} rows in {(time.perf_counter() - at) * 1000:.0f} ms")
    for name, query, params in (
        ("page", PAGE, {"after": "8", "types": TYPES, "fields": FIELDS, "limit": 10_000}),
        ("items", ITEMS, {"ids": ids[:5], "types": TYPES, "fields": FIELDS}),
    ):
        if BACKEND == "memgraph":
            plan = [r["QUERY PLAN"] for r in session.run("EXPLAIN " + query, **params).data()]
            print(f"plan of {name}:", " / ".join(line.strip() for line in plan))
        else:
            summary = session.run("EXPLAIN " + query, **params).consume()

            def said(plan, depth=0):
                yield "  " * depth + plan["operatorType"] + " " + str(plan["args"].get("Details", ""))[:110]
                for child in plan.get("children", []):
                    yield from said(child, depth + 1)

            print(f"plan of {name}:\n" + "\n".join(said(summary.plan)))
