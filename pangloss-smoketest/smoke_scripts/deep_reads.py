"""Read the report chains of nested_checks.py back, five times each, and time the API (median)"""
import statistics, sys, time
from pathlib import Path
import os
import httpx2 as httpx

# (SMOKE_API, SMOKE_OUT, SMOKE_TOKEN, SMOKE_BOLT: for the Neo4j copy)
API_ROOT = os.environ.get("SMOKE_API", "http://localhost:8010/api")
OUT_DIR = Path("smoke_scripts") / os.environ.get("SMOKE_OUT", "out")
BOLT = os.environ.get("SMOKE_BOLT", "bolt://localhost:7697")
DB_NAME = "neo4j" if "7699" in BOLT else "memgraph"
sys.path.insert(0, "smoke_scripts")
from neo4j import GraphDatabase

with GraphDatabase.driver(BOLT, auth=("test", "test") if "7697" in BOLT else ("neo4j", os.environ.get("SMOKE_BOLT_PW", ""))) as d:
    rows, _, _ = d.execute_query("MATCH (f:Factoid) WHERE f.label CONTAINS ' reports of ' "
                                 "WITH f.label AS l, collect(f.id)[0] AS id RETURN l, id", database_=DB_NAME)
tok = os.environ.get("SMOKE_TOKEN") or dict(line.split("=", 1) for line in Path("smoke_scripts/.secrets").read_text().split())["PANGLOSS_TOKEN"]
c = httpx.Client(timeout=600, headers={"Authorization": f"Bearer {tok}"})
for r in sorted(rows, key=lambda r: int(r["l"].split()[0])):
    times = []
    for _ in range(5):
        t = time.perf_counter(); g = c.get(f"{API_ROOT}/Factoid/{r['id']}"); times.append((time.perf_counter() - t) * 1000)
    print(f"{r['l']:>24}: read {statistics.median(times):6.0f} ms (min {min(times):.0f}), {len(g.content)} bytes")
