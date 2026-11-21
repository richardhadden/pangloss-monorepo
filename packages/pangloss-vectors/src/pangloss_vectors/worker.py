"""The worker that keeps the vectors in use current after writes, in the background (implementation_docs/vectors.md,
"Keeping vectors current").

A write of a head of a class that has vectors leaves it pending (`pangloss_cypher.pending`, kind `vectors`), in the
write's own transaction; an update's mark keeps what the old tree named (`before_refs`: the entities it referred to,
and the documents nested in it, which the update replaced by new ones with new ids). The worker, in a loop:

1. **claims** a batch of pending heads, unless a rebuild holds its lease (below);
2. **reads** what the heads are now (whether each is there, its class, deleted, merged into another) and what their
   marks keep of before;
3. tells each registered part that is `local` and has been built what changed (`Changed`: the heads that are there,
   as written; the rest as removed; what they named before), and the part writes what it changes through `write`
   (`store.set_vectors`, in the generation in use, with the profiles that weigh it). A part never built is skipped,
   and so is one whose profiles' vectors in use are of another dimension than today's (a rebuild is due);
4. deletes every vector, of every part, of what is gone: the heads removed, the documents nested in them, and the ids
   the marks kept of before that are no longer nodes (`store.delete_for`);
5. completes the claims, and adds what the parts left stale to their state's `stale`, in one transaction. On any
   failure the claims are given back, to be tried again, and the error raised.

**One worker at a time** works on a database (a lease on the `PGVectorsWorker` node, as `pangloss-criteria`'s): two
would write vectors computed from reads of different moments, in any order.

**The worker and a rebuild** (`rebuild.py`) never overlap. Both take the backend's lock of the rebuild
(`rebuild.LOCK_KEY`) in the transaction that starts them, so one of them goes first:

- a batch is claimed only if no rebuild holds its lease; claiming marks the worker's node with the batch
  (`batch_until`), which the worker renews in the background while it works and takes off when it is done;
- a rebuild takes its lease, and then waits until no batch is marked, or the mark has run out (a worker that
  stopped), which it then takes off, so that the worker, at its next renewal, finds it has lost the batch and stops
  before it writes more.

So marks made while a rebuild runs wait, and are worked after its switch, against the new generation.

**Past a part's cap** (`FASTRP_REFRESH_CAP` of the graph part) a part writes approximate vectors and says how many are
stale; with `VECTORS_REBUILD_AFTER` set, the worker starts a rebuild of a part whose stale vectors are more than that
(the admin job `vectors_rebuild` if `pangloss_admin` is installed, or else the rebuild itself, in the worker).
"""

import asyncio
import contextlib
import dataclasses
import logging
import time
import uuid
from collections.abc import AsyncGenerator, Iterable
from typing import Any

from pangloss_core import Transaction, backend
from pangloss_cypher import fragments, pending
from pangloss_models import hooks

from pangloss_vectors import KIND, pending_work_of, store
from pangloss_vectors.parts import Changed, Item, Part, VectorRow, parts
from pangloss_vectors.rebuild import LEASE as REBUILD_LEASE
from pangloss_vectors.rebuild import LOCK_KEY, WORKER
from pangloss_vectors.settings import rebuild_after
from pangloss_vectors.status import unavailable

logger = logging.getLogger("pangloss.vectors.worker")

LEASE_LABEL = WORKER


@dataclasses.dataclass
class Settings:
    batch: int = 200
    """Heads claimed at once"""
    lease: float = 30.0
    """Seconds a claim (the worker's lease, and its mark of a batch) holds, unless renewed"""
    idle: float = 10.0
    """Seconds between looks for work when nothing wakes it"""
    paused: float = 1.0
    """Seconds between looks while a rebuild holds its lease"""


@dataclasses.dataclass
class Stats:
    batches: int = 0
    heads: int = 0
    written: int = 0
    """Vectors written by the parts"""
    stale: int = 0
    """Of those, or left out of date, the ones the parts said are stale"""
    deleted: int = 0
    """Vector nodes deleted, of what is gone"""
    skipped: dict[str, str] = dataclasses.field(default_factory=dict)
    """The parts skipped in the last batch, and why"""
    paused: int = 0
    """Turns that claimed nothing because a rebuild held its lease"""
    rebuilds: int = 0
    """Rebuilds started because a part had more stale vectors than `VECTORS_REBUILD_AFTER`"""
    failures: int = 0
    last_batch_at: float | None = None


