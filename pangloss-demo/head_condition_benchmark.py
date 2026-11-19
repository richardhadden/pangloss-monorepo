"""What the head condition of `pangloss-derived` costs in a search that leaves wrappers out (matches criteria, step 6):
`search.head_conditions` gives, for the head of each document a pattern passes, "not derived through an excluded
wrapper" (a test of the list `derived_context`). Each of the criteria of `criteria_benchmark.py` is evaluated as the
worker does (`operations.search_ids`, as everyone and as a logged-in reader) with the condition and without it.
Reads only. Run from a copy of the demo whose database is the scratch one (DATABASE in the environment), never the
demo's own."""
import asyncio, statistics, time

from pangloss_cli import load_project
from pangloss_models import Match, initialise
from pangloss_models import search as model_search

RUNS = 9
EXCLUDED = ["MatchesCriteria"]


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
    from pangloss_core import backend as be, settings as s, storage_of
    from pangloss_models import ModelRegistry

    print("database:", s.SETTINGS.DATABASE.DB_URL)
    assert "7690" in str(s.SETTINGS.DATABASE.DB_URL)
    Person = ModelRegistry.all_models()["Person"]
    db = be.current().database()

    @db.read_transaction
    async def q(tx, query, **p):
        return await (await tx.run(query, **p)).data()

    print("nodes:", (await q("MATCH (n) RETURN count(n) AS c"))[0]["c"])
    print("documents with derived_by:", (await q("MATCH (h:HeadNode) WHERE h.derived_by IS NOT NULL RETURN count(h) AS c"))[0]["c"],
          "; with a derived_context that is not empty:",
          (await q("MATCH (h:HeadNode) WHERE size(coalesce(h.derived_context, [])) > 0 RETURN count(h) AS c"))[0]["c"])
    giver = (await q("MATCH (p:Person)<-[:given_by]-(:Transfer) WITH p, count(*) AS n WHERE n >= 2 RETURN p.id AS id LIMIT 1"))[0]["id"]
    carrier = (await q("MATCH (p:Person)<-[:carried_out_by]-(a:Activity)-[:participants]->(:InRole) WITH p, count(DISTINCT a) AS n "
                       "WHERE n >= 2 RETURN p.id AS id LIMIT 1"))[0]["id"]
    hub = (await q("MATCH (p:Person)<-[e:carried_out_by]-() WITH p, count(e) AS n ORDER BY n DESC LIMIT 1 RETURN p.id AS id, n"))[0]
    P = {
        "P1 received a transfer from X": {"$incoming": [{"type": "Transfer", "field": "given_to", "where": {"given_by": {"is": giver}}}]},
        "P2 witnessed an activity of X (InRole)": {"$incoming": [{"type": "Activity", "field": "participants", "where": {"carried_out_by": {"is": carrier}}}]},
        f"P2 of the person with {hub['n']} activities": {"$incoming": [{"type": "Activity", "field": "participants", "where": {"carried_out_by": {"is": hub["id"]}}}]},
        "P4 carried out a battle (no anchor, broad)": {"$incoming": [{"type": "Activity", "field": "carried_out_by", "where": {"activity_type": {"eq": "battle"}}}]},
        "P5 received from someone who witnessed for X (far)": {"$incoming": [{"type": "Transfer", "field": "given_to", "where": {"given_by": {
            "type": "Person", "where": {"$incoming": [{"type": "Activity", "field": "participants", "where": {"carried_out_by": {"is": carrier}}}]}}}}]},
    }
    search_ids = storage_of().operations.search_ids
    given = list(model_search.head_conditions)
    print("head conditions installed:", [f.__name__ for f in given])
    assert given

    for reader, flag in (("logged in", True), ("everyone", False)):
        print(f"\n--- as {reader}: without the condition, with it")
        for name, where in P.items():
            match = Match(type="Person", where=where, exclude_wrappers=EXCLUDED)
            run = lambda: search_ids(Person, match, limit=50, see_unpublished=flag, without=[])
            rows = []
            for with_test in (False, True, False, True):
                model_search.head_conditions[:] = given if with_test else []
                ms = await timed(run, 5 if "P4" in name or "P5" in name else RUNS)
                rows.append((ms, (await run()).count))
            model_search.head_conditions[:] = given
            without = min(rows[0][0], rows[2][0])
            with_ = min(rows[1][0], rows[3][0])
            assert len({count for _, count in rows}) == 1, rows
            print(f"  {name:<52} {without:8.1f} ms  {with_:8.1f} ms  {100 * (with_ - without) / without:+6.1f}%   ({rows[0][1]} found)")
    await backend.disconnect()


asyncio.run(main())
