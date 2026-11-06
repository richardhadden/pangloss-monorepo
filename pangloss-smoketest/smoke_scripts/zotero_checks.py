"""Zotero by hand: base a Book on a ZoteroObject that factoids cite, check the citations follow, unlink it again"""
import httpx2 as httpx
from neo4j import GraphDatabase
API = "http://localhost:8010/api"
tok = httpx.post(f"{API}/users/token", data={"username": "editor", "password": "smoke-editor-pw-2026"}).json()["access_token"]
c = httpx.Client(headers={"Authorization": f"Bearer {tok}"}, timeout=120)
db = GraphDatabase.driver("bolt://localhost:7697", auth=("test", "test"))
rows, _, _ = db.execute_query("""MATCH (z:ZoteroObject)<-[:target]-(:AtPage)<-[:source]-(f:Factoid)
WITH z, count(f) AS n WHERE n >= 2 RETURN z.id AS id, z.label AS label, z.zotero_url AS url, n LIMIT 1""", database_="memgraph")
z = rows[0]; print("item", z["label"][:60], "cited by", z["n"], "factoids", z["url"])
r = c.post(f"{API}/zotero/base-on", json={"model": "Book", "item": z["id"], "data": {"label": z["label"]}})
print("base-on:", r.status_code, r.text[:250])
b = c.get(f"{API}/Book/{z['id']}")
print("GET Book at the same id:", b.status_code, b.json().get("type") if b.status_code == 200 else b.text[:150], "| zotero_url kept:", b.json().get("zoteroUrl") == z["url"] if b.status_code == 200 else None)
rows, _, _ = db.execute_query("MATCH (n {id: $id})<-[:target]-(:AtPage)<-[:source]-(f:Factoid) RETURN labels(n) AS l, count(f) AS n", {"id": z["id"]}, database_="memgraph")
print("still cited:", rows[0]["n"], "labels:", rows[0]["l"])
r = c.post(f"{API}/zotero/unlink", json={"model": "Book", "id": z["id"]})
print("unlink:", r.status_code, r.text[:250])
rows, _, _ = db.execute_query("MATCH (n:Entity) WHERE n.zotero_url = $u RETURN n.id AS id, labels(n) AS l", {"u": z["url"]}, database_="memgraph")
print("after unlink, nodes with that zotero_url:", [(x["id"][:8], [l for l in x["l"] if l in ("Book", "ZoteroObject")]) for x in rows])
rows, _, _ = db.execute_query("MATCH (n {id: $id}) RETURN labels(n) AS l, n.zotero_url AS u", {"id": z["id"]}, database_="memgraph")
print("the Book (same id) now:", [l for l in rows[0]["l"] if l in ("Book", "ZoteroObject")], "zotero_url", rows[0]["u"])
