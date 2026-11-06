"""Edge cases over the API: racing updates, entities written in a factoid's payload, a very big factoid, deep nesting,
deletes and what they do to derived facts and marked entities

    ../.venv/bin/python smoke_scripts/edge_checks.py          # from pangloss-smoketest/
"""

import asyncio
import json
import sys
import time
from pathlib import Path

import httpx2 as httpx

sys.path.insert(0, str(Path(__file__).parent))
import statements  # noqa: E402
from fake import R  # noqa: E402

OUT = Path(__file__).parent / "out"
API = "http://localhost:8010/api"
entities = json.loads((OUT / "entities.json").read_text())
factoids = json.loads((OUT / "factoids.json").read_text())
results = []


def check(name, ok, detail="", ms=None):
    t = f" [{ms:.0f} ms]" if ms is not None else ""
    print(f"{'PASS' if ok else 'FAIL'} {name}{t} {detail}"[:800], flush=True)
    results.append({"name": name, "ok": ok, "detail": detail[:1500], "ms": ms})


def note(name, detail):
    print(f"NOTE {name} {detail}"[:800], flush=True)
    results.append({"name": name, "ok": None, "detail": detail[:1500]})


def token(user):
    return httpx.post(f"{API}/users/token", data={"username": user, "password": f"smoke-{user}-pw-2026"}).json()["access_token"]


SRC = {"type": "AtPage", "page": "1", "target": [{"type": "Book", "id": entities["Book"][2]}]}


async def race(H):
    """Ten updates of one settlement at once, all based on version 1: one should win, nine get 412"""
    async with httpx.AsyncClient(headers=H, timeout=60) as c:
        r = await c.post(f"{API}/Settlement", json={"label": "Raceville"})
        sid = r.json()["id"]
        edit = (await c.get(f"{API}/Settlement/{sid}/edit")).json()

        async def one(i):
            return await c.put(f"{API}/Settlement/{sid}", headers={"If-Match": '"1"'}, json={**edit, "label": f"Raceville {i}"})

        rs = await asyncio.gather(*(one(i) for i in range(10)))
        codes = sorted(r.status_code for r in rs)
        final = (await c.get(f"{API}/Settlement/{sid}")).json()
        check("10 racing updates on version 1: exactly one wins", codes.count(200) == 1 and codes.count(412) == 9,
              f"codes={codes} final version={final['meta']['version']} label={final['label']}")


