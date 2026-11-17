"""Measurements for implementation_docs/matches-criteria.md, before anything is built.

Run from a copy of this demo whose settings point at a scratch Memgraph holding the bulk-loaded data of
implementation_docs/large-data.md (2026-11-17: the container `pangloss-memgraph-identity` on :7690, which `ddl` below
names), never at the demo's own database:

    cp pangloss-demo/criteria_benchmark.py /tmp/smoke/ && cd /tmp/smoke
    ../path/to/.venv/bin/python criteria_benchmark.py [seeds] [compiled] [anchor] [choose] [batch]

Reads the data; writes only PGBench* nodes (stand-ins for descriptions) and two indexes, and removes them at the end.
"""
import asyncio, random, statistics, subprocess, sys, time, uuid

from pangloss_cli import load_project
from pangloss_models import Match, initialise
from pangloss_users import current_request_username

rng = random.Random(11)
WHAT = set(sys.argv[1:]) or {"compiled", "anchor", "seeds", "choose", "batch"}
RUNS = 7


def ddl(statement):
    """Index changes need an auto-commit transaction (Memgraph): through mgconsole in the scratch container"""
    subprocess.run(["docker", "exec", "-i", "pangloss-memgraph-identity", "mgconsole", "--username", "test", "--password", "test"],
                   input=statement + ";\n", text=True, check=True, capture_output=True)


def line(label, ms, extra=""):
    print(f"  {label:<70} {ms:9.2f} ms  {extra}", flush=True)


async def timed(make, n=RUNS):
    await make()  # warm (and the plan cached)
    times, out = [], None
    for _ in range(n):
        t = time.perf_counter()
        out = await make()
        times.append((time.perf_counter() - t) * 1000)
    return statistics.median(times), out


# The visibility checks the compiler writes for a document met on the way: not deleted, its head neither
WALK_UP = """NOT coalesce({v}.deleted, false) AND NOT EXISTS {{ MATCH ({v})-[* 0.. (q_e, q_to | coalesce(q_e.reverse, false))]->(hh:HeadNode)
        WHERE hh.deleted OR NOT ($see_unpublished OR coalesce(hh.published, true)) }}"""
LISTED = "NOT coalesce(n.deleted, false) AND ($see_unpublished OR coalesce(n.published, true)) AND n.merged_into IS NULL"


