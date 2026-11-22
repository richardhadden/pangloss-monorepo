"""Step 9.3 at size: what each part's refresh costs in one turn of the worker, after a gathering of the dated
planted world is told again and after a small factoid of two new people (it writes them).

    uv run python notes/similarity-evaluation/worker_turn_parts.py bolt://localhost:7706
"""

import asyncio, sys, time, runpy, types
URL = sys.argv[1]; sys.argv = ["planted.py"]
src = open("notes/similarity-evaluation/planted.py").read().replace("\nmain()\n", "\n")
mod = types.ModuleType("planted_script"); exec(compile(src, "planted.py", "exec"), mod.__dict__)
mod.DATED = True
async def go(url, backend):
    storage = await mod.connected(backend, url, mod.BASE_APPS + mod.installed(mod.VECTOR_APPS), {"VECTORS_PROFILES": {"when": {"graph": 1, "class": 0.1, "time": 0.5}}})
    from pangloss_vectors import parts, store
    from pangloss_vectors.worker import run_pending
    from pangloss_models import ModelRegistry
    from pangloss_testing import planted
    world = planted.world(seed=1, people=32000, dated=True)
    payload = next(f for f in world.factoids if f["label"].startswith("A gathering"))
    for p in parts.parts().values():
        orig = type(p).refresh
        def wrap(orig=orig, name=p.name):
            async def timed(self, changed, write):
                t = time.perf_counter(); r = await orig(self, changed, write)
                print(f"   refresh {name}: {(time.perf_counter()-t)*1000:.0f} ms, written {r.written}"); return r
            return timed
        type(p).refresh = wrap()
    Person = ModelRegistry.all_models()["Person"]; Factoid = ModelRegistry.all_models()["Factoid"]
    a = await Person.Create(label="Turn A").save(); b = await Person.Create(label="Turn B").save()
    await run_pending()
    await Factoid.Create(**{**payload, "label": "A gathering told again, timed"}).save()
    t = time.perf_counter(); n = await run_pending(); print(f"turn (a gathering): {n} heads, {(time.perf_counter()-t)*1000:.0f} ms")
    await Factoid.Create(label="turn trial", statements=[{"type":"ChildOf","label":"x","child":{"type":"Person","id":str(a.id)},"parent":{"type":"Person","id":str(b.id)},"when":{"type":"ExactDate","year":1500}}]).save()
    t = time.perf_counter(); n = await run_pending(); print(f"turn: {n} heads, {(time.perf_counter()-t)*1000:.0f} ms")
    await storage.setup.disconnect()
asyncio.run(go(URL, "memgraph"))
