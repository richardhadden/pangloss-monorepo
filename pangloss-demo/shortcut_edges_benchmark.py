"""Measurements of shortcut edges (step 11 of implementation_docs/derived-edges-and-documents.md).

Run from a copy of this demo whose settings point at a scratch Memgraph holding the bulk-loaded data of
implementation_docs/large-data.md (2026-11-18: the container `pangloss-memgraph-identity` on :7690), never at the
demo's own database: **it writes and deletes derived edges and their shortcuts.**

    cp pangloss-demo/shortcut_edges_benchmark.py /tmp/d10/project/ && cd /tmp/d10/project
    BENCH_LABEL=after ../path/to/.venv/bin/python shortcut_edges_benchmark.py reads
    BENCH_SHORTCUT=1 ../path/to/.venv/bin/python shortcut_edges_benchmark.py sync paths
    BENCH_SHORTCUT=1 BENCH_LABEL=with ../path/to/.venv/bin/python shortcut_edges_benchmark.py reads
    BENCH_SHORTCUT=1 ../path/to/.venv/bin/python shortcut_edges_benchmark.py build      # then without, to compare
    ../path/to/.venv/bin/python shortcut_edges_benchmark.py sync                         # takes them away again

`reads` uses nothing of this step, so that it can be run with the code as it was before (PYTHONPATH of an older
checkout) to compare. `BENCH_SHORTCUT=1` makes the demo's two declared edges (`CoParticipants`, `GaveTo`) ask for
shortcuts, as `shortcut=True` in the models would.
"""
import asyncio, dataclasses, json, os, pathlib, statistics, subprocess, sys, time

from pangloss_cli import load_project
from pangloss_models import Match, initialise
from pangloss_users import current_request_username

WHAT = sys.argv[1:]
LABEL = os.environ.get("BENCH_LABEL", "run")
SHORTCUT = bool(os.environ.get("BENCH_SHORTCUT"))
CONTAINER = "pangloss-memgraph-identity"


def console(statement: str) -> str:
    done = subprocess.run(["docker", "exec", "-i", CONTAINER, "mgconsole", "--username", "test", "--password", "test",
                           "--output-format", "csv"], input=statement + ";\n", text=True, check=True, capture_output=True)
    return done.stdout


def memory() -> str:
    return next(l for l in console("SHOW STORAGE INFO").splitlines() if "memory_tracked" in l).split(",")[1].strip('"')


def say(label: str, value: str) -> None:
    print(f"  {label:<70} {value}", flush=True)


def median_ms(times: list[float]) -> float:
    return round(statistics.median(times) * 1000, 2)


async def timed(times: dict[str, float], label: str, calls: list) -> None:
    """The median of the calls (each a function that gives an awaitable), after one that is not counted"""
    await calls[0]()
    taken = []
    for call in calls:
        start = time.perf_counter()
        await call()
        taken.append(time.perf_counter() - start)
    times[label] = median_ms(taken)
    say(label, f"{times[label]} ms (n={len(taken)})")


