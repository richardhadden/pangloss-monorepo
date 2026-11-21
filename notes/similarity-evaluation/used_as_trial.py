"""Step 7a.5: three forms of "something refers to this item by one of these relations", on :7690 (reads only).
Result 2026-11-21, 3,000 people, Memgraph 3.14: EXISTS 22 ms, EXISTS with the head of the referrer 18 ms, CALL ... LIMIT 1 19 ms; 93 of 3,000 used. All fine."""
import asyncio, time
from neo4j import AsyncGraphDatabase
async def main():
    d = AsyncGraphDatabase.driver("bolt://localhost:7690", auth=("test","test"))
    async with d.session() as s:
        r = await s.run("MATCH (p:Person:HeadNode)<-[r]-(m) WHERE NOT coalesce(r.reverse,false) RETURN type(r) AS t, count(*) AS n ORDER BY n DESC LIMIT 8"); print(await r.values())
        r = await s.run("MATCH (p:Person:HeadNode) WITH p LIMIT 3000 RETURN collect(p.id) AS ids"); ids=(await r.single())["ids"]
        base = "UNWIND $ids AS id MATCH (item:PGIndexableNode {id: id}) "
        forms = {
         "EXISTS": base+"WHERE EXISTS { MATCH (item)<-[r]-(m:PGIndexableNode) WHERE type(r) IN $names AND NOT coalesce(r.reverse,false) AND NOT coalesce(r.derived,false) } RETURN count(item) AS n",
         "exists+head": base+"""WHERE EXISTS { MATCH (item)<-[r]-(m:PGIndexableNode) WHERE type(r) IN $names AND NOT coalesce(r.reverse,false) AND NOT coalesce(r.derived,false)
              OPTIONAL MATCH (h:HeadNode {id: m.head_node_id}) WITH m, h WHERE NOT coalesce(coalesce(h, m).deleted, false) RETURN 1 } RETURN count(item) AS n""",
         "CALL limit 1": base+"""CALL { WITH item MATCH (item)<-[r]-(m:PGIndexableNode) WHERE type(r) IN $names AND NOT coalesce(r.reverse,false) AND NOT coalesce(r.derived,false)
              OPTIONAL MATCH (h:HeadNode {id: m.head_node_id}) WITH m, h WHERE NOT coalesce(coalesce(h, m).deleted, false) RETURN 1 AS used LIMIT 1 } RETURN count(item) AS n""",
        }
        for name,q in forms.items():
            for names in (["child"],["nothing_of_the_kind"]):
                try:
                    t=time.perf_counter(); r=await s.run(q, ids=ids, names=names); n=(await r.single())["n"]
                    print(f"{name:14} {names} -> {n} of {len(ids)} in {(time.perf_counter()-t)*1000:.0f} ms")
                except Exception as e: print(name, str(e)[:200])
    await d.close()
asyncio.run(main())