async def main():
    project = load_project()
    backend = project.require_database()
    project.import_models()
    initialise()
    from demo_app import models as m
    from pangloss_core import backend as be
    from pangloss_cypher.search_query import build_search_query
    from pangloss_models.search import check_match, search_match

    current_request_username.set("loader")
    await backend.connect()
    db = be.current().database()

    @db.read_transaction
    async def q(tx, query, **p):
        return await (await tx.run(query, **p)).data()

    @db.write_transaction
    async def w(tx, query, **p):
        return await (await tx.run(query, **p)).data()

    print("nodes:", (await q("MATCH (n) RETURN count(n) AS c"))[0]["c"], flush=True)

    # Anchors: givers of transfers (an ordinary one), and the busiest giver; carriers of activities with witnesses
    givers = [r["id"] for r in await q(
        "MATCH (p:Person)<-[:given_by]-(:Transfer) WITH p, count(*) AS n WHERE n >= 2 RETURN p.id AS id LIMIT 400")]
    carriers = [r["id"] for r in await q(
        "MATCH (p:Person)<-[:carried_out_by]-(a:Activity)-[:participants]->(:InRole) WITH p, count(DISTINCT a) AS n "
        "WHERE n >= 2 RETURN p.id AS id LIMIT 400")]
    hub = (await q("MATCH (p:Person)<-[e:carried_out_by]-() WITH p, count(e) AS n ORDER BY n DESC LIMIT 1 RETURN p.id AS id, n"))[0]
    print(f"hub carries {hub['n']} activities", flush=True)
    giver, carrier = givers[0], carriers[0]
    some_year = (await q("MATCH (t:Transfer)-[:given_by]->(:Person {id: $g}) MATCH (t)-[:date]->(d) RETURN d.year AS y LIMIT 1", g=giver))[0]["y"]
    # a year's day numbers (Julian day numbers of 1 Jan of the year and the next, near enough for a range)
    jdn = lambda y: int(365.25 * (y + 4716)) - 1524 + 1  # (Julian calendar, 1 January)
    lo, hi = jdn(some_year), jdn(some_year + 1) - 1

    P = {
        "P1 local: received a transfer from X": {"$incoming": [{"type": "Transfer", "field": "given_to", "where": {"given_by": {"is": giver}}}]},
        "P2 local, through InRole: witnessed an activity of X": {"$incoming": [{"type": "Activity", "field": "participants", "where": {"carried_out_by": {"is": carrier}}}]},
        "P3 local + date: received from X in year Y": {"$incoming": [{"type": "Transfer", "field": "given_to", "where": {
            "given_by": {"is": giver}, "date": {"type": "ExactDate", "where": {"latest_fuzzy": {"gte": lo}, "earliest_fuzzy": {"lte": hi}}}}}]},
        "P4 broad: carried out a battle (no anchor)": {"$incoming": [{"type": "Activity", "field": "carried_out_by", "where": {"activity_type": {"eq": "battle"}}}]},
        "P5 far: received from someone who witnessed for X": {"$incoming": [{"type": "Transfer", "field": "given_to", "where": {"given_by": {
            "type": "Person", "where": {"$incoming": [{"type": "Activity", "field": "participants", "where": {"carried_out_by": {"is": carrier}}}]}}}}]},
    }

    def compiled(where, page_size=50):
        match = search_match(m.Person, Match(type="Person", where=where))
        conds = check_match(m.Person, match)
        return build_search_query(m.Person, conds, 1, page_size)

    def seeded(where):
        query, params = compiled(where)
        start = "MATCH (n:`Person`:Entity)\n    WHERE "
        assert start in query
        return query.replace(start, "UNWIND $seeds AS seed_id\n    MATCH (n:PGIndexableNode {id: seed_id})\n    WHERE n:Person AND "), params

    async def run(query, params, **extra):
        return (await q(query, **params, **extra))[0]["response"]

    # Seeds: what a batch of written factoids refers to, read as the worker would (one query for the batch)
    SEEDS_QUERY = """
    UNWIND $heads AS hid
    MATCH (h:HeadNode {id: hid})
    OPTIONAL MATCH (h)-[e0]->(x0:Entity) WHERE NOT coalesce(e0.reverse, false)
    WITH h, hid, collect(DISTINCT x0.id) AS own
    OPTIONAL MATCH (part:PGIndexableNode {head_node_id: hid})-[e1]->(x1:Entity) WHERE NOT coalesce(e1.reverse, false)
    WITH hid, own, collect(DISTINCT x1.id) AS inner, [l IN collect(DISTINCT labels(part)) | l] AS part_labels
    RETURN hid, own + inner AS refs, part_labels
    """
    # (factoids of the bulk load, "Factoid <n>": not the leftovers of earlier measuring, which name one person each)
    heads200 = [r["id"] for r in await q("UNWIND $labels AS l MATCH (f:Factoid:HeadNode {label: l}) RETURN f.id AS id",
                                          labels=[f"Factoid {i}" for i in rng.sample(range(30000), 200)])]
    print(len(heads200), "heads in the batch", flush=True)

    if "seeds" in WHAT:
        print("\nReading the seeds (the entities written heads refer to)", flush=True)
        for size in (1, 200):
            ms, rows = await timed(lambda: q(SEEDS_QUERY, heads=heads200[:size]))
            refs = {i for r in rows for i in r["refs"]}
            line(f"seeds of {size} factoid head(s)", ms, f"{len(refs)} entities")
    rows = await q(SEEDS_QUERY, heads=heads200)
    seeds200 = sorted({i for r in rows for i in r["refs"]})
    one_head = sorted({i for i in rows[0]["refs"]})

    if "compiled" in WHAT:
        print("\nEvaluating with today's compiler (root first: every Person tested)", flush=True)
        for name, where in P.items():
            query, params = compiled(where)
            ms, resp = await timed(lambda: run(query, params))
            line(f"full   {name}", ms, f"{resp['count']} found")
            sq, sp = seeded(where)
            truth = {r["id"] for r in (await run(*compiled(where, 100)))["results"]} if resp["count"] <= 100 else None
            for label, seeds in (("1 head", one_head), ("200 heads", seeds200)):
                # (each pattern's own match, plus the seeds of the batch, so some seeds match)
                found = [r["id"] for r in (await run(query, params))["results"]][:3]
                s = sorted(set(seeds) | set(found))
                ms2, resp2 = await timed(lambda: run(sq, sp, seeds=s))
                ok = ""
                if truth is not None:
                    got = {r["id"] for r in resp2["results"]}
                    ok = "matches full" if got == truth & set(s) else f"MISMATCH {len(got)} vs {len(truth & set(s))}"
                line(f"seeded ({label}, {len(s)} seeds) {name[:2]}", ms2, f"{resp2['count']} found; {ok}")
        t = time.perf_counter()
        for _ in range(200):
            compiled(P["P3 local + date: received from X in year Y"])
        line("compiling one pattern in Python (check_match + build_search_query)", (time.perf_counter() - t) * 1000 / 200)

    ANCHOR_P1 = f"""
    UNWIND $anchors AS aid
    MATCH (x:PGIndexableNode {{id: aid}})
    WITH *
    MATCH (x)<-[:given_by]-(t)
    WITH *
    MATCH (t)-[:given_to]->(n)
    WHERE t:Transfer AND n:Person AND {WALK_UP.format(v='t')} AND {LISTED}
    RETURN aid, collect(DISTINCT n.id) AS found
    """
    ANCHOR_P2 = f"""
    UNWIND $anchors AS aid
    MATCH (x:PGIndexableNode {{id: aid}})
    WITH *
    MATCH (x)<-[:carried_out_by]-(a)
    WITH *
    MATCH (a)-[:participants]->(r)-[:target]->(n)
    WHERE a:Activity AND r:InRole AND n:Person AND {WALK_UP.format(v='a')} AND {LISTED}
    RETURN aid, collect(DISTINCT n.id) AS found
    """
    ANCHOR_P3 = f"""
    UNWIND $rows AS row
    MATCH (x:PGIndexableNode {{id: row.anchor}})
    WITH *
    MATCH (x)<-[:given_by]-(t)
    WITH *
    MATCH (t)-[:given_to]->(n)
    WITH *
    MATCH (t)-[:date]->(d)
    WHERE t:Transfer AND n:Person AND d.latest_fuzzy >= row.lo AND d.earliest_fuzzy <= row.hi AND {WALK_UP.format(v='t')} AND {LISTED}
    RETURN row.anchor AS aid, collect(DISTINCT n.id) AS found
    """
    if "anchor" in WHAT:
        print("\nEvaluating from the anchor (the entity the criteria name), prototype Cypher", flush=True)
        ms, r = await timed(lambda: q(ANCHOR_P1, anchors=[giver], see_unpublished=True))
        line("P1 from X", ms, f"{len(r[0]['found'])} found")
        truth = {x["id"] for x in (await run(*compiled(P['P1 local: received a transfer from X'], 100)))["results"]}
        line("   same as the compiler's full result?", 0, str(set(r[0]["found"]) == truth))
        ms, r = await timed(lambda: q(ANCHOR_P2, anchors=[carrier], see_unpublished=True))
        line("P2 from X (through InRole)", ms, f"{len(r[0]['found'])} found")
        ms, r = await timed(lambda: q(ANCHOR_P2, anchors=[hub["id"]], see_unpublished=True))
        line(f"P2 from the hub ({hub['n']} activities)", ms, f"{len(r[0]['found'])} found")
        ms, r = await timed(lambda: q(ANCHOR_P3, rows=[{"anchor": giver, "lo": lo, "hi": hi}], see_unpublished=True))
        line("P3 from X, with the date", ms, f"{len(r[0]['found'])} found")

    if "choose" in WHAT:
        print("\nChoosing the descriptions a batch affects (stand-in nodes PGBenchCriteria)", flush=True)
        people = [r["id"] for r in await q("MATCH (p:Person) RETURN p.id AS id")]
        batch_labels = sorted({l for r in rows for ls in r["part_labels"] for l in ls})
        ddl("CREATE INDEX ON :PGBenchCriteria")
        ddl("CREATE INDEX ON :PGBenchAnchor(id)")
        try:
            for n in (1_000, 10_000):
                await w("MATCH (c:PGBenchCriteria) DETACH DELETE c")
                await w("MATCH (a:PGBenchAnchor) DETACH DELETE a")
                descs = []
                for i in range(n):
                    reach = "far" if rng.random() < 0.05 else "local"
                    anchors = [] if rng.random() < 0.05 else [rng.choice(people)]
                    descs.append({"id": str(uuid.uuid4()), "depends_on": ["Person", rng.choice(["Transfer", "Activity"]), "Statement"],
                                  "reach": reach, "anchors": anchors, "candidates": rng.sample(people, rng.randint(0, 3))})
                for k in range(0, n, 2000):
                    await w("UNWIND $d AS d CREATE (:PGBenchCriteria {id: d.id, depends_on: d.depends_on, reach: d.reach, anchors: d.anchors, candidates: d.candidates})", d=descs[k:k + 2000])
                    await w("""UNWIND $d AS d MATCH (c:PGBenchCriteria {id: d.id})
                               FOREACH (a IN d.anchors + d.candidates | MERGE (x:PGBenchAnchor {id: a}) CREATE (x)-[:bench_names]->(c))""", d=descs[k:k + 2000])
                SCAN = """MATCH (c:PGBenchCriteria) WHERE any(l IN c.depends_on WHERE l IN $labels)
                          AND (c.reach = 'far' OR size(c.anchors) = 0 OR any(a IN c.anchors WHERE a IN $seeds) OR any(x IN c.candidates WHERE x IN $seeds))
                          RETURN count(c) AS chosen"""
                ms, r = await timed(lambda: q(SCAN, labels=batch_labels, seeds=seeds200))
                line(f"scan of {n} descriptions, lists on the node, {len(seeds200)} seeds", ms, f"{r[0]['chosen']} chosen")
                INDEXED = """UNWIND $seeds AS s MATCH (:PGBenchAnchor {id: s})-[:bench_names]->(c:PGBenchCriteria)
                             RETURN count(DISTINCT c) AS chosen"""
                ms, r = await timed(lambda: q(INDEXED, seeds=seeds200))
                line(f"index nodes of {n} descriptions (anchors + candidates), {len(seeds200)} seeds", ms, f"{r[0]['chosen']} chosen (+ far / unanchored by label)")
                FAR = "MATCH (c:PGBenchCriteria) WHERE c.reach = 'far' OR size(c.anchors) = 0 RETURN count(c) AS n"
                ms, r = await timed(lambda: q(FAR))
                line(f"   the far and unanchored ones of {n}", ms, f"{r[0]['n']}")
        finally:
            await w("MATCH (c:PGBenchCriteria) DETACH DELETE c")
            await w("MATCH (a:PGBenchAnchor) DETACH DELETE a")
            ddl("DROP INDEX ON :PGBenchCriteria")
            ddl("DROP INDEX ON :PGBenchAnchor(id)")

    if "batch" in WHAT:
        print("\nOne batch of 200 written factoids against 5,000 'received a transfer from X' descriptions", flush=True)
        all_givers = [r["id"] for r in await q("MATCH (p:Person)<-[:given_by]-(:Transfer) RETURN DISTINCT p.id AS id")]
        anchors5k = rng.sample(all_givers, 5000)
        seedset = set(seeds200)
        chosen = [a for a in anchors5k if a in seedset]
        # (and those with a current candidate among the seeds: about as many again, by the 'choose' numbers)
        print(f"  {len(chosen)} of 5,000 are anchored on an entity the batch names", flush=True)
        tmpl = P["P1 local: received a transfer from X"]

        def pattern_for(a):
            return {"$incoming": [{"type": "Transfer", "field": "given_to", "where": {"given_by": {"is": a}}}]}

        async def each_seeded():
            for a in chosen:
                sq, sp = seeded(pattern_for(a))
                await run(sq, sp, seeds=seeds200)
        ms, _ = await timed(each_seeded, n=3)
        line(f"compiled + seeded, one query per description ({len(chosen)})", ms)

        async def each_full():
            for a in chosen[:20]:
                query, params = compiled(pattern_for(a))
                await run(query, params)
        ms, _ = await timed(each_full, n=3)
        line(f"compiled full, one query per description (first 20 only)", ms, f"so about {ms / 20 * len(chosen):.0f} ms for all {len(chosen)}")

        async def each_anchor():
            for a in chosen:
                await q(ANCHOR_P1, anchors=[a], see_unpublished=True)
        ms, _ = await timed(each_anchor, n=3)
        line(f"from the anchor, one query per description ({len(chosen)})", ms)

        ms, r = await timed(lambda: q(ANCHOR_P1, anchors=chosen, see_unpublished=True), n=5)
        line(f"from the anchor, grouped: one query for all {len(chosen)} (UNWIND)", ms)
        ms, r = await timed(lambda: q(ANCHOR_P1, anchors=anchors5k, see_unpublished=True), n=3)
        line("from the anchor, grouped: all 5,000 (a rebuild of the shape)", ms, f"{sum(len(x['found']) for x in r)} candidates")


asyncio.run(main())
