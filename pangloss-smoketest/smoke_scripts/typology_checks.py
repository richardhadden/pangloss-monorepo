"""Typology routes: make, move (to a root and back), refuse a cycle, rename, path, as editor; and search by a supertype"""
import json, httpx2 as httpx
API = "http://localhost:8010/api"
tok = httpx.post(f"{API}/users/token", data={"username": "editor", "password": "smoke-editor-pw-2026"}).json()["access_token"]
c = httpx.Client(headers={"Authorization": f"Bearer {tok}"}, timeout=60)
def show(name, r): print(f"{name}: {r.status_code} {r.text[:250]}")
tree = c.get(f"{API}/typology/OccupationType/tree").json()
merchant = next(t for t in tree if t["label"] == "Merchant"); banker = next(t for t in merchant["children"] if t["label"] == "Banker")
r = c.post(f"{API}/typology/OccupationType", json={"label": "Court banker", "supertype": banker["id"]}); show("make Court banker under Banker", r)
cb = r.json().get("id")
show("path of Court banker", c.get(f"{API}/typology/OccupationType/{cb}/path"))
show("move Merchant under Court banker (a cycle)", c.post(f"{API}/typology/OccupationType/{merchant['id']}/move", json={"to": cb}))
show("move Court banker to a root", c.post(f"{API}/typology/OccupationType/{cb}/move", json={"to": None}))
show("rename it", c.patch(f"{API}/typology/OccupationType/{cb}", json={"label": "Papal banker"}))
show("make a duplicate label at the root", c.post(f"{API}/typology/OccupationType", json={"label": "Merchant"}))
show("delete Banker (in use)", c.delete(f"{API}/OccupationType/{banker['id']}"))
for body in ({"has_type": {"is": merchant["id"]}}, {"has_type": {"is": merchant["id"], "subtypes": True}},
             {"has_type": {"type": "OccupationType", "where": {"supertype": {"is": merchant["id"]}}}}):
    r = c.post(f"{API}/search", json={"type": "Person", "where": body}); show(f"search {json.dumps(body)[:90]}", r)
