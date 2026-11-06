"""Delete a factoid with a two-person meeting and watch the MetWith between them (justifications) go and come back"""
import json, time
import httpx2 as httpx
from neo4j import GraphDatabase
API = "http://localhost:8010/api"
tok = httpx.post(f"{API}/users/token", data={"username": "editor", "password": "smoke-editor-pw-2026"}).json()["access_token"]
c = httpx.Client(headers={"Authorization": f"Bearer {tok}"}, timeout=60)
db = GraphDatabase.driver("bolt://localhost:7697", auth=("test", "test"))
rows, _, _ = db.execute_query("""
MATCH (f:Factoid)-[:statements]->(m:Meeting)-[:participants]->(:InRole)-[:target]->(a:Person)
WITH f, m, collect(DISTINCT a.id) AS people WHERE size(people) = 2
RETURN f.id AS f, people LIMIT 1""", database_="memgraph")
f, (a, b) = rows[0]["f"], rows[0]["people"]
def pair():
    d = c.get(f"{API}/Person/{a}").json().get("_derived", {}).get("MetWith", {"items": [], "count": 0})
    hit = [i for i in d["items"] if i["other"]["id"] == b]
    return d["count"], (hit[0]["justifications"] if hit else 0)
print("factoid", f, "pair", a, b)
print("before: MetWith count, justifications of the pair:", pair())
print("delete:", c.delete(f"{API}/Factoid/{f}").status_code)
for s in (1, 3, 10, 20):
    time.sleep(s - (0 if s == 1 else {3: 1, 10: 3, 20: 10}[s])); print(f"  after {s}s:", pair(), "pending", c.get(f"{API}/derived/status").json()["pending"])
print("undelete:", c.post(f"{API}/Factoid/{f}/undelete").status_code)
time.sleep(5); print("after undelete 5s:", pair())
