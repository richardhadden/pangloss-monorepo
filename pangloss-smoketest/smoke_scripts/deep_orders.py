"""Orders nested N deep (each orders the next; the innermost is a Letter whose sender is bound from ordered_to)"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, "smoke_scripts")
import httpx2 as httpx, statements
e = json.loads(Path("smoke_scripts/out/entities.json").read_text())
tok = dict(l.split("=", 1) for l in Path("smoke_scripts/.secrets").read_text().split())["PANGLOSS_TOKEN"]
c = httpx.Client(timeout=600, headers={"Authorization": f"Bearer {tok}"})
pool = statements.Pool(e, [{"type": "Book", "id": e["Book"][5]}])
for depth in [int(x) for x in sys.argv[1].split(",")]:
    inner = statements.make(pool, "Letter"); inner.pop("sender")
    for _ in range(depth):
        o = statements.order(pool); o.update({"type": "Order", "label": "nested order", "text": "An order to order something."})
        o["thing_ordered"]["contents"] = [inner]; inner = o
    t = time.perf_counter()
    r = c.post("http://localhost:8010/api/Factoid", params={"detail": "true"}, json={"label": f"{depth} orders deep", "source": pool.source(), "statements": [inner]})
    ms = (time.perf_counter() - t) * 1000
    if r.status_code != 201: print(depth, r.status_code, r.text[:300]); continue
    node, d, last_to = r.json()["statements"][0], 0, None
    while node.get("type") == "Order":
        d += 1; last_to = node["orderedTo"]["id"]; node = node["thingOrdered"]["contents"][0]
    t2 = time.perf_counter(); g = c.get(f"http://localhost:8010/api/Factoid/{r.json()['id']}"); ms2 = (time.perf_counter() - t2) * 1000
    print(f"depth {depth}: write {ms:.0f} ms, read {ms2:.0f} ms; read back {d} orders; innermost Letter sender == last ordered_to: "
          f"{node.get('sender', {}).get('id') == last_to}; spaces {len(node['meta']['semanticSpaces'])}: {node['meta']['semanticSpaces'][:3]}...")
