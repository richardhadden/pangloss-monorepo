import neo4j
d = neo4j.GraphDatabase.driver("bolt://localhost:7702", auth=("test", "test"))
def run(q, **p):
    with d.session() as s: return [r.data() for r in s.run(q, **p)]
def plan(q, **p):
    return [list(r.values())[0] for r in run("EXPLAIN " + q, **p)]
print([ (r.get("index type"), r.get("label"), r.get("property")) for r in run("SHOW INDEX INFO") if r.get("label") in ("PGCitation","PGIndexableNode","HeadNode","PGUnprotectedCitation")])
print(run("MATCH (c) WHERE c.target_id IS NOT NULL RETURN labels(c) AS l, c.type AS t, c.head_node_id AS h, c.target_id AS tid LIMIT 3"))
print(run("MATCH (h:HeadNode) RETURN h.type AS t, h.head_node_id AS hn, h.published AS p, h.deleted AS d LIMIT 3"))
print(run("MATCH (n:PGIndexableNode) WHERE NOT n:HeadNode RETURN n.type AS t, n.head_node_id IS NOT NULL AS has, n.published AS p LIMIT 3"))
print(run("MATCH ()-[e]->() RETURN DISTINCT e.reverse AS r, e.derived AS d, e.computed AS c, count(*) AS n"))
ids = [r["id"] for r in run("MATCH (n:PGIndexableNode) RETURN n.id AS id LIMIT 40")]
NODES = """UNWIND $ids AS id MATCH (n:PGIndexableNode {id: id}) OPTIONAL MATCH (h:HeadNode {id: n.head_node_id})
RETURN n.id AS id, n.type AS type, coalesce(h.deleted, n.deleted, false) AS deleted, n.merged_into AS merged_into,
coalesce(h.published, n.published, true) AS published, n.target_id AS cites"""
OUT = """UNWIND $ids AS id MATCH (n:PGIndexableNode {id: id})-[e]->(m:PGIndexableNode)
WHERE NOT coalesce(e.reverse, false) AND NOT coalesce(e.derived, false)
RETURN n.id AS source, m.id AS target, type(e) AS field, properties(e) AS properties"""
IN = """UNWIND $ids AS id MATCH (m:PGIndexableNode {id: id})<-[e]-(n:PGIndexableNode)
WHERE NOT coalesce(e.reverse, false) AND NOT coalesce(e.derived, false)
RETURN n.id AS source, m.id AS target, type(e) AS field, properties(e) AS properties"""
CITING = "UNWIND $ids AS id MATCH (c:PGCitation {target_id: id}) RETURN c.id AS id"
PAGE = """MATCH (n:PGIndexableNode) WHERE n.id > $after WITH n ORDER BY n.id LIMIT $page
RETURN n.id AS id, n.type AS type, n.head_node_id AS head, coalesce(n.deleted, false) AS deleted, n.merged_into AS merged_into, n.published AS published, n.target_id AS cites"""
for name, q, p in (("nodes", NODES, {"ids": ids}), ("out", OUT, {"ids": ids}), ("in", IN, {"ids": ids}), ("citing", CITING, {"ids": ids}), ("page", PAGE, {"after": "", "page": 10})):
    rows = run(q, **p)
    print("==", name, len(rows), "rows;", rows[:1])
    print("  ", " | ".join(x.strip() for x in plan(q, **p)))