def main():
    H = {"Authorization": f"Bearer {token('editor')}"}
    c = httpx.Client(headers=H, timeout=300)
    asyncio.run(race(H))

    # --- an entity written in the payload of a factoid (create_inline): a person and a book that do not exist yet
    url = f"https://example.org/smoke/person/inline-{int(time.time())}"
    burial = {"type": "Burial", "label": "b", "text": "He was buried there.", "date": {"type": "ExactDate", "year": 1530},
              "places": [], "buried": {"type": "Person", "id": url, "create_new": True, "label": "Inline Ignatius",
                                       "known_as": {"value": "Ignatius", "certainty": 2}, "gender": "male",
                                       "born": {"type": "UnknownDate"}, "aliases": [], "has_type": []}}
    r = c.post(f"{API}/Factoid", params={"detail": "true"}, json={"label": "Inline person", "source": SRC, "statements": [burial]})
    check("a factoid makes a new person named by URL (create_inline)", r.status_code == 201, f"{r.status_code} {r.text[:200]}")
    p = c.get(f"{API}/Person/{url}")
    check("the inline person is its own entity, found at its URL", p.status_code == 200 and p.json()["label"] == "Inline Ignatius",
          f"{p.status_code}")
    r = c.post(f"{API}/Factoid", json={"label": "Inline person again", "source": SRC, "statements": [burial]})
    note("the same create_new URL a second time", f"{r.status_code} {r.text[:200]}")
    # an entity without create_inline (Settlement) cannot be written in a payload
    death = {"type": "Death", "label": "d", "text": "He died there.", "date": {"type": "ExactDate", "year": 1530},
             "places": [{"type": "Settlement", "id": "https://example.org/x", "create_new": True, "label": "Nowhere"}],
             "deceased": {"type": "Person", "id": entities["Person"][0]}}
    r = c.post(f"{API}/Factoid", json={"label": "Inline settlement", "source": SRC, "statements": [death]})
    check("an entity without create_inline cannot be made in a payload (422)", r.status_code == 422, f"{r.status_code} {r.text[:200]}")

    # --- a very big factoid: 200 statements
    pool = statements.Pool(entities, [{"type": "Book", "id": entities["Book"][3]}])
    big = {"label": "A very big factoid", "source": SRC, "statements": [statements.make(pool, R.choice(statements.KINDS)) for _ in range(200)]}
    t = time.perf_counter(); r = c.post(f"{API}/Factoid", json=big); ms = (time.perf_counter() - t) * 1000
    check("write a factoid with 200 statements", r.status_code == 201, f"{r.status_code} {r.text[:200]}", ms)
    if r.status_code == 201:
        bid = r.json()["id"]
        t = time.perf_counter(); g = c.get(f"{API}/Factoid/{bid}"); ms = (time.perf_counter() - t) * 1000
        check("read it", g.status_code == 200, f"{len(g.content)} bytes, {len(g.json()['statements'])} statements", ms)
        e = c.get(f"{API}/Factoid/{bid}/edit"); body = e.json(); body["statements"] = body["statements"][:150]
        t = time.perf_counter(); u = c.put(f"{API}/Factoid/{bid}", headers={"If-Match": e.headers["etag"]}, json=body); ms = (time.perf_counter() - t) * 1000
        check("update it, dropping 50 statements", u.status_code == 200, f"{u.status_code} {u.text[:200]}", ms)
        g = c.get(f"{API}/Factoid/{bid}")
        check("the update left 150", len(g.json()["statements"]) == 150, str(len(g.json()["statements"])))
        t = time.perf_counter(); h = c.get(f"{API}/Factoid/{bid}/history/1/diff"); ms = (time.perf_counter() - t) * 1000
        note("history diff of the big factoid v1->v2", f"{h.status_code} {len(h.content)} bytes [{ms:.0f} ms]")

    # --- deep nesting: an order of an order of an order ... 12 deep
    inner = statements.make(pool, "Letter"); inner.pop("sender", None)
    for _ in range(12):
        o = statements.order(pool)
        o.update({"type": "Order", "label": "nested order", "text": "An order to order something."})
        o["thing_ordered"]["contents"] = [inner]
        inner = {k: v for k, v in o.items() if k != "ordered_by"}
    top = {**inner, "ordered_by": pool.agent()}
    t = time.perf_counter(); r = c.post(f"{API}/Factoid", params={"detail": "true"}, json={"label": "Twelve orders deep", "source": SRC, "statements": [top]})
    ms = (time.perf_counter() - t) * 1000
    check("orders nested 12 deep (inner ordered_by left out: bound)", r.status_code == 201, f"{r.status_code} {r.text[:300]}", ms)
    if r.status_code == 201:
        node = r.json()["statements"][0]; depth = 0
        while node.get("type") == "Order":
            depth += 1; node = node["thingOrdered"]["contents"][0]
        note("depth read back, innermost", f"{depth} orders, then {node['type']} with sender={node.get('sender', {}).get('label')} spaces={node['meta'].get('semanticSpaces')}")

    # --- deleting a factoid hides what it justified
    mt = c.get(f"{API}/derived/status").json()
    fact = None
    for fid in factoids[:400]:
        f = c.get(f"{API}/Factoid/{fid}").json()
        if any(s.get("type") == "Meeting" and len(s.get("participants", [])) >= 2 for s in f.get("statements", [])):
            fact = f; break
    if fact:
        m = next(s for s in fact["statements"] if s.get("type") == "Meeting")
        a = m["participants"][0]["target"][0]
        if a["type"] == "Person":
            before = c.get(f"{API}/Person/{a['id']}").json().get("_derived", {}).get("MetWith", {}).get("count")
            r = c.delete(f"{API}/Factoid/{fact['id']}")
            check("delete a factoid", r.status_code == 204, str(r.status_code))
            time.sleep(3)
            after = c.get(f"{API}/Person/{a['id']}").json().get("_derived", {}).get("MetWith", {}).get("count")
            check("deleting it removes a MetWith of a participant (within 3 s)", (before or 0) > (after or 0), f"before={before} after={after}")
            r = c.post(f"{API}/Factoid/{fact['id']}/undelete")
            time.sleep(3)
            again = c.get(f"{API}/Person/{a['id']}").json().get("_derived", {}).get("MetWith", {}).get("count")
            check("undelete brings it back", again == before, f"undelete {r.status_code}, count={again}")
    note("derived worker", json.dumps(mt.get("worker"))[:300])

    # --- an entity marked for deletion: still listed? still offered in autocomplete? still a valid reference?
    pid = entities["Person"][1234]
    r = c.delete(f"{API}/Person/{pid}")
    note("delete a person that is referred to", f"{r.status_code} {r.text[:150]}")
    if r.status_code == 409:
        lbl = c.get(f"{API}/Person/{pid}").json()["label"]
        ac = c.get(f"{API}/autocomplete", params={"q": lbl, "type": "Person", "page_size": 50}).json()
        note("the marked person in autocomplete", f"{'offered' if any(x['id'] == pid for x in ac['results']) else 'not offered'}")
        r = c.post(f"{API}/Factoid", json={"label": "Refers to a marked person", "source": SRC, "statements": [{**death, "places": [], "deceased": {"type": "Person", "id": pid}}]})
        note("a new reference to the marked person", f"{r.status_code} {r.text[:200]}")

    (OUT / "edge_checks.json").write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