class BatchLost(Exception):
    """The worker's mark of its batch ran out and was taken off (a rebuild went ahead): the batch stops, its claims
    given back"""


def database() -> Any:
    return backend.current().database()


# What each claimed head is now
HEADS_QUERY = f"""
UNWIND $ids AS id
MATCH (head:HeadNode {{id: id}})
RETURN head.id AS id, head.type AS type, {fragments.deleted("head")} AS deleted, head.merged_into AS merged_into
"""

# What is nested in these heads (a deleted head keeps its nodes)
BELOW_QUERY = """
UNWIND $ids AS id
MATCH (n:PGIndexableNode {head_node_id: id})
RETURN n.id AS id
"""

# Which of these ids are nodes
THERE_QUERY = """
UNWIND $ids AS id
MATCH (n:PGIndexableNode {id: id})
RETURN n.id AS id
"""

REBUILD_HELD_QUERY = f"""
MATCH (l:{REBUILD_LEASE} {{key: 'rebuild'}})
RETURN l.holder AS holder, l.until AS until
"""

MARK_BATCH_QUERY = f"""
MERGE (w:{LEASE_LABEL} {{kind: $kind}})
SET w.batch = $me, w.batch_until = $until
"""

RENEW_BATCH_QUERY = f"""
MATCH (w:{LEASE_LABEL} {{kind: $kind}})
WHERE w.batch = $me AND w.batch_until >= $now
SET w.batch_until = $until
RETURN count(w) AS kept
"""

END_BATCH_QUERY = f"""
MATCH (w:{LEASE_LABEL} {{kind: $kind}})
WHERE w.batch = $me
REMOVE w.batch, w.batch_until
"""


@dataclasses.dataclass
class Batch:
    """The heads claimed, as they are now"""

    claimed: list[tuple[str, str]]
    written: list[Item]
    """Those that are there, and neither deleted nor merged into another"""
    removed: list[str]
    """The rest"""
    before: list[str]
    """What their marks keep of before"""

    def changed(self) -> Changed:
        return Changed(
            written=tuple(self.written),
            removed=tuple(self.removed),
            before=tuple(self.before),
        )


async def read_batch(tx: Transaction, claimed: list[tuple[str, str]]) -> Batch:
    ids = [head_id for head_id, _ in claimed]
    there: dict[str, Any] = {}
    async for row in await tx.run(HEADS_QUERY, ids=ids):
        there[row["id"]] = row
    written, removed = [], []
    for head_id in ids:
        row = there.get(head_id)
        if row is None or row["deleted"] or row["merged_into"] is not None:
            removed.append(head_id)
        else:
            written.append(Item(head_id, row["type"]))
    kept = await pending.before_of(tx, KIND, ids)
    before = sorted({ref for b in kept.values() for ref in b.refs})
    return Batch(claimed, written, removed, before)


async def gone_ids(tx: Transaction, batch: Batch) -> list[str]:
    """What has lost its vectors: the heads removed, what is nested in them, and what the marks kept of before that is
    no longer a node"""
    gone = set(batch.removed)
    if batch.removed:
        async for row in await tx.run(BELOW_QUERY, ids=batch.removed):
            gone.add(row["id"])
    if batch.before:
        found = {row["id"] async for row in await tx.run(THERE_QUERY, ids=batch.before)}
        gone |= set(batch.before) - found
    return sorted(gone)


def skipped_because(made: Part, found: store.States) -> str | None:
    """Why a part is not refreshed now: it has never been built, it cannot be on this backend, or the vectors in use
    of a profile that weighs it are of another dimension than today's (a rebuild is due)"""
    if not made.local:
        return "it is rebuilt only"
    why = unavailable(made)
    if why is not None:
        return why
    if made.name not in found.parts:
        return "it has never been built"
    for name in store.profiles_weighing(made.name):
        state = found.profiles.get(name)
        lay = store.layout(name)
        if state is not None and state.dimension != lay.dimension:
            return (
                f"the vectors of the profile {name!r} in use are of dimension {state.dimension}, and its parts now "
                f"make {lay.dimension}: a rebuild is due"
            )
    return None


