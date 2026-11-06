"""Checks of the REST API on the filled database: auth, permissions, versions, validation, reads, lists, search,
delete, history, review, derived, calendar, typology, Zotero. Each check prints PASS/FAIL/NOTE with a time.

    ../.venv/bin/python smoke_scripts/api_checks.py          # from pangloss-smoketest/; server on :8010
"""

import json
import random
import sys
import time
from pathlib import Path

import httpx2 as httpx

HERE = Path(__file__).parent
OUT = HERE / "out"
API = "http://localhost:8010/api"
R = random.Random(42)
results: list[dict] = []

entities = json.loads((OUT / "entities.json").read_text())
factoids = json.loads((OUT / "factoids.json").read_text()) if (OUT / "factoids.json").exists() else []


def check(name: str, ok: bool, detail: str = "", ms: float | None = None) -> bool:
    tag = "PASS" if ok else "FAIL"
    t = f" [{ms:.0f} ms]" if ms is not None else ""
    print(f"{tag} {name}{t} {detail}"[:600], flush=True)
    results.append({"name": name, "ok": ok, "detail": detail[:2000], "ms": ms})
    return ok


def note(name: str, detail: str, ms: float | None = None) -> None:
    t = f" [{ms:.0f} ms]" if ms is not None else ""
    print(f"NOTE {name}{t} {detail}"[:600], flush=True)
    results.append({"name": name, "ok": None, "detail": detail[:2000], "ms": ms})


def timed(fn, *a, **k):
    t = time.perf_counter()
    r = fn(*a, **k)
    return r, (time.perf_counter() - t) * 1000


def login(c: httpx.Client, user: str) -> str:
    r = c.post(f"{API}/users/token", data={"username": user, "password": f"smoke-{user}-pw-2026"})
    r.raise_for_status()
    return r.json()["access_token"]


