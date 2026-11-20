"""The worker that keeps the candidates of descriptions up to date, in the background
(implementation_docs/matches-criteria.md, "The worker").

A write of a head that can hold a description, or that the criteria of one could reach (`holders`), leaves it
pending (`pangloss_cypher.pending`, kind `criteria`), in the write's own transaction. The worker, in a loop:

1. **claims** a batch of pending heads;
2. **reads** them: the version of each, the labels of its nodes, the entities it names, and the descriptions inside
   it, with the candidates they have now; and what the marks keep of the heads as they were before an update;
3. **chooses** the descriptions of other documents that what was written could change (`Worker.job_for`): those
   whose criteria touch a class that a written head has, or had, a node of (`depends_on`), and of those the ones
   the entities written bear on (below); and those that name a written entity (`names`);
4. **evaluates** them (`evaluate.evaluate_many`): among the entities the batch names, from an anchor, or root
   first;
5. **writes** what it found with `set_computed`, each only if its head is still at the version read, and completes
   the claims in the last transaction. A description inside a written head is always written (it is evaluated as
   of that write); one that was chosen only if what was found is not what it has. A head written again meanwhile
   has a new token: it stays pending, and is done again.

Only one worker works at a time (a lease on a `PGCriteriaWorker` node), which is what makes the result exact: each
head is processed after its last write, reading the data as it then is.

**Which descriptions, and how** (`analysis` says what a pattern is):

| The description | Chosen | Evaluated |
|---|---|---|
| Inside a written head | Always | In full |
| Names a written entity (one merged, or merged into) | Always | In full |
| `far` | Always | In full |
| `local`, with more candidates than are linked | Always | In full: its list is not all of them |
| `local` and complete ("secretary of X") | If a written head names (or named) an id of each of its anchors, or is an entity that is another than it was (its class changed, another merged into it), or a candidate of its was written | Among what those heads name, and its candidates |
| `local` otherwise | Always | Among everything the batch names, and its candidates |

**The places of one description** (`same_one`: a mark several places of one document share) are one: of a mark,
one place that holds the criteria is evaluated, and every place of the mark in its head is given the result
(`evaluated_by`). The queries that choose descriptions of other documents choose those that hold criteria; a place
with none comes with the holder of its mark that is chosen, and is skipped with it.

"In full" is from an anchor where the criteria name an entity, and root first where they do not. "Among" is exact
for a local pattern because a write can change whether an entity matches only if the head written names the
entity, now or before (the **seeds**: what each head names, what its mark kept of before, and itself), and the
candidates it has are tested again with them.
"""

import asyncio
import dataclasses
import datetime
import functools
import logging
import time
import uuid
from typing import Any

from pangloss_core import Transaction, backend, storage_of
from pangloss_cypher import fragments, pending
from pangloss_cypher.heads import VERSION_OF_HEAD
from pangloss_models import ComputedWrite, PanglossSearchError, hooks
from pangloss_models.computed import EVERYONE

from pangloss_criteria import analysis, holders
from pangloss_criteria.evaluate import (
    Counts,
    Evaluation,
    Job,
    evaluate,
    evaluate_many,
    named_by,
)
from pangloss_criteria.holders import KIND
from pangloss_criteria.models import NAME
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
    chosen: int = 0
    """Descriptions of other documents evaluated because of what was written"""
    skipped: int = 0
    """Descriptions that depend on a class written, and that nothing written bears on: not evaluated"""
    seeded: int = 0
    """Evaluated among the entities the batch names"""
    anchored: int = 0
    """Evaluated in full, from an entity the criteria name"""
    root_first: int = 0
    """Evaluated in full, every entity of the class tested"""
    shared: int = 0
    """Evaluated with others of identical criteria, once for all (`evaluate.evaluate_many`)"""
    unchanged: int = 0
    """Of those, the ones whose result was what they had: nothing written"""
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
    labels: set[str] = dataclasses.field(default_factory=set)
    """The labels of its nodes"""
    anew: bool = False
    """It is an entity that is another now than it was: its class was changed, or others were merged into it. It
    may match what it did not, with no document that names it written"""
    seeds: set[str] = dataclasses.field(default_factory=set)
    """The entities a write of it can change a match of: itself, what it names, what it named before an update
    (the mark's `before_refs`), and the entities merged into any of those (criteria name ids as they were
    written). Of a written head only"""


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
    same_one: str | None = None
    """The mark it shares with the other places of its document that describe the same one. A place with no
    criteria of its own takes the result of one of its mark that has them"""

    @property
    def mark(self) -> tuple[str, str] | None:
        """Its mark, in its head (the same mark in another document means nothing)"""
        return None if self.same_one is None else (self.head, self.same_one)