async def main() -> None:
    project = load_project()
    backend = project.require_database()
    project.import_models()
    from demo_app import models as m

    if SHORTCUT:
        for model in (m.Activity, m.Transfer):
            model._derives = [dataclasses.replace(d, shortcut=True) for d in model._derives]
    initialise()
    from pangloss_core import storage_of
    from pangloss_derived.registry import DerivedRegistry
    from pangloss_derived.worker import database, worker
    from pangloss_models.autocomplete import search_everything

    current_request_username.set("loader")
    await backend.connect()
    db = database()
    operations = storage_of().operations

    @db.read_transaction
    async def read(tx, query, **params):
        return [dict(r) async for r in await tx.run(query, params)]

    # (the people with the most `CoParticipants` edges: those who have, or will have, the most shortcuts)
    busy = [r["id"] for r in await read(
        "MATCH (d:CoParticipants)-[:first]->(p:Person) WHERE p.merged_into IS NULL AND NOT coalesce(p.deleted, false) "
        "WITH p, count(d) AS n ORDER BY n DESC, p.id LIMIT 60 RETURN p.id AS id")]
    factoids = [r["id"] for r in await read(
        "MATCH (d:CoParticipants)<-[:justifies]-(:PGJustification)-[:evidence]->(f:Factoid) "
        "WITH DISTINCT f ORDER BY f.id LIMIT 40 RETURN f.id AS id")]

    if "reads" in WHAT:
        print(f"reads ({LABEL}; shortcut edges in the database: "
              f"{(await read('MATCH ()-[e]->() WHERE e.derived RETURN count(e) AS n'))[0]['n']})")
        times: dict[str, float] = {}
        await timed(times, "Person.get (the whole entity, with what refers to it)",
                    [lambda id=id: m.Person.get(id) for id in busy])
        await timed(times, "a person without what refers to it",
                    [lambda id=id: operations.get_entity_without_incoming(m.Person, id) for id in busy])
        await timed(times, "a person, the first 25 of each incoming field",
                    [lambda id=id: operations.get_entity_with_some(m.Person, id, 25) for id in busy])
        await timed(times, "Factoid.get", [lambda id=id: m.Factoid.get(id) for id in factoids])
        await timed(times, "whether a person can be deleted",
                    [lambda id=id: operations.check_deletable(m.Person, id) for id in busy])
        await timed(times, "Person.list, a page with use counts", [lambda: m.Person.list(use_counts=True)] * 10)
        await timed(times, "Factoid.list, a page", [lambda: m.Factoid.list()] * 10)
        await timed(times, "Person.autocomplete, nothing typed (the most used)",
                    [lambda: m.Person.autocomplete("")] * 5)
        await timed(times, "search of everything, a class and no words (the most connected)",
                    [lambda: search_everything("", [m.Person])] * 5)
        words = [(await m.Person.get(id)).label.split()[0] for id in busy[:10]]
        await timed(times, "search of everything, a word", [lambda w=w: search_everything(w) for w in words])
        await timed(times, "Person.autocomplete, a word", [lambda w=w: m.Person.autocomplete(w) for w in words])
        await timed(times, "Factoid.search, $mentions a person",
                    [lambda id=id: m.Factoid.search(Match(where={"$mentions": {"is": str(id)}})) for id in busy[:30]])
        await timed(times, "Person.merge_preview",
                    [lambda a=a, b=b: m.Person.merge_preview(absorb=a, into=b) for a, b in zip(busy[::2], busy[1::2])])
        edits = [await operations.get_entity_for_edit(m.Person, id) for id in busy[:30]]
        try:
            await timed(times, "an update of a person that changes nothing",
                        [lambda e=e: m.Person.Update(**e.model_dump()).save() for e in edits])
        except Exception as error:  # (not what is measured: said, and left out)
            say("an update of a person", f"not run: {type(error).__name__}: {str(error)[:120]}")
        pathlib.Path(f"shortcut_edges_benchmark.{LABEL}.json").write_text(json.dumps(times, indent=1))

    if "sync" in WHAT:
        from pangloss_derived import shortcuts

        print(f"sync (classes that ask: {sorted(shortcuts.classes())})")
        before = memory()
        start = time.perf_counter()
        done = await shortcuts.sync(db)
        say("shortcuts.sync", f"{time.perf_counter() - start:.2f} s: {json.dumps(done)}")
        say("memory of the database", f"{before} -> {memory()}")
        start = time.perf_counter()
        again = await shortcuts.sync(db)
        say("again, with nothing to do", f"{(time.perf_counter() - start) * 1000:.0f} ms: {json.dumps(again)}")

        @db.read_transaction
        async def count(tx):
            return await shortcuts.counts(tx)

        start = time.perf_counter()
        counted = await count()
        say("shortcuts.counts", f"{(time.perf_counter() - start) * 1000:.0f} ms: {json.dumps(counted)}")

    if "paths" in WHAT:
        print("paths (from each of 60 people; the count of people reached is the same both ways)")
        queries = {
            "one step, by the shortcuts":
                "MATCH (a:PGIndexableNode {id: $id})-[:CoParticipants]-(b) RETURN count(DISTINCT b) AS n",
            "one step, through the nodes":
                "MATCH (a:PGIndexableNode {id: $id})<-[:first|second]-(:CoParticipants)-[:first|second]->(b) "
                "WHERE b <> a RETURN count(DISTINCT b) AS n",
            "up to three steps, by the shortcuts":
                "MATCH (a:PGIndexableNode {id: $id})-[:CoParticipants *1..3]-(b) WHERE b <> a RETURN count(DISTINCT b) AS n",
            "up to three steps, through the nodes":
                "MATCH (a:PGIndexableNode {id: $id})<-[:first|second]-(:CoParticipants)-[:first|second]->(b1) WHERE b1 <> a "
                "WITH DISTINCT a, b1 "
                "OPTIONAL MATCH (b1)<-[:first|second]-(:CoParticipants)-[:first|second]->(b2) WHERE b2 <> b1 "
                "WITH DISTINCT a, b1, b2 "
                "OPTIONAL MATCH (b2)<-[:first|second]-(:CoParticipants)-[:first|second]->(b3) WHERE b3 <> b2 "
                "WITH a, collect(DISTINCT b1) + collect(DISTINCT b2) + collect(DISTINCT b3) AS reached "
                "UNWIND reached AS b WITH a, b WHERE b <> a RETURN count(DISTINCT b) AS n",
            "all shortest paths between two people (BFS), by the shortcuts":
                "MATCH p = (a:PGIndexableNode {id: $id})-[:CoParticipants *BFS ..6]-(b:PGIndexableNode {id: $other}) "
                "RETURN size(relationships(p)) AS n",
        }
        whole = {
            "every pair two steps apart, by the shortcuts":
                "MATCH (a:Person)-[:CoParticipants]-(b)-[:CoParticipants]-(c) WHERE a <> c RETURN count(*) AS n",
            "every pair two steps apart, through the nodes":
                "MATCH (a:Person)<-[:first|second]-(:CoParticipants)-[:first|second]->(b)"
                "<-[:first|second]-(:CoParticipants)-[:first|second]->(c) WHERE a <> c AND a <> b AND b <> c "
                "RETURN count(*) AS n",
            "every triangle, by the shortcuts":
                "MATCH (a:Person)-[:CoParticipants]-(b)-[:CoParticipants]-(c)-[:CoParticipants]-(a) "
                "RETURN count(*) AS n",
            "every triangle, through the nodes":
                "MATCH (a:Person)<-[:first|second]-(:CoParticipants)-[:first|second]->(b)"
                "<-[:first|second]-(:CoParticipants)-[:first|second]->(c)"
                "<-[:first|second]-(:CoParticipants)-[:first|second]->(a) "
                "WHERE a <> b AND b <> c AND a <> c RETURN count(*) AS n",
        }
        for label, query in whole.items():
            taken = []
            for _ in range(4):
                start = time.perf_counter()
                rows = await read(query)
                taken.append(time.perf_counter() - start)
            say(label, f"median {median_ms(taken[1:])} ms; {rows[0]['n']}")
        for label, query in queries.items():
            taken, counts = [], []
            for index, id in enumerate(busy):
                start = time.perf_counter()
                rows = await read(query, id=id, other=busy[(index + 7) % len(busy)])
                taken.append(time.perf_counter() - start)
                counts.append(rows[0]["n"] if rows else None)
            reached = [c for c in counts if c is not None]
            say(label, f"median {median_ms(taken)} ms, max {max(taken) * 1000:.0f} ms; "
                       f"reached: median {statistics.median(reached) if reached else '-'}, "
                       f"sum {sum(reached)}, found {len(reached)}")

    if "build" in WHAT:
        rule = DerivedRegistry.all_checked()["Activity__CoParticipants"]
        print(f"build (CoParticipants from nothing; shortcut={rule.model._meta.shortcut})")
        await worker.take_lease()
        try:
            start = time.perf_counter()
            removed = await worker.remove_justifications(rule.name, None)
            say("its justifications and edges deleted", f"{time.perf_counter() - start:.2f} s ({removed})")
            start = time.perf_counter()
            counts = await worker.rebuild(rule)
            say("built again", f"{time.perf_counter() - start:.2f} s: {json.dumps(counts, default=str)}")
            edges = (await read("MATCH (d:CoParticipants) RETURN count(d) AS n"))[0]["n"]
            there = (await read("MATCH ()-[e:CoParticipants]->() WHERE e.derived RETURN count(e) AS n"))[0]["n"]
            say("edges, and shortcuts", f"{edges}, {there}")
        finally:
            await worker.give_up_lease()

    await backend.disconnect()


asyncio.run(main())
