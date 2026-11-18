"""Measurements of derived documents (step 10 of implementation_docs/derived-edges-and-documents.md).

Run from a copy of this demo whose settings point at a scratch Memgraph holding the bulk-loaded data of
implementation_docs/large-data.md (2026-11-18: the container `pangloss-memgraph-identity` on :7690), never at the
demo's own database: **it writes tens of thousands of factoids and derived factoids, and does not remove them.**

    cp pangloss-demo/derived_documents_benchmark.py /tmp/d10/project/ && cd /tmp/d10/project
    ../path/to/.venv/bin/python derived_documents_benchmark.py build [live] [publish] [change] [fanout] [bigsource] [block] [search]

The stages use slices of the people that are there (by id), so each can be run once. `build` first: the others use
its families.
"""
import asyncio, json, os, pathlib, re, statistics, subprocess, sys, time

from pangloss_cli import load_project
from pangloss_models import initialise
from pangloss_users import current_request_username

WHAT = sys.argv[1:]
STATE = pathlib.Path("derived_documents_benchmark.json")
CONTAINER = "pangloss-memgraph-identity"
FAMILIES, CHILDREN = int(os.environ.get("BENCH_FAMILIES", 4000)), 3
# (a trial: a few families, of people far from those the stages use)
OFFSET = int(os.environ.get("BENCH_OFFSET", 0))


def console(statement: str) -> str:
    done = subprocess.run(["docker", "exec", "-i", CONTAINER, "mgconsole", "--username", "test", "--password", "test",
                           "--output-format", "csv"], input=statement + ";\n", text=True, check=True, capture_output=True)
    return done.stdout


def memory() -> str:
    return next(l for l in console("SHOW STORAGE INFO").splitlines() if "memory_tracked" in l).split(",")[1].strip('"')


def say(label: str, value: str) -> None:
    print(f"  {label:<74} {value}", flush=True)


def ms(times: list[float]) -> str:
    times = sorted(times)
    return (f"median {statistics.median(times) * 1000:.1f} ms, p95 {times[int(len(times) * 0.95) - 1] * 1000:.1f} ms, "
            f"max {times[-1] * 1000:.0f} ms (n={len(times)})")


