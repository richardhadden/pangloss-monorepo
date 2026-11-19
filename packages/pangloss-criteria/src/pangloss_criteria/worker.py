"""The worker that keeps the candidates of descriptions up to date, in the background
(implementation_docs/matches-criteria.md, "The worker").

A write of a head that can hold a description leaves it pending (`pangloss_cypher.pending`, kind `criteria`), in the
write's own transaction. The worker, in a loop:

1. **claims** a batch of pending heads;
2. **reads** them: the version of each, the entities each names, and the descriptions inside each, with the
   candidates they have now;
3. **evaluates** each description in full (`evaluate.evaluate`);
4. **writes** what it found with `set_computed`, each only if its head is still at the version read, and completes
   the claims in the last transaction. A head written again meanwhile has a new token: it stays pending, and is
   done again.

Only one worker works at a time (a lease on a `PGCriteriaWorker` node), which is what makes the result exact: each
head is processed after its last write, reading the data as it then is.

(So far it evaluates the descriptions inside the heads that were written. Following the writes of other documents
is step 5 of the plan.)
"""

import asyncio
import dataclasses
import datetime
import logging
import time
import uuid
from typing import Any

from pangloss_core import Transaction, backend, storage_of
from pangloss_cypher import fragments, pending
from pangloss_cypher.heads import VERSION_OF_HEAD
from pangloss_models import ComputedWrite, PanglossSearchError, hooks
from pangloss_models.computed import EVERYONE

from pangloss_criteria import holders
from pangloss_criteria.evaluate import Evaluation, evaluate
from pangloss_criteria.holders import KIND
from pangloss_criteria.pattern import SearchPattern

logger = logging.getLogger("pangloss.criteria.worker")

LEASE_LABEL = "PGCriteriaWorker"


@dataclasses.dataclass
class Settings:
    batch: int = 200
    """Heads claimed at once"""
    lease: float = 30.0
    """Seconds a claim (and the worker's lease) holds, unless renewed"""
    idle: float = 10.0
    """Seconds between looks for work when nothing wakes it"""
    write_chunk: int = 500
    """Descriptions written in one transaction"""


@dataclasses.dataclass
class Stats:
    batches: int = 0
    heads: int = 0
    evaluated: int = 0
    written: int = 0
    refused: int = 0
    """Results not written because their head had changed since it was read (it is pending again)"""
    broken: int = 0
    failures: int = 0
    seconds_reading: float = 0.0
    seconds_evaluating: float = 0.0
    seconds_writing: float = 0.0
    last_batch_at: float | None = None


@dataclasses.dataclass
class Head:
    id: str
    type: str
    version: int
    deleted: bool
    named: set[str] = dataclasses.field(default_factory=set)
    """The ids of the entities its tree refers to (not those it is computed to be related to)"""


@dataclasses.dataclass
class Description:
    """A description as it is stored now"""

    id: str
    head: str
    criteria: str | None
    count: int
    count_everyone: int
    broken: str | None
    targets: list[tuple[str, str]]
    """Its candidates, in order: (id, who may see it)"""


def database() -> Any:
    return backend.current().database()


HEADS_QUERY = f"""
    UNWIND $heads AS head_id
    MATCH (head:HeadNode {{id: head_id}})
    RETURN head.id AS id, head.type AS type, {VERSION_OF_HEAD} AS version,
           {fragments.deleted("head")} AS deleted
"""

# The entities a head names: those its own node refers to, and those the nodes below it do (two queries: each finds
# its nodes by an index). Not what is computed (`asserted`): a candidate is not "named"
NAMED_BY_HEAD_QUERY = f"""
    UNWIND $heads AS head_id
    MATCH (node:PGIndexableNode {{id: head_id}})-[edge]->(entity:Entity)
    WHERE {fragments.forward("edge")} AND {fragments.asserted("edge")}
    RETURN head_id AS head, collect(DISTINCT entity.id) AS named
"""

NAMED_BELOW_QUERY = f"""
    UNWIND $heads AS head_id
    MATCH (node:PGIndexableNode {{head_node_id: head_id}})-[edge]->(entity:Entity)
    WHERE {fragments.forward("edge")} AND {fragments.asserted("edge")}
    RETURN head_id AS head, collect(DISTINCT entity.id) AS named
"""

