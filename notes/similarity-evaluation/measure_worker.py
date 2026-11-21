"""Step 5.3's measurements (implementation_docs/similarity-build-plan.md): what keeping vectors current costs.

Run from the directory of a project whose settings point at a **scratch** database with `pangloss_vectors` and
`pangloss_fastrp` installed and a rebuild done (a copy of the demo: notes/similarity-evaluation/README.md):

    cd /tmp/similar-demo && /path/to/.venv/bin/python /path/to/notes/similarity-evaluation/measure_worker.py

**It writes**: a few hundred `Factoid`s of one `ChildOf` each, naming two people and a source taken at random. It prints:

A. what the mark costs a small write (the same saves with and without the kind `vectors`, in turns);
B. one turn of the worker for one write (the whole turn; inside it, the writing of the vectors in place, which is
   where the vector index is paid for), and one turn for a batch;
C. with four writers at once and the worker running as it does in the server: how long a write waits for its
   vectors.
"""

import asyncio
import random
import statistics
import time

from pangloss_cli import load_project
from pangloss_models import initialise

EACH = 40  # (saves in a turn of A; five turns each way)
SINGLE = 40  # (writes worked one at a time in B)
WRITERS, WRITES = 4, 50  # (C)


def spread(values, unit="ms", scale=1000.0):
    values = sorted(v * scale for v in values)
    at = lambda q: values[min(len(values) - 1, int(q * len(values)))]  # noqa: E731
    return f"median {at(0.5):.1f}, 90% {at(0.9):.1f}, most {values[-1]:.1f} {unit} (of {len(values)})"