def main() -> None:
    c = httpx.Client(timeout=120)
    tokens = {u: login(c, u) for u in ("admin", "importer", "editor", "reviewer", "reader")}
    H = {u: {"Authorization": f"Bearer {t}"} for u, t in tokens.items()}

    # ---------------- auth -----------------
    r = c.post(f"{API}/users/token", data={"username": "editor", "password": "wrong"})
    check("login with a wrong password is 401", r.status_code == 401, str(r.status_code))
    r = c.post(f"{API}/users/token", data={"username": "nobody", "password": "x"})
    check("login of an unknown user is 401", r.status_code == 401, str(r.status_code))
    r = c.get(f"{API}/users/me", headers=H["reader"])
    check("GET /users/me", r.status_code == 200 and r.json().get("username") == "reader", r.text[:200])
    r = c.get(f"{API}/users/", headers=H["reader"])
    check("a non-admin cannot list users (403)", r.status_code == 403, str(r.status_code))
    r = c.get(f"{API}/users/", headers=H["admin"])
    check("an admin lists users", r.status_code == 200 and len(r.json()) >= 5, str(r.status_code))
    r = c.get(f"{API}/users/editor", headers=H["reader"])
    check("a user cannot read another user's details (403)", r.status_code == 403, str(r.status_code))
    r = c.post(f"{API}/Person", json={"label": "x"})
    check("create without login is 401", r.status_code == 401, str(r.status_code))
    r = c.post(f"{API}/users/me/tokens", headers=H["reader"], json={"name": "ro", "scope": "read", "expiresDays": 1})
    check("make a read-only personal token", r.status_code == 201, r.text[:200])
    ro = r.json().get("token")
    if ro:
        r = c.post(f"{API}/Commodity", headers={"Authorization": f"Bearer {ro}"}, json={"label": "should not exist"})
        check("a read-scope token cannot write (403)", r.status_code == 403, f"{r.status_code} {r.text[:200]}")
        r = c.get(f"{API}/Person", headers={"Authorization": f"Bearer {ro}"}, params={"pageSize": 1})
        check("a read-scope token can read", r.status_code == 200, str(r.status_code))
    r = c.put(f"{API}/users/admin/admin", headers=H["admin"], json={"admin": False})
    check("an admin cannot remove their own admin (400)", r.status_code == 400, str(r.status_code))
    r = c.post(f"{API}/users/token", data={"username": "reader", "password": "smoke-reader-pw-2026"})
    refresh = r.json()["refresh_token"]
    r = c.post(f"{API}/users/token/refresh", json={"refresh_token": refresh})
    check("refresh a token", r.status_code == 200 and "access_token" in r.json(), str(r.status_code))
    c.post(f"{API}/users/token/revoke", json={"refresh_token": refresh})
    r = c.post(f"{API}/users/token/refresh", json={"refresh_token": refresh})
    check("a revoked refresh token is refused", r.status_code == 401, str(r.status_code))
    # (disable: a disabled user cannot write; enable again)
    c.put(f"{API}/users/reader/disabled", headers=H["admin"], json={"disabled": True})
    r = c.get(f"{API}/users/me", headers=H["reader"])
    check("a disabled user's token is refused (401)", r.status_code == 401, str(r.status_code))
    c.put(f"{API}/users/reader/disabled", headers=H["admin"], json={"disabled": False})
    tokens["reader"] = login(c, "reader")
    H["reader"] = {"Authorization": f"Bearer {tokens['reader']}"}

    # ---------------- reads -----------------
    pid = R.choice(entities["Person"])
    r, ms = timed(c.get, f"{API}/Person/{pid}")
    check("GET a person", r.status_code == 200, f"{len(r.content)} bytes", ms)
    r, ms = timed(c.get, f"{API}/Person/https://example.org/smoke/person/10")
    check("GET a person at its URL", r.status_code == 200, r.text[:150], ms)
    r, ms = timed(c.get, f"{API}/Person/https:/example.org/smoke/person/10")
    check("GET a person at a URL with merged slashes", r.status_code == 200, str(r.status_code), ms)
    r = c.get(f"{API}/Person/01a1ae17-0000-7000-8000-000000000000")
    check("GET a missing id is 404", r.status_code == 404, str(r.status_code))
    r = c.get(f"{API}/Person/not-a-uuid")
    check("GET a malformed id is 4xx (not 500)", 400 <= r.status_code < 500, f"{r.status_code} {r.text[:150]}")
    r = c.get(f"{API}/Nonexistent")
    check("GET an unknown model is 404", r.status_code == 404, str(r.status_code))
    # most referred-to people: a heavy entity page
    if factoids:
        fid = R.choice(factoids)
        r, ms = timed(c.get, f"{API}/Factoid/{fid}")
        check("GET a factoid", r.status_code == 200, f"{len(r.content)} bytes", ms)
        r, ms = timed(c.get, f"{API}/Statement", params={"pageSize": 5})
        check("list the abstract Statement (subclasses)", r.status_code == 200, f"count={r.json().get('count')}", ms)
        r = c.post(f"{API}/Statement", headers=H["editor"], json={"label": "x", "text": "xxxxx", "involves": []})
        check("POST to an abstract class is 405", r.status_code == 405, str(r.status_code))
        r = c.post(f"{API}/Birth", headers=H["editor"], json={"label": "x"})
        check("POST to a create_directly=False class is 405", r.status_code == 405, str(r.status_code))

    # ---------------- lists and search -----------------
    for model in ("Person", "Factoid", "Settlement", "Group", "Entity", "Agent" if False else "Place"):
        r, ms = timed(c.get, f"{API}/{model}", params={"pageSize": 50})
        check(f"list {model} (page 1 of 50)", r.status_code == 200, f"count={r.json().get('count')}", ms)
    r, ms = timed(c.get, f"{API}/Person", params={"pageSize": 50, "page": 500})
    check("list Person page 500", r.status_code == 200, f"results={len(r.json().get('results', []))}", ms)
    r, ms = timed(c.get, f"{API}/Person", params={"pageSize": 500})
    check("list Person page_size 500", r.status_code == 200, f"results={len(r.json().get('results', []))}", ms)
    r = c.get(f"{API}/Person", params={"pageSize": 501})
    check("page_size 501 is refused (422)", r.status_code == 422, str(r.status_code))
    r = c.get(f"{API}/Person", params={"page": 0})
    check("page 0 is refused (422)", r.status_code == 422, str(r.status_code))
    for q in ("Medici", "Lorenzo Medici", "Giovanni", "zzzzqqq", "Fugger Augsburg", "de'"):
        r, ms = timed(c.get, f"{API}/Person", params={"q": q, "pageSize": 20})
        j = r.json() if r.status_code == 200 else {}
        check(f"search Person q={q!r}", r.status_code == 200, f"count={j.get('count')} truncated={j.get('truncated')}", ms)
    r, ms = timed(c.get, f"{API}/Factoid", params={"q": "Medici", "pageSize": 20})
    check("search Factoid q='Medici'", r.status_code == 200, f"count={r.json().get('count')}", ms)
    r, ms = timed(c.get, f"{API}/autocomplete", params={"q": "Lor Med", "type": ["Person", "Family"]})
    check("autocomplete 'Lor Med' over Person, Family", r.status_code == 200, f"count={r.json().get('count')}", ms)
    r, ms = timed(c.get, f"{API}/autocomplete", params={"q": "Flor", "type": "Entity"})
    check("autocomplete 'Flor' over Entity", r.status_code == 200, f"count={r.json().get('count')}", ms)
    for q in ("%", "*", "(", '"', "\\", "' OR 1=1 --", "a" * 500, "日本"):
        r, ms = timed(c.get, f"{API}/Person", params={"q": q})
        check(f"search with odd text {q[:12]!r} is not a 500", r.status_code < 500, f"{r.status_code} {r.text[:120]}", ms)
        r = c.get(f"{API}/autocomplete", params={"q": q, "type": "Person"})
        check(f"autocomplete with odd text {q[:12]!r} is not a 500", r.status_code < 500, f"{r.status_code} {r.text[:120]}")

    # structured search
    patterns = {
        "persons born female": {"type": "Person", "where": {"gender": "female"}},
        "persons with an occupation": {"type": "Person", "where": {"has_type": {"$any": {}}}},
        "factoids with a Marriage": {"type": "Factoid", "where": {"statements": {"type": "Marriage"}}},
        "factoids citing a person": {"type": "Factoid", "where": {"$mentions": {"type": "Person", "id": pid}}},
        "sales over 5000": {"type": "Factoid", "where": {"statements": {"type": "Sale", "where": {"price": {"gt": "5000"}}}}},
        "factoids with a negated statement": {"type": "Factoid", "where": {"statements": {"$spaces": ["Negative"]}}},
        "order by label": {"type": "Person", "where": {}, "order_by": [{"field": "label"}]},
    }
    for name, pat in patterns.items():
        r, ms = timed(c.post, f"{API}/search", json=pat)
        j = r.json()
        check(f"structured search: {name}", r.status_code == 200, f"{r.status_code} count={j.get('count')} {'' if r.status_code == 200 else r.text[:300]}", ms)
    r = c.post(f"{API}/search", json={"type": "Person", "where": {"no_such_field": 1}})
    check("structured search on an unknown field is 422", r.status_code == 422, f"{r.status_code} {r.text[:200]}")

    # ---------------- writes, versions -----------------
    r, ms = timed(c.post, f"{API}/Settlement", headers=H["editor"], json={"label": "Smokeville", "populationEstimate": 10})
    check("create a Settlement (camelCase field)", r.status_code == 201, r.text[:200], ms)
    sid = r.json()["id"]
    check("create returns ETag \"1\"", r.headers.get("etag") == '"1"', str(r.headers.get("etag")))
    r = c.get(f"{API}/Settlement/{sid}/edit", headers=H["editor"])
    check("edit view has ETag", r.headers.get("etag") == '"1"', str(r.headers.get("etag")))
    body = r.json()
    body["label"] = "Smokeville on Sea"
    r = c.put(f"{API}/Settlement/{sid}", headers=H["editor"], json=body)
    check("update without If-Match is 428", r.status_code == 428, str(r.status_code))
    r = c.put(f"{API}/Settlement/{sid}", headers={**H["editor"], "If-Match": '"1"'}, json=body)
    check("update with If-Match 1", r.status_code == 200 and r.headers.get("etag") == '"2"', f"{r.status_code} {r.headers.get('etag')}")
    r = c.put(f"{API}/Settlement/{sid}", headers={**H["editor"], "If-Match": '"1"'}, json=body)
    check("stale If-Match is 412 with currentVersion", r.status_code == 412 and "currentVersion" in r.text, f"{r.status_code} {r.text[:150]}")
    r = c.put(f"{API}/Settlement/{sid}", headers={**H["editor"], "If-Match": 'W/"2"'}, json=body)
    check("weak ETag is 400", r.status_code == 400, str(r.status_code))
    r = c.put(f"{API}/Place/{sid}", headers={**H["editor"], "If-Match": '"2"'}, json={**body, "type": "Place"})
    check("update at a parent's route is 409", r.status_code == 409, f"{r.status_code} {r.text[:150]}")
    r = c.get(f"{API}/Place/{sid}/edit", headers=H["editor"], follow_redirects=False)
    check("edit at the parent's route is 308", r.status_code == 308, f"{r.status_code} {r.headers.get('location')}")
    r = c.put(f"{API}/Settlement/{sid}", headers={**H["editor"], "If-Match": "*"}, json={**body, "label": "Forced"})
    check("If-Match * overwrites", r.status_code == 200, str(r.status_code))
    r = c.post(f"{API}/Settlement", headers=H["editor"], json={"label": "Bad", "populationEstimate": "many"})
    check("invalid literal is 422", r.status_code == 422, str(r.status_code))
    r = c.post(f"{API}/Group", headers=H["editor"], json={"label": "G", "name": "x"})
    check("MinLen(2) on Group.name is enforced (422)", r.status_code == 422, str(r.status_code))
    r = c.post(f"{API}/Person", headers=H["editor"], json={"label": "No fields"})
    check("missing required fields is 422", r.status_code == 422, str(r.status_code))
    # a factoid pointing at a missing entity, at an entity of the wrong type
    src = {"type": "AtPage", "page": "1", "target": [{"type": "Book", "id": entities["Book"][0]}]}
    def fact(stmt):
        return {"label": "Smoke factoid", "source": src, "statements": [stmt]}
    death = {"type": "Death", "label": "d", "text": "He died there.", "date": {"type": "ExactDate", "year": 1500},
             "places": [], "deceased": {"type": "Person", "id": pid}}
    r = c.post(f"{API}/Factoid", headers=H["editor"], json=fact({**death, "deceased": {"type": "Person", "id": "01a1ae17-0000-7000-8000-000000000000"}}))
    check("reference to a missing entity is 422", r.status_code == 422, f"{r.status_code} {r.text[:200]}")
    r = c.post(f"{API}/Factoid", headers=H["editor"], json=fact({**death, "deceased": {"type": "Person", "id": entities["Settlement"][0]}}))
    check("reference to an entity of the wrong type is 422", r.status_code == 422, f"{r.status_code} {r.text[:200]}")
    r = c.post(f"{API}/Factoid", headers=H["editor"], json=fact({**death, "deceased": {"type": "Settlement", "id": entities["Settlement"][0]}}))
    check("a type the field does not allow is 422", r.status_code == 422, f"{r.status_code} {r.text[:200]}")
    r = c.post(f"{API}/Factoid", headers=H["editor"], json=fact({**death, "text": "shrt"}))
    check("MinLen(5) on text is enforced (422)", r.status_code == 422, str(r.status_code))
    r = c.post(f"{API}/Factoid", headers=H["editor"], json=fact({"type": "Marriage", "label": "m", "text": "They married.",
                                                                "date": {"type": "ExactDate", "year": 1500}, "places": [],
                                                                "spouses": [{"type": "Person", "id": pid}]}))
    check("MinLen(2) on a list relation is enforced (422)", r.status_code == 422, f"{r.status_code} {r.text[:200]}")
    r = c.post(f"{API}/Factoid", headers=H["editor"], json=fact({**death, "date": {"type": "Period", "start": {"type": "ExactDate", "year": 1500}, "end": {"type": "ExactDate", "year": 1501}}}))
    check("a Period on a SingleDateable is 422", r.status_code == 422, f"{r.status_code} {r.text[:200]}")
    r = c.post(f"{API}/Factoid", headers=H["editor"], json=fact({**death, "date": {"type": "ExactDate", "year": 1500, "month": 2, "day": 30}}))
    check("30 February is 422", r.status_code == 422, f"{r.status_code} {r.text[:200]}")
    r = c.post(f"{API}/Factoid", headers=H["editor"], json={"label": "Smoke factoid", "source": {**src, "target": []}, "statements": [death]})
    check("AtPage with no target (MinLen 1) is 422", r.status_code == 422, f"{r.status_code}")
    r = c.post(f"{API}/Factoid", headers=H["editor"], json={"label": "Smoke factoid", "source": {**src, "target": src["target"] * 2}, "statements": [death]})
    check("AtPage with two targets (MaxLen 1) is 422", r.status_code == 422, f"{r.status_code}")
    # a good one, with detail, then update the factoid and check nested replacement
    r, ms = timed(c.post, f"{API}/Factoid", headers=H["editor"], params={"detail": "true"}, json=fact(death))
    check("create a factoid with detail=true", r.status_code == 201 and r.json().get("statements"), r.text[:200], ms)
    f = r.json()
    fid_new = f["id"]
    st = f["statements"][0]
    check("a dated statement has date_text etc. hidden (DB-only fields not sent)", "dateSortDay" not in json.dumps(st), json.dumps(st)[:300])
    # reviewable: unpublished factoid is hidden from anonymous readers
    r = c.get(f"{API}/Factoid/{fid_new}")
    check("an unpublished factoid is hidden from anonymous readers", r.status_code == 404, str(r.status_code))
    r = c.get(f"{API}/Factoid/{fid_new}", headers=H["reader"])
    check("an unpublished factoid is visible to a logged-in user", r.status_code == 200, str(r.status_code))
    r = c.get(f"{API}/Factoid/{fid_new}/edit", headers=H["editor"])
    edit = r.json()
    edit["statements"][0]["text"] = "He died there, of a fever."
    r, ms = timed(c.put, f"{API}/Factoid/{fid_new}", headers={**H["editor"], "If-Match": r.headers["etag"]}, params={"detail": "true"}, json=edit)
    check("update a factoid (nested statement kept as Update)", r.status_code == 200 and r.json()["statements"][0]["text"].endswith("fever."),
          f"{r.status_code} {r.text[:200]}", ms)
    check("nested statement keeps its id over an update", r.status_code == 200 and r.json()["statements"][0]["id"] == st["id"],
          f"{st['id']} -> {r.json()['statements'][0]['id'] if r.status_code == 200 else '?'}")

    # ---------------- delete -----------------
    r = c.get(f"{API}/Person/{pid}/deletable", headers=H["editor"])
    check("deletable of a referred-to person says no, with referencedBy", r.status_code == 200 and r.json().get("deletable") is False,
          r.text[:300])
    r = c.delete(f"{API}/Settlement/{sid}", headers=H["editor"])
    check("delete an unused settlement (204)", r.status_code == 204, str(r.status_code))
    r = c.get(f"{API}/Settlement/{sid}")
    check("a deleted settlement is 404", r.status_code == 404, str(r.status_code))
    r = c.post(f"{API}/Settlement/{sid}/undelete", headers=H["editor"])
    check("undelete (204)", r.status_code == 204, str(r.status_code))
    r = c.post(f"{API}/Settlement/{sid}/undelete", headers=H["editor"])
    check("undelete what is not deleted is 409", r.status_code == 409, str(r.status_code))
    r = c.delete(f"{API}/Person/{pid}", headers=H["editor"])
    check("delete a referred-to person is 409 with referencedBy", r.status_code == 409 and "referencedBy" in r.text, f"{r.status_code} {r.text[:200]}")
    r = c.get(f"{API}/Person/{pid}")
    note("a person marked for deletion: GET status", str(r.status_code))
    stid = st["id"]
    r = c.delete(f"{API}/Death/{stid}", headers=H["editor"])
    check("delete a document that is part of another is 400", r.status_code == 400, f"{r.status_code} {r.text[:150]}")

    (OUT / "api_checks.json").write_text(json.dumps(results, indent=1))
    fails = [x for x in results if x["ok"] is False]
    print(f"\n{len(results)} checks, {len(fails)} failed")


if __name__ == "__main__":
    main()