DESCRIPTIONS_QUERY = f"""
    UNWIND $heads AS head_id
    MATCH (d:PGIndexableNode {{head_node_id: head_id}})
    WHERE any(label IN labels(d) WHERE label IN $labels)
    RETURN head_id AS head, d.id AS id, d.criteria AS criteria,
           coalesce(d.candidate_count, 0) AS count,
           coalesce(d.candidate_count_everyone, 0) AS count_everyone,
           d.broken AS broken,
           [(d)-[edge:target]->(candidate)
            WHERE coalesce(edge.{fragments.COMPUTED_EDGE}, false) AND NOT coalesce(edge.reverse, false)
            | {{id: candidate.id, seen_by: coalesce(edge.seen_by, '{EVERYONE}'),
                position: coalesce(edge.pg_position, 0)}}] AS targets
"""


async def read_heads(
    tx: Transaction, ids: list[str]
) -> tuple[dict[str, Head], list[Description]]:
    """The heads as they are now, and the descriptions inside them"""
    heads: dict[str, Head] = {}
    async for row in await tx.run(HEADS_QUERY, heads=ids):
        heads[row["id"]] = Head(
            id=row["id"],
            type=row["type"],
            version=row["version"],
            deleted=row["deleted"],
        )
    for query in (NAMED_BY_HEAD_QUERY, NAMED_BELOW_QUERY):
        async for row in await tx.run(query, heads=ids):
            if row["head"] in heads:
                heads[row["head"]].named.update(row["named"])
    descriptions: list[Description] = []
    labels = holders.description_labels()
    if labels:
        async for row in await tx.run(DESCRIPTIONS_QUERY, heads=ids, labels=labels):
            targets = sorted(row["targets"], key=lambda t: t["position"])
            descriptions.append(
                Description(
                    id=row["id"],
                    head=row["head"],
                    criteria=row["criteria"],
                    count=row["count"],
                    count_everyone=row["count_everyone"],
                    broken=row["broken"],
                    targets=[(t["id"], t["seen_by"]) for t in targets],
                )
            )
    return heads, descriptions


