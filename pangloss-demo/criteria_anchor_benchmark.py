"""Matches criteria, step 7: what an evaluation costs each way (`pangloss_criteria.evaluate`): root first (every
entity of the class tested), from an anchor (among what is around an entity the criteria name), seeded (among given
ids), and many of one shape at once. Each result from an anchor is compared with the root-first one. Reads only.
Run from a copy of the demo whose database is a scratch one (DATABASE in the environment), never the demo's own."""
import asyncio, random, statistics, sys, time

from pangloss_cli import load_project
from pangloss_models import initialise

RUNS = 7


async def timed(make, n=RUNS):
    await make()
    times = []
    for _ in range(n):
        t = time.perf_counter()
        await make()
        times.append((time.perf_counter() - t) * 1000)
    return statistics.median(times)


async def main():
    project = load_project()
    backend = project.require_database()
    project.import_models()
    initialise()
    await backend.connect()
    from pangloss_core import backend as be, settings as s
    from pangloss_criteria import SearchPattern
    from pangloss_criteria.evaluate import Counts, Job, evaluate, evaluate_many

    url = str(s.SETTINGS.DATABASE.DB_URL)
    print("database:", url)
    assert "7688" not in url
    db = be.current().database()

    @db.read_transaction
    async def q(tx, query, **p):
        return await (await tx.run(query, **p)).data()

    print("nodes:", (await q("MATCH (n) RETURN count(n) AS c"))[0]["c"], flush=True)
    givers = [r["id"] for r in await q(
        "MATCH (p:Person)<-[:given_by]-(:Transfer) WITH p, count(*) AS n WHERE n >= 2 RETURN p.id AS id LIMIT 5000")]
    carriers = [r["id"] for r in await q(
        "MATCH (p:Person)<-[:carried_out_by]-(a:Activity)-[:participants]->(:InRole) WITH p, count(DISTINCT a) AS n "
        "WHERE n >= 2 RETURN p.id AS id LIMIT 10")]
    hub = (await q("MATCH (p:Person)<-[e:carried_out_by]-() WITH p, count(e) AS n ORDER BY n DESC LIMIT 1 RETURN p.id AS id, n"))[0]
    giver, carrier = givers[0], carriers[0]
    transfer = lambda g: {"$incoming": [{"type": "Transfer", "field": "given_to", "where": {"given_by": {"is": g}}}]}
    witnessed = lambda c: {"$incoming": [{"type": "Activity", "field": "participants", "where": {"carried_out_by": {"is": c}}}]}
    P = {
        "P1 received a transfer from X": transfer(giver),
        "P2 witnessed an activity of X (InRole)": witnessed(carrier),
        f"P2 of the person with {hub['n']} activities": witnessed(hub["id"]),
        "P4 carried out a battle (no anchor)": {"$incoming": [{"type": "Activity", "field": "carried_out_by", "where": {"activity_type": {"eq": "battle"}}}]},
        "P5 received from someone who witnessed for X (far)": {"$incoming": [{"type": "Transfer", "field": "given_to", "where": {"given_by": {
            "type": "Person", "where": witnessed(carrier)["$incoming"] and {"$incoming": witnessed(carrier)["$incoming"]}}}}]},
    }
    pattern = lambda where: SearchPattern({"type": "Person", "where": where})

    print("\n--- one description, in full: root first, and as `evaluate_many` does it")
    for name, where in P.items():
        p = pattern(where)
        truth = await evaluate(p)
        root = await timed(lambda: evaluate(p), 3)
        counts = Counts()
        found = (await evaluate_many([Job("d", p, set())], counts=counts))["d"]
        assert (found.count, found.count_everyone, found.candidates) == (truth.count, truth.count_everyone, truth.candidates), name
        many = await timed(lambda: evaluate_many([Job("d", p, set())]), 3 if counts.root_first else RUNS)
        how = "from an anchor" if counts.anchored else "root first"
        print(f"  {name:<52} {root:8.1f} ms  {many:8.1f} ms  ({how}; {truth.count} found)", flush=True)

    rng = random.Random(7)
    print("\n--- many of one shape (received a transfer from X, an X each), in full")
    for n in (1, 116, 1000, 5000):
        chosen = rng.sample(givers, min(n, len(givers)))
        jobs = [Job(str(i), pattern(transfer(g)), set()) for i, g in enumerate(chosen)]
        ms = await timed(lambda: evaluate_many(jobs), 3)
        found = await evaluate_many(jobs)
        print(f"  {len(jobs):5} descriptions {ms:9.1f} ms   {sum(f.count for f in found.values())} candidates", flush=True)
    # (the same as one query each)
    chosen = rng.sample(givers, 116)
    async def one_each():
        for i, g in enumerate(chosen):
            await evaluate_many([Job(str(i), pattern(transfer(g)), set())])
    print(f"    116, a call each {await timed(one_each, 3):9.1f} ms", flush=True)

    print("\n--- seeded: among the entities a batch names")
    people = [r["id"] for r in await q("MATCH (p:Person) RETURN p.id AS id LIMIT 20000")]
    for seeds in (11, 1226):
        among = set(rng.sample(people, seeds))
        for n in (1, 116, 1000):
            jobs = [Job(str(i), pattern(transfer(g)), set(), among=among) for i, g in enumerate(rng.sample(givers, n))]
            ms = await timed(lambda: evaluate_many(jobs), 3)
            print(f"  {n:5} descriptions among {seeds:5} seeds {ms:9.1f} ms", flush=True)
        broad = [Job("b", pattern(P["P4 carried out a battle (no anchor)"]), set(), among=among)]
        print(f"      P4 (broad) among {seeds:5} seeds {await timed(lambda: evaluate_many(broad), 3):9.1f} ms", flush=True)
    await backend.disconnect()


asyncio.run(main())
