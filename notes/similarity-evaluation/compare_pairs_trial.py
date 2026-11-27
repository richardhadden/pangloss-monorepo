"""Scratch: the pairs-by-rule query tried at size."""
import asyncio, sys, time, types, typing, statistics, random
from pathlib import Path
HERE = Path("/Users/rhadden/Development/pangloss-monorepo/notes/similarity-evaluation")
def planted_script():
    source = (HERE / "planted.py").read_text(encoding="utf-8").replace("\nmain()\n", "\n")
    module = types.ModuleType("planted_script"); module.__file__ = str(HERE / "planted.py")
    exec(compile(source, "planted.py", "exec"), module.__dict__)
    module.COMPARED = module.DATED = True
    return module

FIELDS = {  # class -> root field -> (edges across related classes, target labels)
    "Activity": {"carried_out_by": (["carried_out_by"], ["Person", "Group"]), "participants": (["participants"], ["Person", "Group"])},
    "Transfer": {"given_by": (["given_by"], ["Person", "Group"]), "given_to": (["given_to"], ["Person", "Group"])},
    "Attendance": {"attended_by": (["attended_by"], ["Person"]), "assembly_of": (["assembly_of"], ["Group"])},
    "Birth": {"person": (["person"], ["Person"])},
    "Making": {"made_by": (["made_by"], ["Person", "Group"]), "made": (["made", "picture_made"], ["Thing", "Picture"])},
}
RELATED = {"Activity": ["Activity"], "Transfer": ["Transfer"], "Attendance": ["Attendance"], "Birth": ["Birth"], "Making": ["Making", "MakingOfPicture"]}

async def main(backend, url, shape):
    script = planted_script()
    storage = await script.connected(backend, url, ["pangloss_derived", "pangloss_library", "pangloss_criteria"])
    from pangloss_core import backend as be
    current = be.current(); database = current.database(); fr = current.fragments; d = current.dialect
    def own(kind):
        return f"""
        MATCH (s:PGIndexableNode {{id: $id}})
        MATCH (s)-[e]->(x){d.from_wrappers("a")}(v:Entity)
        WHERE type(e) IN $edges AND NOT coalesce(e.reverse, false)
        RETURN DISTINCT type(e) AS field, v.id AS entity, labels(v) AS labels
        """
    def others(kind):
        labels = " OR ".join(f"t:{name}" for name in RELATED[kind])
        from pangloss_cypher.search_query import wrapper
        head = fr.head_of("t", "t_head")
        tail = f"""
            WITH DISTINCT root, entity, t
            WHERE t.id <> $id
            {head.match}
            WITH root, entity, t, {head.name}
            WHERE {fr.visible("t", head)}
            RETURN root, entity, t.id AS id"""
        return f"""
        UNWIND $found AS f
        WITH f, f.entity AS vid
        MATCH (v:PGIndexableNode {{id: vid}})<-[e]-(t)
        WHERE type(e) IN f.edges AND NOT coalesce(e.reverse, false)
        WITH f.root AS root, f.entity AS entity, t
        WHERE ({labels})
        {tail}
        UNION
        UNWIND $found AS f
        WITH f, f.entity AS vid
        MATCH (v:PGIndexableNode {{id: vid}})<-[e3]-(y)
        WHERE type(e3) IN $held AND NOT coalesce(e3.reverse, false) AND {wrapper("y")}
        MATCH (y){d.through_wrappers("b", backwards=True)}(w)
        MATCH (w)<-[e2]-(t)
        WHERE type(e2) IN f.edges AND NOT coalesce(e2.reverse, false)
        WITH f.root AS root, f.entity AS entity, t
        WHERE ({labels})
        {tail}
        """
    @database.read_transaction
    async def run(tx, query, **params):
        result = await tx.run(query, **params)
        return [dict(r) async for r in result]
    for kind in FIELDS:
        ids = [r["id"] for r in await run(f"MATCH (s:{kind}) RETURN s.id AS id LIMIT 3000")]
        random.Random(1).shuffle(ids)
        times, counts = [], []
        edges = [e for es, _ in FIELDS[kind].values() for e in es]
        for id in ids[:60]:
            began = time.perf_counter()
            mine = await run(own(kind), id=id, edges=edges)
            found = []
            for r in mine:
                for root, (es, targets) in FIELDS[kind].items():
                    if r["field"] in es and set(r["labels"]) & set(targets):
                        found.append({"root": root, "entity": r["entity"], "edges": es})
            rows = await run(others(kind), id=id, found=found, see_unpublished=False, held=["target", "contents", "alternatives"])
            times.append((time.perf_counter() - began) * 1000); counts.append(len({r["id"] for r in rows}))
        print(f"{backend} {shape} {kind:11} entities {len(found)} (last); others median {statistics.median(counts):.0f} most {max(counts)}; ms median {statistics.median(times):.1f} p90 {sorted(times)[53]:.1f} most {max(times):.1f}")
    if len(sys.argv) > 4:
        q = others("Activity")
        for part in q.split("UNION"):
            began = time.perf_counter()
            rows = await run(part, id=id, found=found[:0] or [{"root": "participants", "entity": mine[0]["entity"], "edges": ["participants", "carried_out_by"]}], see_unpublished=False, held=["target", "contents", "alternatives"])
            print(len(rows), (time.perf_counter() - began) * 1000)
            for r in await run("EXPLAIN " + part, id=id, found=[], see_unpublished=False, held=["target"]): print("   ", list(r.values())[0])
    await storage.setup.disconnect()

asyncio.run(main(sys.argv[1], sys.argv[2], sys.argv[3]))
