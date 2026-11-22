"""Step 9.3: the queries that read the dates for the time part, tried with their plans: a page of every date for a
rebuild (keyset on `PGIndexableNode(id)`, as the name part's), and the dates under some heads for a refresh (by
the index of `PGIndexableNode(head_node_id)`). Each date with what holds it and its head.

    uv run python notes/similarity-evaluation/dates_query_trial.py memgraph bolt://localhost:7706
    uv run python notes/similarity-evaluation/dates_query_trial.py neo4j bolt://localhost:7707
"""

import sys
import time

import neo4j

BACKEND, URL = sys.argv[1], sys.argv[2]
AUTH = {"memgraph": ("test", "test"), "neo4j": ("neo4j", "test-password")}[BACKEND]
# (what holds a date is at the end of its one reverse edge; a date held by a date is a part of it, an end of a range
# or a period, and not a date of anything. `kept`: the head is there and not deleted)
ROW = """[d.id, d.earliest_fuzzy, d.earliest_strict, d.latest_strict, d.latest_fuzzy, d.precision,
    n.id, n.type, n:Date, n:Document OR n:Entity, coalesce(h.id, n.id), coalesce(h.type, n.type),
    (d.head_node_id IS NULL OR h IS NOT NULL) AND NOT coalesce(coalesce(h, n).deleted, false)
    AND n.merged_into IS NULL]"""
PAGE = f"""
MATCH (d:PGIndexableNode) WHERE d.id > $after AND d:Date
WITH d ORDER BY d.id LIMIT $limit
OPTIONAL MATCH (d)-[r]->(n) WHERE r.reverse = true
OPTIONAL MATCH (h:HeadNode {{id: d.head_node_id}})
RETURN collect({ROW}) AS rows
"""
BELOW = f"""
UNWIND $ids AS id
MATCH (d:PGIndexableNode {{head_node_id: id}}) WHERE d:Date
OPTIONAL MATCH (d)-[r]->(n) WHERE r.reverse = true
OPTIONAL MATCH (h:HeadNode {{id: d.head_node_id}})
RETURN collect({ROW}) AS rows
"""

with neo4j.GraphDatabase.driver(URL, auth=AUTH) as driver, driver.session() as session:
    began = time.perf_counter()
    after, count, pages, slowest, top, items, kept = "", 0, 0, 0.0, 0, 0, 0
    heads: list[str] = []
    while True:
        at = time.perf_counter()
        rows = session.run(PAGE, after=after, limit=10_000).single()["rows"]
        slowest = max(slowest, time.perf_counter() - at)
        pages += 1
        count += len(rows)
        top += sum(1 for row in rows if not row[8])
        items += sum(1 for row in rows if not row[8] and row[9])
        kept += sum(1 for row in rows if row[12])
        heads += [row[10] for row in rows[:10]]
        if len(rows) < 10_000:
            break
        after = max(row[0] for row in rows)
    print(f"{BACKEND}: {count:,} dates read in {pages} pages, {time.perf_counter() - began:.1f} s (the slowest page "
          f"{slowest:.2f} s); {top:,} not held by a date, {items:,} of them by a document or an entity; {kept:,} "
          f"with a head that is there; a row {rows[-1]}")
    for size in (1, 50, len(heads)):
        at = time.perf_counter()
        found = session.run(BELOW, ids=heads[:size]).single()["rows"]
        print(f"the dates under {min(size, len(heads))} heads: {len(found)} in "
              f"{(time.perf_counter() - at) * 1000:.0f} ms")
    for name, query, params in (
        ("page", PAGE, {"after": "8", "limit": 10_000}),
        ("below", BELOW, {"ids": heads[:5]}),
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
