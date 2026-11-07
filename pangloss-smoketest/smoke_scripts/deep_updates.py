"""Update the report chains of nested_checks.py: read the edit view, change the innermost letter's label, PUT it
back with If-Match; time it and check the change and the ids of the nested documents survive"""
import json, sys, time
from pathlib import Path
import os
import httpx2 as httpx

# (SMOKE_API, SMOKE_OUT, SMOKE_TOKEN, SMOKE_BOLT: for the Neo4j copy)
API_ROOT = os.environ.get("SMOKE_API", "http://localhost:8010/api")
OUT_DIR = Path("smoke_scripts") / os.environ.get("SMOKE_OUT", "out")
BOLT = os.environ.get("SMOKE_BOLT", "bolt://localhost:7697")
DB_NAME = "neo4j" if "7699" in BOLT else "memgraph"
from neo4j import GraphDatabase

with GraphDatabase.driver(BOLT, auth=("test", "test") if "7697" in BOLT else ("neo4j", os.environ.get("SMOKE_BOLT_PW", ""))) as d:
    rows, _, _ = d.execute_query("MATCH (f:Factoid) WHERE f.label CONTAINS ' reports of ' "
                                 "WITH f.label AS l, collect(f.id)[0] AS id RETURN l, id", database_=DB_NAME)
tok = os.environ.get("SMOKE_TOKEN") or dict(line.split("=", 1) for line in Path("smoke_scripts/.secrets").read_text().split())["PANGLOSS_TOKEN"]
c = httpx.Client(timeout=600, headers={"Authorization": f"Bearer {tok}"})
API = API_ROOT


def walk(node):
    """The documents down the chain, outermost first"""
    out = []
    while isinstance(node, dict) and node.get("type") in ("Report", "Order", "Letter"):
        out.append(node)
        if node["type"] == "Report":
            node = node["reported"]["contents"][0]
        elif node["type"] == "Order":
            node = node["thingOrdered"]["contents"][0]
        else:
            break
    return out


for r in sorted(rows, key=lambda r: int(r["l"].split()[0])):
    t = time.perf_counter()
    e = c.get(f"{API}/Factoid/{r['id']}/edit")
    t_edit = (time.perf_counter() - t) * 1000
    body, etag = e.json(), e.headers.get("etag")
    chain = walk(body["statements"][0])
    ids = [n["id"] for n in chain]
    chain[-1]["label"] = f"changed {time.time():.0f}"
    t = time.perf_counter()
    u = c.put(f"{API}/Factoid/{r['id']}", headers={"If-Match": etag}, json=body)
    t_put = (time.perf_counter() - t) * 1000
    if u.status_code != 200:
        print(f"{r['l']:>24}: edit {t_edit:.0f} ms, PUT {u.status_code} {u.text[:400]}")
        continue
    after = walk(c.get(f"{API}/Factoid/{r['id']}").json()["statements"][0])
    print(f"{r['l']:>24}: edit view {t_edit:5.0f} ms ({len(e.content)} bytes), PUT {t_put:6.0f} ms; "
          f"label changed {after[-1]['label'] == chain[-1]['label']}, ids kept {[n['id'] for n in after] == ids}")
