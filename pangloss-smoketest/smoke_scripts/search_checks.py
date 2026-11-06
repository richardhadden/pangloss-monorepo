"""Structured search, lists and autocomplete on the filled database: timings, and counts checked against Cypher

    ../.venv/bin/python smoke_scripts/search_checks.py        # from pangloss-smoketest/
"""

import json
import random
import time
from pathlib import Path

import httpx2 as httpx
from neo4j import GraphDatabase

HERE = Path(__file__).parent
OUT = HERE / "out"
API = "http://localhost:8010/api"
R = random.Random(7)
entities = json.loads((OUT / "entities.json").read_text())
db = GraphDatabase.driver("bolt://localhost:7697", auth=("test", "test"))
results = []


def cy(q: str, **p):
    rows, _, _ = db.execute_query(q, p, database_="memgraph")
    return rows


def run(c, name, pattern, expect_count=None):
    t = time.perf_counter()
    r = c.post(f"{API}/search", json=pattern)
    ms = (time.perf_counter() - t) * 1000
    ok = r.status_code == 200
    j = r.json() if ok else {}
    count = j.get("count")
    if ok and expect_count is not None:
        ok = count == expect_count
    tag = "PASS" if ok else "FAIL"
    exp = f" expected={expect_count}" if expect_count is not None else ""
    extra = "" if r.status_code == 200 else r.text[:400]
    print(f"{tag} {name} [{ms:.0f} ms] status={r.status_code} count={count}{exp} {extra}", flush=True)
    results.append({"name": name, "ok": ok, "ms": round(ms), "count": count, "expected": expect_count, "status": r.status_code,
                    "error": extra})
    return j


