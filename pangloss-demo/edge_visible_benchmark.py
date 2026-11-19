"""What `fragments.edge_visible` costs where a read follows an edge that may be computed: the document read, what
refers to an entity, and a structured search. Each is timed with the test in the query (as when a model has a
computed relation) and without it (as before). Reads only. Run from a copy of the demo whose database is the scratch
one (DATABASE in the environment), never the demo's own."""
import asyncio, os, statistics, sys, time

from pangloss_cli import load_project
from pangloss_models import Match, initialise
from pangloss_models import computed
from pangloss_users import see_unpublished

RUNS = 9


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
    from pangloss_core import settings as s
    print("database:", s.SETTINGS.DATABASE.DB_URL)
    assert "7690" in str(s.SETTINGS.DATABASE.DB_URL)
    models = __import__("pangloss_models").ModelRegistry.all_models()
    Factoid, Person, Activity = models["Factoid"], models["Person"], models["Activity"]
    db = __import__("pangloss_core").backend.current().database()

    @db.read_transaction
    async def pick(tx):
        r = await tx.run("MATCH (f:Factoid:HeadNode) RETURN f.id AS id LIMIT 200")
        factoids = [x["id"] async for x in r]
        r = await tx.run("MATCH (p:Person)-[e]->() WITH p, count(e) AS n ORDER BY n DESC LIMIT 3 RETURN p.id AS id, n")
        busy = [(x["id"], x["n"]) async for x in r]
        r = await tx.run("MATCH (p:Person)-[e]->() WITH p, count(e) AS n WHERE n > 5 AND n < 40 RETURN p.id AS id, n LIMIT 50")
        ordinary = [(x["id"], x["n"]) async for x in r]
        r = await tx.run("MATCH (n) RETURN count(n) AS n")
        total = (await r.single())["n"]
        return factoids, busy, ordinary, total

    factoids, busy, ordinary, total = await pick()
    print("nodes:", total, "busy people:", busy)

    async def read_factoids():
        for id in factoids[:50]:
            await Factoid.get(id)

    async def read_person(id):
        await Person.get(id)

    async def read_people():
        for id, _ in ordinary[:25]:
            await Person.get(id)

    target = ordinary[0][0]
    searches = {
        "activities carried out by one person (through wrappers)": lambda: Activity.search(
            Match(where={"carried_out_by": {"is": str(target)}})),
        "factoids that mention one person": lambda: Factoid.search(
            Match(where={"$mentions": {"is": str(target)}})),
        "people referred to by an activity of a busy person's witness": lambda: Person.search(
            Match(where={"$incoming": [{"type": "Activity", "where": {"carried_out_by": {"is": str(busy[0][0])}}}]}), page_size=10),
        "activities with anyone carrying them out (exists)": lambda: Activity.search(
            Match(where={"carried_out_by": {"exists": True}}), page_size=10),
    }

    for reader, flag in (("logged in", True), ("not logged in", False)):
        token = see_unpublished.set(flag)
        print(f"\n--- reader: {reader}")
        rows = []
        for with_test in (False, True):
            computed._any["relations"] = with_test
            computed._any["fields"] = with_test
            row = [
                await timed(read_factoids),
                await timed(lambda: read_person(busy[0][0]), 5),
                await timed(read_people),
            ]
            for make in searches.values():
                row.append(await timed(make, 5))
            rows.append(row)
        names = ["50 factoids read", f"a person with {busy[0][1]} edges read", "25 people read", *searches]
        for name, without, with_ in zip(names, *rows):
            print(f"  {name:<62} {without:9.1f} ms  {with_:9.1f} ms  {100 * (with_ - without) / without:+6.1f}%")
        see_unpublished.reset(token)
    computed.clear()
    await backend.disconnect()


asyncio.run(main())