async def main() -> None:
    project = load_project()
    backend = project.require_database()
    project.import_models()
    initialise()
    from demo_app import models as m
    from pangloss_derived import store, written
    from pangloss_derived.registry import DerivedRegistry
    from pangloss_derived.worker import database, pending_status, worker
    from pangloss_models.autocomplete import search_everything
    from pangloss_review import ReviewStatus, service

    current_request_username.set("loader")
    await backend.connect()
    db = database()
    rule = DerivedRegistry.all_checked()["siblings"]

    @db.read_transaction
    async def read(tx, query, **params):
        return [dict(r) async for r in await tx.run(query, params)]

    @db.write_transaction
    async def write(tx, query, **params):
        return [dict(r) async for r in await tx.run(query, params)]

    people = [r["id"] for r in await read("MATCH (p:Person:HeadNode) WHERE p.merged_into IS NULL AND NOT coalesce(p.deleted, false) "
                                         "RETURN p.id AS id ORDER BY p.id")]
    sources = [r["id"] for r in await read("MATCH (z:ZoteroObject:HeadNode) RETURN z.id AS id ORDER BY z.id LIMIT 50")]
    state = json.loads(STATE.read_text()) if STATE.exists() else {}

    def person(i: int) -> dict:
        return {"type": "Person", "id": people[i + OFFSET]}

    def child_of(child: int, parent: int) -> dict:
        return {"type": "ChildOf", "label": f"{child} child of {parent}", "child": person(child), "parent": person(parent), "places": []}

    def factoid(statements: list[dict], n: int):
        return m.Factoid.Create(label=f"Bench {n}", statements=statements,
                                source={"type": "AtPage", "page": str(n), "target": [{"type": "ZoteroObject", "id": sources[n % len(sources)]}]})

    async def save_all(creates: list, writers: int = 8) -> tuple[list[str], list[float]]:
        """Saved by several writers at once. Gives the ids, in the order given, and the time of each save"""
        ids: list = [None] * len(creates)
        times: list[float] = []
        todo = iter(range(len(creates)))

        async def writer() -> None:
            current_request_username.set("loader")
            for i in todo:
                began = time.perf_counter()
                ids[i] = str((await creates[i].save()).id)
                times.append(time.perf_counter() - began)

        await asyncio.gather(*(writer() for _ in range(writers)))
        return ids, times

    async def counts() -> dict:
        (row,) = await read("MATCH (d:DerivedFactoid:HeadNode) RETURN count(d) AS all, "
                            "sum(CASE WHEN coalesce(d.deleted, false) THEN 1 ELSE 0 END) AS deleted, "
                            "sum(CASE WHEN coalesce(d.published, true) THEN 1 ELSE 0 END) AS published")
        (nodes,) = await read("MATCH (n) RETURN count(n) AS nodes")
        return {**row, **nodes}

    async def drain(label: str) -> float:
        """The worker does all there is. Says what it did and how long it took"""
        before = worker.stats
        worker.stats = type(before)()
        await worker.take_lease()
        began = time.perf_counter()
        try:
            await worker.drain()
        finally:
            await worker.give_up_lease()
        took = time.perf_counter() - began
        s, d = worker.stats, worker.stats.documents
        say(label, f"{took:.1f} s: {s.heads} heads, {s.rows} rows; finding {s.seconds_finding:.1f} s, justifications "
                   f"{s.seconds_writing:.1f} s, documents {s.seconds_documents:.1f} s")
        looked = d.made + d.changed + d.deleted + d.undeleted + d.published + d.unpublished + d.same
        say("  documents", f"made {d.made}, changed {d.changed}, deleted {d.deleted}, published {d.published}, same {d.same}, "
                           f"left out {d.left_out}, failed {d.failed}"
                           + (f": {looked / s.seconds_documents:.0f} a second, {s.seconds_documents / looked * 1000:.1f} ms each" if looked and s.seconds_documents else ""))
        worker.stats = before
        return took

    print(f"{len(people)} people; {await counts()}; memory {memory()}")

    if "build" in WHAT:
        print("A first build")
        creates = [factoid([child_of(FAMILIES + f * CHILDREN + c, f)], f * CHILDREN + c) for f in range(FAMILIES) for c in range(CHILDREN)]
        began = time.perf_counter()
        ids, times = await save_all(creates)
        say(f"{len(ids)} factoids of one ChildOf saved by 8 writers", f"{time.perf_counter() - began:.0f} s; a save {ms(times)}")
        state["build"] = ids
        STATE.write_text(json.dumps(state))
        # (as after a bulk load: nothing is pending, and the rule has never been built)
        await write("MATCH (p:PGPending) WHERE p.kind STARTS WITH 'derive' DETACH DELETE p")
        before, memory_before = await counts(), memory()
        await worker.take_lease()
        began = time.perf_counter()
        built = await worker.rebuild(rule)
        await worker.give_up_lease()
        say("rebuild of `siblings` (the justifications)", f"{time.perf_counter() - began:.1f} s: {built}")
        await drain("the documents written")
        after = await counts()
        say("made", f"{after['all'] - before['all']} documents, {after['nodes'] - before['nodes']} nodes; memory {memory_before} -> {memory()}")
        await worker.take_lease()
        began = time.perf_counter()
        built = await worker.rebuild(rule)
        await worker.give_up_lease()
        say("a second rebuild", f"{time.perf_counter() - began:.1f} s: {built}")
        await drain("and its documents")
        again = await counts()
        say("changed by the second rebuild", f"{again['nodes'] - after['nodes']} nodes, {again['all'] - after['all']} documents")

    if "live" in WHAT:
        print("Writers and the worker at once")
        base_parent, base_child, families = 16000, 16500, 500
        creates = [factoid([child_of(base_child + f * 3 + c, base_parent + f)], 100000 + f * 3 + c) for f in range(families) for c in range(3)]
        lags: list[float] = []
        saves: list[float] = []
        todo = iter(range(families))

        async def family_writer() -> None:
            current_request_username.set("loader")
            for f in todo:
                for c in range(3):
                    began = time.perf_counter()
                    last = str((await creates[f * 3 + c].save()).id)
                    saves.append(time.perf_counter() - began)
                saved = time.perf_counter()
                if f % 5:
                    continue
                # (the third factoid of the family is a source of two documents)
                while True:
                    (row,) = await read("MATCH (c:PGUnprotectedCitation {target_head_id: $id}) RETURN count(c) AS n", id=last)
                    if row["n"] >= 2:
                        lags.append(time.perf_counter() - saved)
                        break
                    if time.perf_counter() - saved > 120:
                        lags.append(120.0)
                        break
                    await asyncio.sleep(0.02)

        most = 0

        async def watch() -> None:
            nonlocal most
            while True:
                status = await pending_status()
                most = max(most, status["pending"]["pending"] + status["documents"]["pending"] + status["retractions"]["pending"])
                await asyncio.sleep(0.25)

        before = await counts()
        running, watching = asyncio.create_task(worker.run()), asyncio.create_task(watch())
        began = time.perf_counter()
        await asyncio.gather(*(family_writer() for _ in range(4)))
        wrote = time.perf_counter() - began
        while (await counts())["all"] - before["all"] < families * 3:
            await asyncio.sleep(0.1)
            if time.perf_counter() - began > 900:
                break
        took = time.perf_counter() - began
        running.cancel(), watching.cancel()
        await asyncio.gather(running, watching, return_exceptions=True)
        say(f"{families * 3} factoids by 4 writers, the worker running", f"written in {wrote:.1f} s; a save {ms(saves)}")
        say("all their documents there after", f"{took:.1f} s ({(await counts())['all'] - before['all']} documents); most pending at once {most}")
        say("from the save of a family's last factoid to its two documents", ms(lags))
        # (the same saves with no worker)
        creates = [factoid([child_of(18500 + i, 18400 + i // 3)], 200000 + i) for i in range(300)]
        _, alone = await save_all(creates, writers=4)
        say("a save by 4 writers with no worker running", ms(alone))
        await drain("(those drained)")

    if "publish" in WHAT:
        print("Sources published, changed, deleted")
        ids = state["build"]
        began = time.perf_counter()
        for id in ids[: 300 * 3]:
            await service.set_status(id, ReviewStatus.PUBLISHED, "loader")
        say("900 factoids (300 families) published", f"{time.perf_counter() - began:.1f} s")
        await drain("their documents published")

    if "change" in WHAT:
        ids = state["build"]
        times = []
        for f in range(300, 600):
            view = await m.Factoid.get(ids[f * 3])
            statement = view.statements[0]
            began = time.perf_counter()
            # (another child, the statement the node it was: both documents of this child are others now)
            await m.Factoid.Update(id=view.id, label=view.label, source=json.loads(view.source.model_dump_json()),
                                   statements=[{**child_of(19000 + f, f), "id": statement.id}]).save()
            times.append(time.perf_counter() - began)
        say("300 factoids given another child", ms(times))
        await drain("their documents")
        began = time.perf_counter()
        for f in range(600, 900):
            await m.Factoid.delete(ids[f * 3])
        say("300 factoids deleted", f"{time.perf_counter() - began:.1f} s")
        await drain("their documents")

    if "fanout" in WHAT:
        print("One parent, more and more children")
        parent, first = 20000, 20001
        steps = []
        for n in range(0, 200, 20):
            creates = [factoid([child_of(first + i, parent)], 300000 + i) for i in range(n, n + 20)]
            ids, times = await save_all(creates, writers=4)
            took = await drain(f"children {n + 1} to {n + 20} ({(n + 20) * (n + 19) // 2 - n * (n - 1) // 2} new pairs)")
            steps.append(took)
        (one,), times = await save_all([factoid([child_of(first + 200, parent)], 300200)], writers=1)
        say("one more child: the save", ms(times))
        await drain("its 200 documents")
        state["fanout"] = {"parent": people[parent], "child": people[first], "last": one}
        STATE.write_text(json.dumps(state))

    if "search" in WHAT:
        print("The search of everything, and a person's page")
        child, plain = state["fanout"]["child"], people[30000]
        for what, id in (("a child among 201 (200 derived factoids name them)", child), ("a person in no derived factoid", plain)):
            (row,) = await read("MATCH (p:Person {id: $id}) RETURN p.label AS label", id=id)
            times, found = [], None
            for _ in range(8):
                began = time.perf_counter()
                found = await search_everything(row["label"], page_size=25)
                times.append(time.perf_counter() - began)
            say(f"search of everything for the label of {what}", f"{ms(times[1:])}; {found.count} results")
            times = []
            for _ in range(8):
                began = time.perf_counter()
                await m.Person.get(id)
                times.append(time.perf_counter() - began)
            say("  that person read", ms(times[1:]))

    if "bigsource" in WHAT:
        print("One factoid that thousands of derived factoids rest on")
        n = 60
        big = factoid([child_of(21001 + i, 21000) for i in range(n)], 400000)
        control = factoid([child_of(21100 + i, 21200 + i) for i in range(n)], 400001)
        (big_id, control_id), times = await save_all([big, control], writers=1)
        say(f"created: {n} statements of one parent; {n} of {n} parents", f"{times[0] * 1000:.0f} ms; {times[1] * 1000:.0f} ms")
        await drain(f"the {n * (n - 1) // 2} documents of the first")

        async def update(id: str, round: int) -> float:
            view = await m.Factoid.get(id)
            statements = [{"type": "ChildOf", "id": s.id, "label": s.label, "text": f"round {round}",
                           "child": {"type": "Person", "id": s.child[0].id if isinstance(s.child, list) else s.child.id},
                           "parent": {"type": "Person", "id": s.parent[0].id if isinstance(s.parent, list) else s.parent.id},
                           "places": []} for s in view.statements]
            update = m.Factoid.Update(id=view.id, label=view.label, source=json.loads(view.source.model_dump_json()), statements=statements)
            began = time.perf_counter()
            await update.save()
            return time.perf_counter() - began

        for what, id in (("the factoid with 1,770 derived factoids", big_id), ("the one with none", control_id)):
            times = [await update(id, r) for r in range(8)]
            say(f"an update of {what} (a text changed in each statement)", ms(times[1:]))
        await drain("the worker after those updates")
        began = time.perf_counter()
        await m.Factoid.delete(big_id)
        say("deleting it", f"{(time.perf_counter() - began) * 1000:.0f} ms")
        await drain("its documents deleted")

    if "block" in WHAT:
        print("`block=[DerivedFactoid]`: the rule's query with and without the test of the head's class")
        ids = [r["id"] for r in await read("MATCH (c:ChildOf) RETURN c.id AS id")]
        for seed in rule.seeds:
            query, params = store.query_of(rule, seed.node)
            without = re.sub(r"\n\s*AND NOT hd_\w+:`?DerivedFactoid`?", "", query)
            assert without != query
            for what, text in (("with", query), ("without", without), ("with", query), ("without", without)):
                began, rows = time.perf_counter(), 0
                for start in range(0, len(ids), 500):
                    rows += len(await read(text, **params, seeds=ids[start : start + 500]))
                say(f"seeded at {seed.node}, {len(ids)} seeds, {what}", f"{time.perf_counter() - began:.2f} s, {rows} rows")

    print(f"{await counts()}; memory {memory()}")
    status = await pending_status()
    print({k: status[k] for k in ("pending", "documents", "retractions", "written")})
    await backend.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
