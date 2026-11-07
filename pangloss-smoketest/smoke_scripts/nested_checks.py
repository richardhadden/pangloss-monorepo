"""The deeply nested kinds (2026-11-07): write each at its deepest, read it back, compare, time

    ../.venv/bin/python smoke_scripts/nested_checks.py          # from pangloss-smoketest/, API on :8010

- Report of a report of a report of a report of an order of an order of an order of a letter (Hearsay spaces in
  documents in Positive/NegativeSubjunctive spaces: 8 documents deep);
- Witnessing: witnesses as Attributed[InRole[Identification[WeightedAlternative[Person]]]] (reified four deep);
- SealedLetter: Seal > SealImpression > SealMatrix (embedded three deep).
"""

import json
import sys
import time
from pathlib import Path

import os
import httpx2 as httpx

# (SMOKE_API, SMOKE_OUT, SMOKE_TOKEN, SMOKE_BOLT: for the Neo4j copy)
API_ROOT = os.environ.get("SMOKE_API", "http://localhost:8010/api")
OUT_DIR = Path("smoke_scripts") / os.environ.get("SMOKE_OUT", "out")
BOLT = os.environ.get("SMOKE_BOLT", "bolt://localhost:7697")
DB_NAME = "neo4j" if "7699" in BOLT else "memgraph"

sys.path.insert(0, "smoke_scripts")
import statements  # noqa: E402
import fake  # noqa: E402
from fake import R  # noqa: E402

API = API_ROOT
e = json.loads((OUT_DIR / "entities.json").read_text())
tok = os.environ.get("SMOKE_TOKEN") or dict(line.split("=", 1) for line in Path("smoke_scripts/.secrets").read_text().split())["PANGLOSS_TOKEN"]
c = httpx.Client(timeout=600, headers={"Authorization": f"Bearer {tok}"})
pool = statements.Pool(e, [{"type": "Book", "id": e["Book"][5]}])
R.seed(7)


def report_chain(reports: int, orders: int) -> dict:
    inner = statements.make(pool, "Letter")
    if orders:
        inner.pop("sender")  # (bound from the innermost order's ordered_to)
    for _ in range(orders):
        o = {**statements.base("Order", "nested order", "An order."), **statements.order(pool)}
        o["thing_ordered"]["contents"] = [inner]
        inner = o
    for _ in range(reports):
        inner = {**statements.base("Report", "nested report", "Someone said."), "reporter": pool.agent(),
                 "reported": {"type": "Hearsay", "contents": [inner]}}
    return inner


def depth_of(node: dict) -> list[str]:
    """The chain of document types down the first item of each space"""
    chain = []
    while isinstance(node, dict) and node.get("type") in ("Report", "Order", "Letter"):
        chain.append(node["type"])
        if node["type"] == "Report":
            node = node["reported"]["contents"][0]
        elif node["type"] == "Order":
            node = node["thingOrdered"]["contents"][0]
        else:
            break
    return chain


def post(label: str, stmts: list[dict]) -> tuple[dict | None, float, float]:
    t = time.perf_counter()
    r = c.post(f"{API}/Factoid", params={"detail": "true"},
               json={"label": label, "source": pool.source(), "statements": stmts})
    w = (time.perf_counter() - t) * 1000
    if r.status_code != 201:
        print(f"{label}: {r.status_code} {r.text[:600]}")
        return None, w, 0
    t = time.perf_counter()
    g = c.get(f"{API}/Factoid/{r.json()['id']}")
    rd = (time.perf_counter() - t) * 1000
    return g.json(), w, rd


results = {}
for reports, orders in [(1, 0), (2, 1), (4, 3), (6, 6), (10, 10)]:
    got, w, rd = post(f"{reports} reports of {orders} orders", [report_chain(reports, orders)])
    if got:
        chain = depth_of(got["statements"][0])
        ok = chain == ["Report"] * reports + ["Order"] * orders + ["Letter"]
        print(f"reports {reports} orders {orders}: write {w:.0f} ms, read {rd:.0f} ms, chain read back ok={ok} "
              f"({len(chain)} documents)")
        results[f"report{reports}_order{orders}"] = {"write_ms": w, "read_ms": rd, "ok": ok}

# Witnessing, four reified levels
wit = {**statements.base("Witnessing", "witnessed", "Witnessed."), "date": fake.any_date(), "places": [],
       "presided_by": pool.agent(), "witnesses": [statements.witness(pool) for _ in range(6)]}
got, w, rd = post("witnessing 6 x 4 deep", [wit])
if got:
    s = got["statements"][0]
    first = s["witnesses"][0]
    lvl = [first["type"], first["target"][0]["type"], first["target"][0]["target"][0]["type"],
           first["target"][0]["target"][0]["target"][0]["type"]]
    people = first["target"][0]["target"][0]["target"][0]["alternatives"]
    sent = wit["witnesses"][0]["target"][0]["target"][0]["target"][0]["alternatives"]
    ok = lvl == ["Attributed", "InRole", "Identification", "WeightedAlternative"] and \
        [p["id"] for p in people] == [p["id"] for p in sent] and \
        [p["edgeProperties"]["percent"] for p in people] == [p["edge_properties"]["percent"] for p in sent]
    print(f"witnessing: write {w:.0f} ms, read {rd:.0f} ms, levels {lvl}, people and percentages read back ok={ok}")
    results["witnessing"] = {"write_ms": w, "read_ms": rd, "ok": ok}

# SealedLetter, three embedded levels
sl = statements.make(pool, "SealedLetter")
got, w, rd = post("sealed letter", [sl])
if got:
    seal = got["statements"][0]["seal"]
    ok = seal["impression"]["matrix"]["motto"] == sl["seal"]["impression"]["matrix"]["motto"] and \
        seal["impression"]["waxColour"] == sl["seal"]["impression"]["wax_colour"]
    print(f"sealed letter: write {w:.0f} ms, read {rd:.0f} ms, seal read back ok={ok}")
    results["sealed_letter"] = {"write_ms": w, "read_ms": rd, "ok": ok, "id": got["statements"][0]["id"]}

(OUT_DIR / "nested_checks.json").write_text(json.dumps(results, indent=1))