def main():
    c = httpx.Client(timeout=120)
    tok = c.post(f"{API}/users/token", data={"username": "editor", "password": "smoke-editor-pw-2026"}).json()["access_token"]
    c.headers["Authorization"] = f"Bearer {tok}"

    # a well-referred person, a banker type id
    top = cy("MATCH (p:Person)<-[r]-(x) WHERE r.reverse IS NULL OR r.reverse = false WITH p, count(r) AS n "
             "RETURN p.id AS id, p.label AS label, n ORDER BY n DESC LIMIT 1")[0]
    pid = top["id"]
    print(f"most referred-to person: {top['label']} ({top['n']} edges) {pid}")
    banker = cy("MATCH (t:OccupationType {label: 'Banker'}) RETURN t.id AS id")[0]["id"]
    merchant = cy("MATCH (t:OccupationType {label: 'Merchant'}) RETURN t.id AS id")[0]["id"]

    females = cy("MATCH (p:Person {gender: 'female'}) WHERE p.deleted IS NULL OR p.deleted = false RETURN count(p) AS n")[0]["n"]
    run(c, "Person gender eq female", {"type": "Person", "where": {"gender": {"eq": "female"}}}, females)
    bankers = cy("MATCH (p:Person)-[:has_type]->(:OccupationType {label: 'Banker'}) RETURN count(DISTINCT p) AS n")[0]["n"]
    run(c, "Person has_type is Banker", {"type": "Person", "where": {"has_type": {"is": banker}}}, bankers)
    run(c, "Person has_type nested label Banker", {"type": "Person", "where": {"has_type": {"type": "OccupationType", "where": {"label": {"eq": "Banker"}}}}}, bankers)
    run(c, "Person has_type is Merchant (subtypes?)", {"type": "Person", "where": {"has_type": {"is": merchant}}})
    run(c, "Person aliases exists", {"type": "Person", "where": {"aliases": {"exists": True}}})
    run(c, "Person known_as certainty 5", {"type": "Person", "where": {"known_as": {"certainty": {"eq": 5}}}})
    run(c, "Person label starts_with 'Lorenzo'", {"type": "Person", "where": {"label": {"starts_with": "Lorenzo"}}})
    run(c, "Person label contains 'medici'", {"type": "Person", "where": {"label": {"contains": "medici"}}})
    run(c, "Person $not gender male", {"type": "Person", "where": {"$not": {"gender": {"eq": "male"}}}})
    run(c, "Person $any_of female or unknown", {"type": "Person", "where": {"$any_of": [{"gender": {"eq": "female"}}, {"gender": {"eq": "unknown"}}]}})
    run(c, "Person order by label desc", {"type": "Person", "where": {}, "order_by": [{"field": "label", "direction": "desc"}]})
    run(c, "Person order by born.sort_day", {"type": "Person", "where": {}, "order_by": [{"field": "born.sort_day"}]})
    run(c, "Person $incoming Letter sender", {"type": "Person", "where": {"$incoming": [{"type": "Letter", "field": "sender"}]}})
    run(c, "Person $incoming any Marriage", {"type": "Person", "where": {"$incoming": [{"type": "Marriage"}]}})
    run(c, "Person $incoming Death in 1500s", {"type": "Person", "where": {"$incoming": [{"type": "Death", "where": {
        "date": {"type": "ExactDate", "where": {"earliest_strict": {"gte": 2268924}}}}}]}})

    facts_all = cy("MATCH (f:Factoid) WHERE f.deleted IS NULL OR f.deleted=false RETURN count(f) AS n")[0]["n"]
    run(c, "Factoid all (logged in sees unpublished)", {"type": "Factoid", "where": {}}, facts_all)
    marriage_facts = cy("MATCH (f:Factoid)-[:statements]->(:Marriage) RETURN count(DISTINCT f) AS n")[0]["n"]
    run(c, "Factoid statements type Marriage (direct only in Cypher)", {"type": "Factoid", "where": {"statements": {"type": "Marriage", "where": {}}}})
    print(f"  (Cypher: {marriage_facts} factoids with a Marriage directly in statements; the search also sees through spaces)")
    run(c, "Factoid $mentions top person", {"type": "Factoid", "where": {"$mentions": pid}})
    run(c, "Factoid sale price > 5000", {"type": "Factoid", "where": {"statements": {"type": "Sale", "where": {"price": {"gt": "5000"}}}}})
    run(c, "Factoid statement in Negative", {"type": "Factoid", "where": {"statements": {"type": "Statement", "where": {"$spaces": ["Negative"]}}}})
    run(c, "Factoid $somewhere Settlement label 'Florence'", {"type": "Factoid", "where": {"$somewhere": [{"type": "Settlement", "where": {"label": {"contains": "Florence"}}}]}})
    run(c, "Factoid source page eq '12'", {"type": "Factoid", "where": {"source": {"type": "AtPage", "where": {"page": {"eq": "12"}}}}})
    run(c, "Factoid published false", {"type": "Factoid", "where": {"published": {"eq": False}}})
    run(c, "Factoid statement Membership via Identification",
        {"type": "Factoid", "where": {"statements": {"type": "Membership", "where": {"member": {"is": pid}}}}})
    run(c, "Factoid order_by recorded_on", {"type": "Factoid", "where": {}, "order_by": [{"field": "recorded_on", "direction": "desc"}]})
    run(c, "Factoid deep: Gift given_by a Family", {"type": "Factoid", "where": {"statements": {"type": "Gift", "where": {"given_by": {"type": "Family", "where": {}}}}}})
    run(c, "Abstract: Statement dated by sort_day order", {"type": "Statement", "where": {}, "order_by": [{"field": "date_sort_day"}]})
    run(c, "Group subclasses: name contains 'Medici'", {"type": "Group", "where": {"name": {"contains": "Medici"}}})
    run(c, "Settlement population > 100000", {"type": "Settlement", "where": {"population_estimate": {"gt": 100000}}},
        cy("MATCH (s:Settlement) WHERE s.population_estimate > 100000 RETURN count(s) AS n")[0]["n"])
    run(c, "Place coordinates latitude > 50 (TypedDict)", {"type": "Place", "where": {"coordinates": {"latitude": {"gt": 50}}}})
    run(c, "Feast rank eq double", {"type": "Feast", "where": {"rank": {"eq": "double"}}})
    run(c, "bad operator is 422", {"type": "Person", "where": {"gender": {"near": "f"}}})
    run(c, "page 2 page_size 100", {"type": "Person", "where": {}, "page": 2, "page_size": 100})

    # lists, deep search, autocomplete, timings over many words
    timings = {}
    for q in ["Medici", "Giovanni", "Lorenzo de", "Florence", "House of", "Codex", "Fugger Welser", "Factoid", "x"]:
        for model in ("Person", "Entity" if False else "Group", "Factoid", "Place"):
            t = time.perf_counter()
            r = c.get(f"{API}/{model}", params={"q": q, "page_size": 25})
            timings[f"list {model} q={q}"] = (round((time.perf_counter() - t) * 1000), r.status_code, r.json().get("count") if r.status_code == 200 else r.text[:100])
        t = time.perf_counter()
        r = c.get(f"{API}/autocomplete", params={"q": q, "type": "Entity"})
        timings[f"autocomplete Entity q={q}"] = (round((time.perf_counter() - t) * 1000), r.status_code, r.json().get("count") if r.status_code == 200 else r.text[:100])
    for k, v in timings.items():
        print(f"TIME {k}: {v[0]} ms status={v[1]} count={v[2]}")
    t = time.perf_counter()
    r = c.get(f"{API}/Factoid", params={"q": "Medici", "deep": "true", "page_size": 25})
    print(f"TIME deep search Factoid q=Medici: {(time.perf_counter() - t) * 1000:.0f} ms status={r.status_code} count={r.json().get('count') if r.status_code == 200 else r.text[:200]}")
    t = time.perf_counter()
    r = c.get(f"{API}/Person/{pid}")
    print(f"TIME GET most referred person: {(time.perf_counter() - t) * 1000:.0f} ms, {len(r.content)} bytes")
    (OUT / "search_checks.json").write_text(json.dumps({"results": results, "timings": timings, "top_person": pid}, indent=1))


if __name__ == "__main__":
    main()