async def main():
    project = load_project()
    backend = project.require_database()
    project.import_models()
    initialise()
    await backend.connect()
    # (what is written is recorded as written by this user, who must be there)
    from pangloss_users import current_request_username

    current_request_username.set("loader")

    import pangloss_vectors
    from pangloss_models import ModelRegistry
    from pangloss_vectors import store
    from pangloss_vectors import worker as worker_module
    from pangloss_vectors.status import status
    from pangloss_vectors.worker import pending_status, run_pending, worker

    found = await status()
    if found.rebuild_due:
        raise SystemExit("a rebuild is due: the worker would skip the parts. Rebuild first")
    for part in found.parts:
        print(f"part {part.part}: {part.count:,} vectors, {part.stale} stale")
    Factoid = ModelRegistry._model_dict["Factoid"]
    from pangloss_core import backend as core_backend

    database = core_backend.current().database()

    @database.read_transaction
    async def people(tx):
        result = await tx.run(
            "MATCH (p:Person:HeadNode) WHERE p.merged_into IS NULL AND coalesce(p.deleted, false) = false "
            "RETURN p.id AS id, p.type AS type LIMIT 60000"
        )
        return [(r["id"], r["type"]) async for r in result]

    @database.read_transaction
    async def backed(tx):
        result = await tx.run("MATCH (s:ZoteroBacked:HeadNode) RETURN s.id AS id, s.type AS type LIMIT 2000")
        return [(r["id"], r["type"]) async for r in result]

    sources = await backed()
    print(f"{len(sources):,} sources to cite")
    everyone = await people()
    chooser = random.Random(5)
    print(f"{len(everyone):,} people to name")
    counter = iter(range(10**9))

    async def save():
        (child, child_type), (parent, parent_type) = chooser.sample(everyone, 2)
        source_id, source_type = chooser.choice(sources)
        began = time.perf_counter()
        await Factoid.Create(
            label=f"measured {next(counter)}",
            source={"type": "AtPage", "page": "1", "target": [{"type": source_type, "id": source_id}]},
            statements=[
                {
                    "type": "ChildOf",
                    "label": "a child of someone",
                    "text": "A child of someone, for a measurement",
                    "child": {"type": child_type, "id": child},
                    "parent": {"type": parent_type, "id": parent},
                    "places": [],
                }
            ],
        ).save()
        return time.perf_counter() - began

    left = (await pending_status())["pending"]
    if left:
        print(f"{left} heads were pending: worked first, {await run_pending()} done")

    # A. the mark
    print("\nA. a small write (a factoid of one ChildOf naming two people), with and without the mark of the kind vectors")
    installed = pangloss_vectors.installed
    with_mark, without = [], []
    for _ in range(3):  # (warm)
        await save()
    for _ in range(5):
        with_mark += [await save() for _ in range(EACH)]
        before = (await pending_status())["pending"]
        pangloss_vectors.installed = lambda settings=None: False
        try:
            without += [await save() for _ in range(EACH)]
        finally:
            pangloss_vectors.installed = installed
        if (await pending_status())["pending"] != before:
            raise SystemExit("the saves without the mark left marks: the switch does not work")
    print("  with the mark:   ", spread(with_mark))
    print("  without the mark:", spread(without))
    marked = (await pending_status())["pending"]

    # B. the worker's turn
    writing = []
    set_vectors = store.set_vectors
    rows_written = []

    async def timed_set_vectors(part, rows, *args, **kwargs):
        rows = list(rows)
        began = time.perf_counter()
        try:
            return await set_vectors(part, rows, *args, **kwargs)
        finally:
            writing.append(time.perf_counter() - began)
            rows_written.append(len(rows))

    store.set_vectors = timed_set_vectors
    print(f"\nB. the worker: one turn for the {marked} heads A left (a batch is {worker.settings.batch})")
    began = time.perf_counter()
    done = await run_pending()
    took = time.perf_counter() - began
    print(f"  {done} heads in {took:.2f} s ({1000 * took / max(done, 1):.1f} ms a head); writing the vectors in place "
          f"{sum(writing):.2f} s of it, {sum(rows_written):,} vectors")
    state = await status()
    print("  stale now:", ", ".join(f"{p.part} {p.stale}" for p in state.parts))

    print(f"  then {SINGLE} writes, each worked alone")
    turns, writes, counts = [], [], []
    for _ in range(SINGLE):
        await save()
        writing.clear()
        rows_written.clear()
        began = time.perf_counter()
        await run_pending()
        turns.append(time.perf_counter() - began)
        writes.append(sum(writing))
        counts.append(sum(rows_written))
    print("  a turn:                      ", spread(turns))
    print("  of it, writing the vectors:  ", spread(writes))
    print("  vectors written in a turn:   ", spread(counts, unit="", scale=1))
    per_vector = [w / c for w, c in zip(writes, counts, strict=True) if c]
    print("  writing, for each vector:    ", spread(per_vector))
    state = await status()
    print("  stale now:", ", ".join(f"{p.part} {p.stale}" for p in state.parts))
    store.set_vectors = set_vectors

    # C. four writers, the worker running
    print(f"\nC. {WRITERS} writers of {WRITES} writes each, the worker running in this process as in the server")
    running = asyncio.create_task(worker.run())
    await asyncio.sleep(0.5)
    saved_at, save_took = [], []
    zero = time.perf_counter()

    async def writer():
        for _ in range(WRITES):
            save_took.append(await save())
            saved_at.append(time.perf_counter() - zero)

    samples = []  # (seconds, pending)

    async def watch(stop):
        while not stop.is_set():
            samples.append((time.perf_counter() - zero, (await pending_status())["pending"]))
            await asyncio.sleep(0.05)

    stop = asyncio.Event()
    watching = asyncio.create_task(watch(stop))
    await asyncio.gather(*(writer() for _ in range(WRITERS)))
    written = time.perf_counter() - zero
    while (await pending_status())["pending"]:
        await asyncio.sleep(0.05)
    caught_up = time.perf_counter() - zero
    stop.set()
    await watching
    running.cancel()
    await asyncio.gather(running, return_exceptions=True)
    await worker_module.worker.give_up_lease()
    saved_at.sort()
    # (in the order written: the i-th write has its vectors when the count done reaches i)
    lags = []
    at = 0
    for index, moment in enumerate(saved_at, start=1):
        while at < len(samples):
            when, pending = samples[at]
            written_by_then = sum(1 for s in saved_at if s <= when)
            if written_by_then - pending >= index:
                break
            at += 1
        lags.append((samples[at][0] if at < len(samples) else caught_up) - moment)
    print(f"  the writes: {len(saved_at)} in {written:.2f} s ({len(saved_at) / written:.0f} a second); a save",
          spread(save_took))
    print(f"  the worker had caught up {caught_up - written:.2f} s after the last write; "
          f"most pending at once {max(p for _, p in samples)}")
    print("  a write waited for its vectors:", spread(lags, unit="s", scale=1))
    state = await status()
    print("  stale now:", ", ".join(f"{p.part} {p.stale}" for p in state.parts))
    print(f"  (a save alone, from A: median {1000 * statistics.median(with_mark):.1f} ms)")
    close = getattr(backend, "close", None)
    if close is not None:
        await close()


asyncio.run(main())
