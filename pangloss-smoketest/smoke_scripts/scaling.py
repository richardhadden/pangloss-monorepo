"""How write time grows with the number of statements in one factoid (same kinds, over the API)"""
import json, os, sys, time
from pathlib import Path
sys.path.insert(0, "smoke_scripts")
import httpx2 as httpx, statements
from fake import R
e = json.loads(Path(f"smoke_scripts/{os.environ.get('SMOKE_OUT', 'out')}/entities.json").read_text())
tok = os.environ.get("SMOKE_TOKEN") or dict(l.split("=", 1) for l in Path("smoke_scripts/.secrets").read_text().split())["PANGLOSS_TOKEN"]
c = httpx.Client(timeout=600, headers={"Authorization": f"Bearer {tok}"})
pool = statements.Pool(e, [{"type": "Book", "id": e["Book"][4]}])
kinds = sys.argv[2].split(",") if len(sys.argv) > 2 else statements.KINDS
for n in [int(x) for x in sys.argv[1].split(",")]:
    p = {"label": f"Scaling {n}", "source": pool.source(), "statements": [statements.make(pool, R.choice(kinds)) for _ in range(n)]}
    t = time.perf_counter(); r = c.post(os.environ.get("SMOKE_API", "http://localhost:8010/api") + "/Factoid", json=p); ms = (time.perf_counter() - t) * 1000
    print(f"{n:4} statements ({','.join(kinds)[:30]}): {r.status_code} {ms:8.0f} ms  ({ms / n:6.0f} ms per statement)", flush=True)