def evaluated_by(descriptions: list[Description]) -> dict[str, Description | None]:
    """For each description (by id), the one whose evaluation it takes: itself, if it holds criteria and is the
    first of its mark with them (or has no mark); the first of its mark with the same criteria; and for a place
    with no criteria, the first of its mark that has them. None for a place of a mark that no place of its head
    holds criteria for (the API refuses such a write: there may be one after a hand edit)"""
    first: dict[tuple[str, str], Description] = {}
    holding: dict[tuple[tuple[str, str], str], Description] = {}
    for description in descriptions:
        if description.mark is not None and description.criteria is not None:
            first.setdefault(description.mark, description)
            holding.setdefault((description.mark, description.criteria), description)
    found: dict[str, Description | None] = {}
    for description in descriptions:
        if description.mark is None:
            found[description.id] = description if description.criteria else None
        elif description.criteria is None:
            found[description.id] = first.get(description.mark)
        else:
            found[description.id] = holding[(description.mark, description.criteria)]
    return found


def database() -> Any:
    return backend.current().database()


HEADS_QUERY = f"""
    UNWIND $heads AS head_id
    MATCH (head:HeadNode {{id: head_id}})
    RETURN head.id AS id, head.type AS type, {VERSION_OF_HEAD} AS version,
           {fragments.deleted("head")} AS deleted
"""

LABELS_OF_HEAD_QUERY = """
    UNWIND $heads AS head_id
    MATCH (node:HeadNode {id: head_id})
    RETURN head_id AS head, labels(node) AS labels
"""

LABELS_BELOW_QUERY = """
    UNWIND $heads AS head_id
    MATCH (node:PGIndexableNode {head_node_id: head_id})
    UNWIND labels(node) AS label
    RETURN head_id AS head, collect(DISTINCT label) AS labels
"""

# The descriptions of other documents that a batch could change: their criteria touch a class that a written head
# has (or had) a node of, or name a written entity (one that was merged, or into which another was: the ids of the
# criteria are resolved when they are evaluated)
# (the first choice, in the database: `anchors` holds ids only for a pattern that no write can bear on unless it
# names one of them. A description saved before these were worked out has no `reach`, and is always chosen)
CHOOSE_QUERY = f"""
    MATCH (d:{NAME})
    WHERE d.criteria IS NOT NULL AND NOT d.head_node_id IN $heads
    WITH d, any(id IN coalesce(d.names, []) WHERE id IN $written) AS named
    WHERE named
       OR (any(label IN coalesce(d.depends_on, []) WHERE label IN $labels)
           AND (coalesce(d.reach, 'far') <> 'local'
                OR size(coalesce(d.anchors, [])) = 0
                OR coalesce(d.candidate_count, 0) > size([(d)-[edge:target]->() WHERE {fragments.forward("edge")} | 1])
                OR $anew
                OR any(id IN d.anchors WHERE id IN $seeds)))
    RETURN d.id AS id, d.head_node_id AS head, named
"""