class Worker:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()
        self.id = str(uuid.uuid4())
        self.stats = Stats()
        self._wake: asyncio.Event | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    # -- waking --

    def wake(self) -> None:
        if self._wake is not None and self._loop is not None:
            self._loop.call_soon_threadsafe(self._wake.set)

    def listen(self, event: hooks.WriteEvent) -> None:
        """(`hooks.after_write`) a write that may have left work: wake up (a `computed` write too: what the criteria
        worker finds is joined in the graph)"""
        if pending_work_of(event.model):
            self.wake()

    def marked(self, model: type) -> None:
        """(`hooks.work_marked`) a head was marked by something that is not a write (it was published)"""
        if pending_work_of(model):
            self.wake()

    # -- the lease of the worker --

    async def take_lease(self) -> bool:
        """Whether this worker is the one that works (it takes the lease, or renews it)"""
        db = database()
        now = time.time()

        @db.write_transaction
        async def take(tx: Transaction) -> bool:
            result = await tx.run(
                f"""
                MERGE (w:{LEASE_LABEL} {{kind: $kind}})
                WITH w
                WHERE w.holder IS NULL OR w.holder = $me OR w.until < $now
                SET w.holder = $me, w.until = $until
                RETURN w.holder AS holder
                """,
                kind=KIND,
                me=self.id,
                now=now,
                until=now + self.settings.lease,
            )
            return await result.single() is not None

        return await take()

    async def give_up_lease(self) -> None:
        db = database()

        @db.write_transaction
        async def give(tx: Transaction) -> None:
            await (
                await tx.run(
                    f"MATCH (w:{LEASE_LABEL} {{kind: $kind, holder: $me}}) REMOVE w.holder, w.until",
                    kind=KIND,
                    me=self.id,
                )
            ).consume()

        await give()

    # -- a batch --

    async def claim(self) -> list[tuple[str, str]] | None:
        """Claim a batch, and mark the worker's node with it, under the rebuild's lock; None if a rebuild holds its
        lease (nothing is claimed)"""
        current = backend.current()
        db = database()
        settings = self.settings

        @db.write_transaction
        async def claim(tx: Transaction) -> list[tuple[str, str]] | None:
            await current.lock(tx, LOCK_KEY)
            now = time.time()
            held = await (await tx.run(REBUILD_HELD_QUERY)).single()
            if (
                held is not None
                and held["holder"] is not None
                and (held["until"] or 0) > now
            ):
                return None
            claimed = await pending.claim(tx, KIND, settings.batch, settings.lease)
            if claimed:
                await (
                    await tx.run(
                        MARK_BATCH_QUERY,
                        kind=KIND,
                        me=self.id,
                        until=now + settings.lease,
                    )
                ).consume()
            return claimed

        return await claim()

    async def renew_batch(self) -> bool:
        current = backend.current()
        db = database()

        @db.write_transaction
        async def renew(tx: Transaction) -> bool:
            await current.lock(tx, LOCK_KEY)
            now = time.time()
            record = await (
                await tx.run(
                    RENEW_BATCH_QUERY,
                    kind=KIND,
                    me=self.id,
                    now=now,
                    until=now + self.settings.lease,
                )
            ).single()
            return bool(record and record["kept"])

        return await renew()

    @contextlib.asynccontextmanager
    async def batch_held(self) -> AsyncGenerator[dict[str, bool]]:
        """The worker's mark of its batch, renewed in the background while the block runs. Gives `{"lost": ...}`,
        true once a renewal found the mark taken off"""
        state = {"lost": False}

        async def keep() -> None:
            while True:
                await asyncio.sleep(self.settings.lease / 4)
                try:
                    if not await self.renew_batch():
                        state["lost"] = True
                        return
                except Exception:  # noqa: BLE001
                    # (tried again at the next beat: the mark holds for four)
                    continue

        task = asyncio.create_task(keep())
        try:
            yield state
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def process_batch(self) -> int:
        """Claim a batch of pending heads and bring their vectors up to date. Gives how many were claimed (0 if none
        were pending, or a rebuild holds its lease: `stats.paused` says which). (The lock of the rebuild is made by
        `drain`)"""
        claimed = await self.claim()
        if claimed is None:
            self.stats.paused += 1
            return 0
        if not claimed:
            return 0
        db = database()
        try:
            async with self.batch_held() as held:

                @db.read_transaction
                async def read(tx: Transaction) -> tuple[Batch, store.States]:
                    return await read_batch(tx, claimed), await store._states(tx)

                batch, found = await read()
                changed = batch.changed()
                written = 0
                stale: dict[str, int] = {}
                skipped: dict[str, str] = {}
                for name, made in parts().items():
                    why = skipped_because(made, found)
                    if why is not None:
                        skipped[name] = why
                        continue

                    async def write(
                        rows: Iterable[VectorRow], name: str = name
                    ) -> None:
                        nonlocal written
                        if held["lost"]:
                            raise BatchLost(
                                "The worker's batch ran out while it worked, and a rebuild went ahead"
                            )
                        written += await store.set_vectors(name, rows)

                    try:
                        refreshed = await made.refresh(changed, write)
                    except store.RebuildDue as error:
                        skipped[name] = str(error)
                        continue
                    if refreshed.stale:
                        stale[name] = refreshed.stale

                @db.read_transaction
                async def gone(tx: Transaction) -> list[str]:
                    return await gone_ids(tx, batch)

                if held["lost"]:
                    raise BatchLost(
                        "The worker's batch ran out while it worked, and a rebuild went ahead"
                    )
                deleted = await store.delete_for(await gone())

                @db.write_transaction
                async def complete(tx: Transaction) -> None:
                    await pending.complete(tx, KIND, claimed)
                    await store.add_stale(tx, stale)
                    await (
                        await tx.run(END_BATCH_QUERY, kind=KIND, me=self.id)
                    ).consume()

                if held["lost"]:
                    raise BatchLost(
                        "The worker's batch ran out while it worked, and a rebuild went ahead"
                    )
                await complete()
        except BaseException:
            # (given back, to be tried again: a claim that is not completed would wait for its lease to run out)
            try:

                @db.write_transaction
                async def release(tx: Transaction) -> None:
                    await pending.release(tx, KIND, [head_id for head_id, _ in claimed])
                    await (
                        await tx.run(END_BATCH_QUERY, kind=KIND, me=self.id)
                    ).consume()

                await release()
            except Exception:
                logger.exception("Could not give back the claims of a failed batch")
            raise
        stats = self.stats
        stats.batches += 1
        stats.heads += len(claimed)
        stats.written += written
        stats.stale += sum(stale.values())
        stats.deleted += deleted
        stats.skipped = skipped
        stats.last_batch_at = time.time()
        for name, why in skipped.items():
            logger.debug("Vectors: the %s part was skipped: %s", name, why)
        logger.debug(
            "Vectors: %s heads, %s vectors written (%s stale), %s deleted",
            len(claimed),
            written,
            sum(stale.values()),
            deleted,
        )
        if stale:
            await self.rebuild_if_stale()
        return len(claimed)

    async def rebuild_if_stale(self) -> None:
        """Start a rebuild of each part with more stale vectors than `VECTORS_REBUILD_AFTER`, if it is set: the admin
        job `vectors_rebuild` (`pangloss_admin`, if installed: a process of its own), or else the rebuild itself, here"""
        limit = rebuild_after()
        if limit is None:
            return
        found = await store.states()
        due = sorted(
            name
            for name, state in found.parts.items()
            if state.stale > limit and name in parts()
        )
        for name in due:
            self.stats.rebuilds += 1
            if start_rebuild_job(name):
                continue
            from pangloss_vectors.rebuild import VectorsRebuildBusy, rebuild

            try:
                logger.info(
                    "Vectors: the %s part has %s stale vectors (VECTORS_REBUILD_AFTER is %s): rebuilding it",
                    name,
                    found.parts[name].stale,
                    limit,
                )
                await rebuild(name)
            except VectorsRebuildBusy:
                # (another is running, which sets the count to 0 as well)
                pass

    async def drain(self) -> int:
        """Do every batch there is now. Gives how many heads were done"""
        # (the node of the lock the claims take, made once for each turn: the tests empty the database between them)
        await backend.current().ensure_lock(LOCK_KEY)
        done = 0
        while True:
            claimed = await self.process_batch()
            if not claimed:
                return done
            done += claimed
            # (the lease is renewed between batches: a worker that has lost it stops, and whoever holds it goes on)
            if not await self.take_lease():
                return done

    async def run(self, settings: Any = None) -> None:
        """Runs until cancelled (a `BackgroundTask`)"""
        self._loop = asyncio.get_running_loop()
        self._wake = asyncio.Event()
        try:
            while not await self.take_lease():
                await asyncio.sleep(self.settings.idle)
            batch, delay = self.settings.batch, 1.0
            while True:
                self._wake.clear()
                paused = self.stats.paused
                try:
                    await self.drain()
                except Exception:
                    # (the claims were given back. Smaller batches meet fewer saves; the size grows back as they go)
                    self.stats.failures += 1
                    self.settings.batch = max(10, self.settings.batch // 2)
                    logger.warning(
                        "Vectors: a batch failed; trying again in %.0f s, %s heads at a time",
                        delay,
                        self.settings.batch,
                        exc_info=True,
                    )
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 60.0)
                    continue
                delay = 1.0
                self.settings.batch = batch
                # (while a rebuild runs, look again soon: nothing wakes the worker when it ends)
                wait = (
                    self.settings.paused
                    if self.stats.paused > paused
                    else self.settings.idle
                )
                try:
                    await asyncio.wait_for(self._wake.wait(), wait)
                except TimeoutError:
                    pass
                while not await self.take_lease():
                    await asyncio.sleep(self.settings.idle)
        finally:
            self._wake = None
            self._loop = None
            try:
                await self.give_up_lease()
            except Exception:
                logger.debug("The lease was not given up", exc_info=True)


