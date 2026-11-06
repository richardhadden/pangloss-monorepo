"""One factoid of n statements: made, read, updated with a quarter of its statements dropped, read again, deleted

    ../.venv/bin/python smoke_scripts/large_update.py 200
"""
import json, os, sys, time
from pathlib import Path
sys.path.insert(0, "smoke_scripts")
import httpx2 as httpx, statements
from fake import R
e = json.loads(Path(f"smoke_scripts/{os.environ.get('SMOKE_OUT', 'out')}/entities.json").read_text())
tok = os.environ.get("SMOKE_TOKEN") or dict(l.split("=", 1) for l in Path("smoke_scripts/.secrets").read_text().split())["PANGLOSS_TOKEN"]
api = os.environ.get("SMOKE_API", "http://localhost:8010/api")
c = httpx.Client(timeout=600, headers={"Authorization": f"Bearer {tok}"})
pool = statements.Pool(e, [{"type": "Book", "id": e["Book"][4]}])
n = int(sys.argv[1]) if len(sys.argv) > 1 else 200


def timed(what, call):
    t = time.perf_counter(); r = call(); ms = (time.perf_counter() - t) * 1000
    print(f"{what}: {r.status_code} {ms:8.0f} ms", flush=True)
    return r


p = {"label": f"Large update {n}", "source": pool.source(), "statements": [statements.make(pool, R.choice(statements.KINDS)) for _ in range(n)]}
made = timed(f"create with {n} statements", lambda: c.post(f"{api}/Factoid", json=p)).json()
timed("read", lambda: c.get(f"{api}/Factoid/{made['id']}"))
read = timed("read to edit", lambda: c.get(f"{api}/Factoid/{made['id']}/edit"))
doc = read.json()
doc["statements"] = doc["statements"][: n - n // 4]
r = timed(f"update, dropping {n // 4}", lambda: c.put(f"{api}/Factoid/{made['id']}", json=doc, headers={"If-Match": read.headers["etag"]}))
if r.status_code != 200:
    print(r.text[:600])
again = timed("read again", lambda: c.get(f"{api}/Factoid/{made['id']}"))
print("statements now:", len(again.json()["statements"]), "version", again.json()["meta"]["version"])
timed("delete", lambda: c.delete(f"{api}/Factoid/{made['id']}"))
