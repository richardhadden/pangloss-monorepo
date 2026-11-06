"""Review, history, typology, calendar and Zotero routes, as different users

    ../.venv/bin/python smoke_scripts/review_history_checks.py       # from pangloss-smoketest/
"""

import json
import random
import time
from pathlib import Path

import httpx2 as httpx

HERE = Path(__file__).parent
OUT = HERE / "out"
API = "http://localhost:8010/api"
R = random.Random(99)
results = []
factoids = json.loads((OUT / "factoids.json").read_text())
entities = json.loads((OUT / "entities.json").read_text())


def check(name, ok, detail="", ms=None):
    t = f" [{ms:.0f} ms]" if ms is not None else ""
    print(f"{'PASS' if ok else 'FAIL'} {name}{t} {detail}"[:700], flush=True)
    results.append({"name": name, "ok": ok, "detail": detail[:1500], "ms": ms})


def note(name, detail):
    print(f"NOTE {name} {detail}"[:700], flush=True)
    results.append({"name": name, "ok": None, "detail": detail[:1500]})


def client(user):
    c = httpx.Client(timeout=120)
    r = c.post(f"{API}/users/token", data={"username": user, "password": f"smoke-{user}-pw-2026"})
    c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return c


def timed(fn, *a, **k):
    t = time.perf_counter()
    r = fn(*a, **k)
    return r, (time.perf_counter() - t) * 1000