def start_rebuild_job(part_name: str) -> bool:
    """Start the admin job `vectors_rebuild` of a part, if `pangloss_admin` is installed (a job of the kind already
    running is left to run). Gives whether the job was started or is running"""
    from pangloss_core import settings as core_settings

    settings = core_settings.__dict__.get("SETTINGS")
    if "pangloss_admin" not in (getattr(settings, "INSTALLED_APPS", None) or ()):
        return False
    from pangloss_admin import store as job_store

    jobs = job_store.JobStore(job_store.jobs_directory(settings))
    try:
        job = jobs.create("vectors_rebuild", {"part": part_name}, "vectors worker")
    except job_store.JobConflict:
        return True
    logger.info(
        "Vectors: the %s part has more stale vectors than VECTORS_REBUILD_AFTER: the job %s rebuilds it",
        part_name,
        job["id"],
    )
    # (through the module, so that the tests can put something else in its place)
    job_store.launch(jobs, job["id"])
    return True


# The worker of this process (the server's background task; the tests' `run_pending`)
worker = Worker()


async def run_pending() -> int:
    """Do all the pending work now (for tests and scripts: no waiting for the background). Gives how many heads
    were done. Nothing while a rebuild holds its lease"""
    await worker.take_lease()
    try:
        return await worker.drain()
    finally:
        await worker.give_up_lease()


async def pending_status() -> dict[str, Any]:
    """What is pending and claimed, and when the oldest was marked"""
    db = database()

    @db.read_transaction
    async def read(tx: Transaction) -> dict[str, Any]:
        return await pending.count(tx, KIND)

    return await read()


async def idle(timeout: float = 30.0, poll: float = 0.05) -> None:
    """Wait until no head is pending for this worker. Raises `TimeoutError` if some still are after `timeout`
    seconds (the worker may not be running)"""
    deadline = time.monotonic() + timeout
    while left := (await pending_status())["pending"]:
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"{left} heads still wait for their vectors after {timeout} s: is the vectors worker running?"
            )
        await asyncio.sleep(poll)