def values_of(found: Evaluation, when: datetime.datetime) -> dict[str, Any]:
    return {
        "target": found.targets,
        "candidate_count": found.count,
        "candidate_count_everyone": found.count_everyone,
        "evaluated_when": when,
        "broken": None,
    }


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
        """(`hooks.after_write`) a write that may have left work: wake up. Not what this worker itself wrote (a
        `computed` event: nothing computed leaves work of this kind)"""
        if event.op != "computed" and holders.pending_work_of(event.model):
            self.wake()

    def marked(self, model: type) -> None:
        """(`hooks.work_marked`) a head was marked by something that is not a write"""
        if holders.pending_work_of(model):
            self.wake()

    # -- the lease --

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

    async def evaluate_description(
        self, description: Description, head: Head, when: datetime.datetime
    ) -> dict[str, Any] | None:
        """What to write for a description inside a head that was written: its result, or why it has none. None
        for one that has no criteria of its own"""
        if description.criteria is None:
            return None
        try:
            found = await evaluate(SearchPattern(description.criteria), head.named)
        except (PanglossSearchError, ValueError) as error:
            # (the criteria no longer fit the models: said on the description, which keeps the candidates it has,
            # and not tried again until it is saved)
            self.stats.broken += 1
            return {"broken": str(error), "evaluated_when": when}
        self.stats.evaluated += 1
        return values_of(found, when)

    async def process_batch(self) -> int:
        """Claim a batch of pending heads and evaluate the descriptions inside them. Gives how many were claimed"""
        db = database()
        settings = self.settings

        @db.write_transaction
        async def claim(tx: Transaction) -> list[tuple[str, str]]:
            return await pending.claim(tx, KIND, settings.batch, settings.lease)

        claimed = await claim()
        if not claimed:
            return 0
        ids = [head_id for head_id, _ in claimed]
        began = time.monotonic()
        try:

            @db.read_transaction
            async def read(
                tx: Transaction,
            ) -> tuple[dict[str, Head], list[Description]]:
                return await read_heads(tx, ids)

            heads, descriptions = await read()
            read_at = time.monotonic()
            when = datetime.datetime.now(datetime.UTC)
            writes: list[ComputedWrite] = []
            for description in descriptions:
                head = heads.get(description.head)
                # (a deleted document shows nothing: evaluated again when it is brought back, which marks it)
                if head is None or head.deleted:
                    continue
                values = await self.evaluate_description(description, head, when)
                if values is not None:
                    writes.append(ComputedWrite(description.id, values, head.version))
            evaluated_at = time.monotonic()
            await self.write(writes, claimed)
        except BaseException:
            # (given back, to be tried again: a claim that is not completed would wait for its lease to run out)
            try:

                @db.write_transaction
                async def release(tx: Transaction) -> None:
                    await pending.release(tx, KIND, ids)

                await release()
            except Exception:
                logger.exception("Could not give back the claims of a failed batch")
            raise
        stats = self.stats
        stats.batches += 1
        stats.heads += len(claimed)
        stats.seconds_reading += read_at - began
        stats.seconds_evaluating += evaluated_at - read_at
        stats.seconds_writing += time.monotonic() - evaluated_at
        stats.last_batch_at = time.time()
        logger.debug(
            "Criteria: %s heads, %s descriptions (%.0f ms reading, %.0f ms evaluating, %.0f ms writing)",
            len(claimed),
            len(writes),
            (read_at - began) * 1000,
            (evaluated_at - read_at) * 1000,
            (time.monotonic() - evaluated_at) * 1000,
        )
        return len(claimed)

    async def write(
        self, writes: list[ComputedWrite], claimed: list[tuple[str, str]]
    ) -> None:
        """Write the results, some at a time, and complete the claims in the last transaction: a head is done only
        when all that was found for it is written. A result whose head has changed since it was read is refused
        (`set_computed`), and nothing more need be done: the save that changed it marked it again"""
        set_computed_batch = storage_of().operations.set_computed_batch

        async def complete(tx: Any) -> None:
            await pending.complete(tx, KIND, claimed)

        chunk = self.settings.write_chunk
        chunks = [
            writes[start : start + chunk] for start in range(0, len(writes), chunk)
        ]
        for index, some in enumerate(chunks or [[]]):
            last = index == len(chunks or [[]]) - 1
            # (never `criteria`: no description searches through candidates, so writing them changes no other
            # result. The head's other kinds are marked: a derived rule reads the candidates)
            written = await set_computed_batch(
                some, less=[KIND], then=complete if last else None
            )
            self.stats.written += sum(written)
            self.stats.refused += len(written) - sum(written)

    async def drain(self) -> int:
        """Do every batch there is now. Gives how many heads were done"""
        done = 0
        while True:
            claimed = await self.process_batch()
            if not claimed:
                return done
            done += claimed
            await self.take_lease()

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
                try:
                    await self.drain()
                except Exception:
                    # (most often a write that met saves too many times: the claims were given back. Smaller
                    # batches meet fewer; the size grows back as they go through)
                    self.stats.failures += 1
                    self.settings.batch = max(10, self.settings.batch // 2)
                    logger.warning(
                        "Criteria: a batch failed; trying again in %.0f s, %s heads at a time",
                        delay,
                        self.settings.batch,
                        exc_info=True,
                    )
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 60.0)
                    continue
                delay = 1.0
                self.settings.batch = batch
                try:
                    await asyncio.wait_for(self._wake.wait(), self.settings.idle)
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


# The worker of this process (the server's background task; the tests' `run_pending`)
worker = Worker()


async def run_pending() -> int:
    """Do all the pending work now (for tests and scripts: no waiting for the background). Gives how many heads
    were done"""
    await worker.take_lease()
    try:
        return await worker.drain()
    finally:
        await worker.give_up_lease()


async def pending_status() -> dict[str, Any]:
    """What is pending and claimed, and the oldest mark"""
    db = database()

    @db.read_transaction
    async def read(tx: Transaction) -> dict[str, Any]:
        return await pending.count(tx, KIND)

    return await read()


PENDING_QUERY = f"MATCH (p:{pending.LABEL} {{key: $key}}) RETURN count(p) AS marks"


async def is_pending(head_id: Any) -> bool:
    """Whether a head is marked for this worker (written, and not yet processed since)"""
    db = database()

    @db.read_transaction
    async def read(tx: Transaction) -> bool:
        record = await (
            await tx.run(PENDING_QUERY, key=pending.key_of(KIND, str(head_id)))
        ).single()
        return bool(record and record["marks"])

    return await read()


async def settled(head_id: Any, timeout: float = 10.0, poll: float = 0.02) -> None:
    """Wait until the mark a save left on a head is completed: the descriptions in it have their first result
    since that save. `save()` returns before the candidates are there; a script or a test that reads them waits
    with this. Raises `TimeoutError` if the worker has not done it in `timeout` seconds (it may not be running)"""
    deadline = time.monotonic() + timeout
    while await is_pending(head_id):
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"The descriptions of {head_id} were not evaluated in {timeout} s: is the criteria worker running?"
            )
        await asyncio.sleep(poll)