# The descriptions a written entity is a candidate of (its class may have changed)
CANDIDATE_OF_QUERY = f"""
    UNWIND $written AS id
    MATCH (candidate:Entity {{id: id}})<-[edge:target]-(d:{NAME})
    WHERE {fragments.forward("edge")} AND d.criteria IS NOT NULL AND NOT d.head_node_id IN $heads
    RETURN DISTINCT d.id AS id, d.head_node_id AS head
"""

# The entities merged into each of these (those of merges since undone too: more seeds do no harm)
MERGED_INTO_QUERY = """
    UNWIND $ids AS id
    MATCH (m:PGMerge {survivor: id})
    RETURN id, collect(DISTINCT m.absorbed) AS absorbed
"""

EVERY_HEAD_QUERY = f"""
    MATCH (d:{NAME})
    RETURN DISTINCT d.head_node_id AS head
"""

DESCRIPTIONS_QUERY = f"""
    UNWIND $heads AS head_id
    MATCH (d:PGIndexableNode {{head_node_id: head_id}})
    WHERE any(label IN labels(d) WHERE label IN $labels)
    RETURN head_id AS head, d.id AS id, d.criteria AS criteria, d.same_one AS same_one,
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
    for head_id, named in (await named_by(tx, heads)).items():
        heads[head_id].named = named
    for query in (LABELS_OF_HEAD_QUERY, LABELS_BELOW_QUERY):
        async for row in await tx.run(query, heads=ids):
            if row["head"] in heads:
                heads[row["head"]].labels.update(row["labels"])
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
                    same_one=None if row["same_one"] is None else str(row["same_one"]),
                )
            )
    return heads, descriptions


async def merged_into(tx: Transaction, ids: set[str]) -> dict[str, set[str]]:
    """For each id, the ids of the entities merged into it, through any number of merges"""
    found: dict[str, set[str]] = {}
    asking = {id: {id} for id in ids}
    while asking:
        rows = await tx.run(MERGED_INTO_QUERY, ids=sorted(asking))
        again: dict[str, set[str]] = {}
        async for row in rows:
            for absorbed in row["absorbed"]:
                for first in asking[row["id"]]:
                    if absorbed not in found.setdefault(first, set()):
                        found[first].add(absorbed)
                        again.setdefault(absorbed, set()).add(first)
        asking = again
    return found


@dataclasses.dataclass
class Batch:
    """What a batch of written heads is, read once"""

    written: list[Head]
    """The heads that were claimed, as they are now (one that is no longer there is left out)"""
    heads: dict[str, Head]
    """Those, and the heads of the descriptions chosen"""
    descriptions: list[Description]
    """The descriptions inside the written heads, and those chosen"""
    chosen: dict[str, bool] = dataclasses.field(default_factory=dict)
    """The descriptions of other documents, by id: whether it is to be evaluated in full whatever it is (it names
    a written entity)"""

    @property
    def seeds(self) -> set[str]:
        return {id for head in self.written for id in head.seeds}


async def read_batch(tx: Transaction, ids: list[str]) -> Batch:
    heads, descriptions = await read_heads(tx, ids)
    written = [heads[id] for id in ids if id in heads]
    # (the labels the written heads have nodes of, and had before an update replaced them)
    labels = {label for head in written for label in head.labels}
    kept = await pending.before_of(tx, KIND, ids)
    for head in written:
        head.seeds = {head.id, *head.named}
        if head.id in kept:
            head.seeds |= kept[head.id].refs
            labels |= kept[head.id].labels
            head.anew = "Entity" in head.labels and bool(
                (head.labels ^ kept[head.id].labels) - {"HeadNode"}
            )
    absorbed = await merged_into(tx, {id for head in written for id in head.seeds})
    for head in written:
        head.anew = head.anew or bool(absorbed.get(head.id))
        for id in list(head.seeds):
            head.seeds |= absorbed.get(id, set())
    batch = Batch(written, heads, descriptions)
    written_ids = sorted(
        {id for head in written for id in (head.id, *absorbed.get(head.id, ()))}
    )
    result = await tx.run(
        CHOOSE_QUERY,
        labels=sorted(labels),
        heads=ids,
        written=written_ids,
        seeds=sorted(batch.seeds),
        anew=any(head.anew for head in written),
    )
    where: dict[str, str] = {}
    async for row in result:
        where[row["id"]] = row["head"]
        batch.chosen[row["id"]] = row["named"]
    async for row in await tx.run(CANDIDATE_OF_QUERY, written=written_ids, heads=ids):
        where.setdefault(row["id"], row["head"])
        batch.chosen.setdefault(row["id"], False)
    if where:
        others, their = await read_heads(tx, sorted(set(where.values())))
        heads.update(others)
        # (a holder chosen brings the places of its mark: they take its result. The queries choose holders only)
        marks = {
            d.mark: batch.chosen[d.id]
            for d in their
            if d.id in where and d.mark is not None
        }
        for d in their:
            if d.id in where:
                descriptions.append(d)
            elif d.mark in marks:
                descriptions.append(d)
                batch.chosen[d.id] = marks[d.mark]
    return batch


def same_result(description: Description, values: dict[str, Any]) -> bool:
    """Whether what was found for a description is what it has"""
    if "target" not in values:
        return description.broken == values["broken"]
    return (
        description.broken is None
        and description.count == values["candidate_count"]
        and description.count_everyone == values["candidate_count_everyone"]
        and description.targets
        == [(str(target.id), target.seen_by) for target in values["target"]]
    )


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
        self,
        description: Description,
        head: Head,
        when: datetime.datetime,
        criteria: str | None = None,
    ) -> dict[str, Any] | None:
        """What a description would have, evaluated alone, in full and root first (the plain way, which the
        others must agree with: `out_of_date`). `criteria`: those it is evaluated by, if not its own (a place of a
        mark, by those of the place that holds them: `evaluated_by`). None for one that has none"""
        criteria = criteria if criteria is not None else description.criteria
        if criteria is None:
            return None
        try:
            found = await evaluate(SearchPattern(criteria), head.named)
        except (PanglossSearchError, ValueError) as error:
            # (the criteria no longer fit the models: said on the description, which keeps the candidates it has,
            # and not tried again until it is saved)
            self.stats.broken += 1
            return {"broken": str(error), "evaluated_when": when}
        self.stats.evaluated += 1
        return values_of(found, when)

    def job_for(self, description: Description, head: Head, batch: Batch) -> Job | None:
        """How a description is to be evaluated for the batch (the table at the top). None: nothing written bears
        on it. Raises `ValueError` if its criteria cannot be read"""
        job = Job(description.id, SearchPattern(description.criteria), set(head.named))
        if description.id not in batch.chosen or batch.chosen[description.id]:
            return job
        found = analysis.of(job.pattern)
        if found is None or found.reach != analysis.LOCAL:
            return job
        # (its list is not all of them; or it had no result, and what it has is of before)
        if description.count != len(description.targets) or description.broken:
            return job
        has = {id for id, _ in description.targets}
        if found.complete:
            bearing = [
                written
                for written in batch.written
                if written.anew
                or all(
                    any(id in written.seeds for id in anchor.ids)
                    for anchor in found.anchors
                )
            ]
            if not bearing and not has & {written.id for written in batch.written}:
                return None
            job.among = has.union(*(written.seeds for written in bearing))
        else:
            job.among = has | batch.seeds
        return job

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
            async def read(tx: Transaction) -> Batch:
                return await read_batch(tx, ids)

            batch = await read()
            read_at = time.monotonic()
            when = datetime.datetime.now(datetime.UTC)
            stats = self.stats
            results: dict[str, Evaluation | Exception] = {}
            jobs: list[Job] = []
            # (of the places of one mark, one is evaluated: the others take its result, below)
            by = evaluated_by(batch.descriptions)
            for description in batch.descriptions:
                head = batch.heads.get(description.head)
                # (a deleted document shows nothing: evaluated again when it is brought back, which marks it)
                if (
                    head is None
                    or head.deleted
                    or by[description.id] is not description
                ):
                    continue
                try:
                    job = self.job_for(description, head, batch)
                except ValueError as error:
                    results[description.id] = error
                    continue
                if job is None:
                    stats.skipped += 1
                else:
                    jobs.append(job)
            counts = Counts()
            results.update(await evaluate_many(jobs, counts=counts))
            stats.seeded += counts.seeded
            stats.anchored += counts.anchored
            stats.root_first += counts.root_first
            stats.shared += counts.shared
            writes: list[ComputedWrite] = []
            for description in batch.descriptions:
                source = by[description.id]
                found = None if source is None else results.get(source.id)
                if found is None:
                    continue
                if isinstance(found, Exception):
                    # (the criteria no longer fit the models: said on the description, which keeps the candidates
                    # it has, and not tried again until it is saved)
                    stats.broken += 1
                    values: dict[str, Any] = {
                        "broken": str(found),
                        "evaluated_when": when,
                    }
                else:
                    stats.evaluated += 1
                    values = values_of(found, when)
                if description.id in batch.chosen:
                    stats.chosen += 1
                    # (its document was not written: nothing to say unless the result is another. Each write
                    # is an event for the pages that show it, and work for whoever reads the candidates)
                    if same_result(description, values):
                        stats.unchanged += 1
                        continue
                writes.append(
                    ComputedWrite(
                        description.id, values, batch.heads[description.head].version
                    )
                )
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


async def read_some(
    ids: list[str], tx: Transaction
) -> tuple[dict[str, Head], list[Description]]:
    return await read_heads(tx, ids)


ANY_PENDING_QUERY = f"MATCH (p:{pending.LABEL}) RETURN count(p) AS marks"


async def idle(timeout: float = 30.0, poll: float = 0.05) -> None:
    """Wait until no work of any kind is pending: of this worker, and of every other app's (`pangloss-derived`
    writes derived documents after a save, which the criteria then read, and reads the candidates this worker
    writes). `settled` waits for a description's first result; a test of the two packages together waits with
    this. Raises `TimeoutError` if work is still pending after `timeout` seconds (a worker may not be running)"""
    db = database()

    @db.read_transaction
    async def marks(tx: Transaction) -> int:
        record = await (await tx.run(ANY_PENDING_QUERY)).single()
        return record["marks"] if record else 0

    deadline = time.monotonic() + timeout
    while left := await marks():
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"{left} heads still have work pending after {timeout} s: are the workers running?"
            )
        await asyncio.sleep(poll)


async def out_of_date(chunk: int = 200) -> list[str]:
    """The ids of the descriptions whose stored result is not what a full evaluation gives now: every description
    of the database is evaluated, and nothing is written. Empty when the worker has caught up with every write
    (what "exact in the end" means, and what the churn test asks). It runs long on a large database"""
    db = database()

    @db.read_transaction
    async def every_head(tx: Transaction) -> list[str]:
        return [row["head"] async for row in await tx.run(EVERY_HEAD_QUERY)]

    head_ids = sorted(await every_head())
    when = datetime.datetime.now(datetime.UTC)
    checker = Worker()
    found: list[str] = []
    for start in range(0, len(head_ids), chunk):
        some = head_ids[start : start + chunk]

        heads, descriptions = await db.read_transaction(
            functools.partial(read_some, some)
        )()
        # (each place alone: a place with no criteria by those of its mark's holder, in its head)
        by = evaluated_by(descriptions)
        for description in descriptions:
            head = heads.get(description.head)
            source = by[description.id]
            if head is None or head.deleted or source is None:
                continue
            values = await checker.evaluate_description(
                description, head, when, source.criteria
            )
            if values is not None and not same_result(description, values):
                found.append(description.id)
    return found


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