def main():
    anon = httpx.Client(timeout=120)
    editor, reviewer, importer, admin = client("editor"), client("reviewer"), client("importer"), client("admin")

    # ---------------- review -----------------
    r, ms = timed(reviewer.get, f"{API}/review/queue", params={"status": "unchecked", "type": "Factoid"})
    check("review queue", r.status_code == 200, f"{r.status_code} {str(r.json())[:200]}", ms)
    q = r.json()
    fid = factoids[0]
    r = importer.post(f"{API}/review/{fid}/status", json={"status": "checked"})
    check("importer cannot check their own factoid (403)", r.status_code == 403, f"{r.status_code} {r.text[:200]}")
    r = reviewer.post(f"{API}/review/{fid}/comments", json={"text": "Page number looks wrong"})
    check("reviewer comments", r.status_code in (200, 201), f"{r.status_code} {r.text[:200]}")
    cid = r.json().get("id") if r.status_code in (200, 201) else None
    f = reviewer.get(f"{API}/Factoid/{fid}").json()
    part = f["statements"][0]["id"] if "id" in f["statements"][0] else None
    if part:
        r = reviewer.post(f"{API}/review/{fid}/comments", json={"text": "This statement?", "targetId": part})
        check("reviewer comments on a part", r.status_code in (200, 201), f"{r.status_code} {r.text[:200]}")
    r = reviewer.post(f"{API}/review/{fid}/comments", json={"text": "bad target", "targetId": factoids[1]})
    check("comment on a part not in the document is 422", r.status_code == 422, f"{r.status_code} {r.text[:200]}")
    if cid:
        r = reviewer.post(f"{API}/review/{fid}/comments/{cid}/resolve")
        check("resolve a comment", r.status_code in (200, 204), str(r.status_code))
    r = reviewer.get(f"{API}/review/{fid}", params={"resolved": "true"})
    check("review state with resolved comments", r.status_code == 200, r.text[:300])
    # publish 500 factoids, timed
    times = []
    for i in factoids[:500]:
        r, ms = timed(reviewer.post, f"{API}/review/{i}/status", json={"status": "checked"})
        times.append(ms)
        if r.status_code != 200:
            check("check a factoid", False, f"{r.status_code} {r.text[:200]}")
            break
    times.sort()
    note("checking 500 factoids one by one", f"p50 {times[len(times) // 2]:.0f} ms, p95 {times[int(len(times) * .95)]:.0f} ms")
    r = anon.get(f"{API}/Factoid/{factoids[0]}")
    check("a checked factoid is visible to anonymous", r.status_code == 200, str(r.status_code))
    r = anon.get(f"{API}/Factoid", params={"page_size": 1})
    check("anonymous list counts the published factoids", r.json().get("count") == 500, f"count={r.json().get('count')}")
    # editing a checked factoid: does it go back to unchecked?
    r = editor.get(f"{API}/Factoid/{factoids[0]}/edit")
    body, etag = r.json(), r.headers.get("etag")
    body["label"] = body["label"] + " (edited)"
    r = editor.put(f"{API}/Factoid/{factoids[0]}", headers={"If-Match": etag}, json=body)
    check("editor updates a checked factoid", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    st = reviewer.get(f"{API}/review/{factoids[0]}").json()
    note("review state after an edit of a checked factoid", json.dumps(st)[:300])
    r = anon.get(f"{API}/Factoid/{factoids[0]}")
    note("anonymous GET after the edit", f"{r.status_code} label={r.json().get('label') if r.status_code == 200 else ''}")
    # created as checked in one request
    src = {"type": "AtPage", "page": "9", "target": [{"type": "Book", "id": entities["Book"][1]}]}
    stmt = {"type": "Burial", "label": "b", "text": "He was buried.", "date": {"type": "ExactDate", "year": 1550}, "places": [],
            "buried": {"type": "Person", "id": entities["Person"][5]}}
    r = editor.post(f"{API}/Factoid", params={"review_status": "checked"}, json={"label": "Pre-checked", "source": src, "statements": [stmt]})
    check("create with ?review_status=checked", r.status_code == 201, f"{r.status_code} {r.text[:200]}")
    if r.status_code == 201:
        r2 = anon.get(f"{API}/Factoid/{r.json()['id']}")
        check("pre-checked factoid is published at once", r2.status_code == 200, str(r2.status_code))

    # ---------------- history -----------------
    r, ms = timed(editor.get, f"{API}/Factoid/{factoids[0]}/history")
    check("history of an edited factoid", r.status_code == 200, f"{r.status_code} {r.text[:400]}", ms)
    (OUT / "history_sample.json").write_text(r.text)

    # ---------------- typology -----------------
    r, ms = timed(anon.get, f"{API}/typology/OccupationTypology/tree")
    if r.status_code == 404:
        r, ms = timed(anon.get, f"{API}/typology/OccupationType/tree")
    check("occupation typology", r.status_code == 200, f"{r.status_code} {r.text[:300]}", ms)

    # ---------------- calendar -----------------
    for path in ("calendar/month/gregorian/1500/3", "calendar/day/G1500-03-25", "calendar/month/julian/1582/10", "calendar/day/G1582-10-10", "calendar/easter/gregorian/1600", "calendar/year/gregorian/1550", "calendar/characterisations"):
        r, ms = timed(anon.get, f"{API}/{path}")
        check(f"GET /api/{path}", r.status_code in (200, 404, 422), f"{r.status_code} {r.text[:250]}", ms)

    # ---------------- zotero -----------------
    for path in ("zotero/status", "typology/types", "calendar/settings"):
        r, ms = timed(admin.get, f"{API}/{path}")
        note(f"GET /api/{path}", f"{r.status_code} {r.text[:250]} [{ms:.0f} ms]")
    z = anon.get(f"{API}/ZoteroObject", params={"page_size": 1}).json()["results"][0]
    r = admin.get(f"{API}/ZoteroObject/{z['id']}/edit")
    body, etag = r.json(), r.headers.get("etag")
    body["title"] = "Changed by hand"
    r = admin.put(f"{API}/ZoteroObject/{z['id']}", headers={"If-Match": etag}, json=body)
    check("Zotero-owned field cannot be edited through the API", r.status_code in (400, 403, 409, 422), f"{r.status_code} {r.text[:250]}")

    (OUT / "review_history_checks.json").write_text(json.dumps(results, indent=1))
    print(f"{len(results)} checks, {sum(1 for x in results if x['ok'] is False)} failed")


if __name__ == "__main__":
    main()
