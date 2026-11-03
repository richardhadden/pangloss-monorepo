"""The worker that keeps derived facts up to date, in the background.

A write of a head node whose class can trigger a rule leaves it pending (`pangloss_cypher.pending`, kind `derive`), in
the write's own transaction; the write is not slower by more than that. The worker, in a loop:

1. **claims** a batch of pending heads;
2. **finds** (in a read transaction) every justification that a node of one of them is in: for each place of each rule
   that a node of its tree can be at, one seeded query with all the batch's nodes of that class;
3. **writes** (in one write transaction) what was found that is not there, deletes the justifications with evidence in
   the batch that were not found again (and the facts left with none), and completes the claims whose token is the one
   claimed. A head written again meanwhile stays pending, and is done again.

Only one worker works at a time (a lease on a `PGDeriveWorker` node; another waits), which is what makes this exact:
see docs/derived-implementation.md, "Why one sequential worker converges". `after_write` wakes it, so that the work
starts at once rather than at its next look.

When it starts, and when asked, it brings each rule up to date with the facts stored (`sync_rules`): a new rule, or one
whose hash has changed, is built again from all the nodes of the class of one of its places; one that was removed has
its facts deleted.
"""

import asyncio
import dataclasses
import logging
import time
import uuid
from typing import Any

from pangloss_core import backend
from pangloss_cypher import pending
from pangloss_core.backend import Transaction
from pangloss_models import hooks

from pangloss_derived import store
from pangloss_derived.check import CheckedRule
from pangloss_derived.registry import DerivedRegistry

logger = logging.getLogger("pangloss.derived.worker")

KIND = "derive"
LEASE_LABEL = "PGDeriveWorker"


@dataclasses.dataclass
class Settings:
    batch: int = 200
    """Heads claimed at once"""
    lease: float = 30.0
    """Seconds a claim (and the worker's lease) holds, unless renewed (after each batch, and each chunk of a build).
    A worker that stops without giving its lease up holds the others back this long"""
    idle: float = 10.0
    """Seconds between looks for work when nothing wakes it"""
    rebuild_chunk: int = 500
    """Nodes seeded at once when a rule is built again"""
    remove_chunk: int = 5000


@dataclasses.dataclass
class Stats:
    batches: int = 0
    heads: int = 0
    new: int = 0
    removed: int = 0
    rows: int = 0
    overflows: int = 0
    failures: int = 0
    seconds_finding: float = 0.0
    seconds_writing: float = 0.0
    last_batch_at: float | None = None
    rebuilds: dict[str, dict[str, Any]] = dataclasses.field(default_factory=dict)


def database() -> Any:
    return backend.current().database()


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
        """(`hooks.after_write`) a write that may have left work: wake up"""
        if event.model.__name__ in DerivedRegistry.triggers:
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

    async def process_batch(self) -> int:
        """Claim a batch of pending heads and bring what they justify up to date. Gives how many were claimed"""
        db = database()
        settings = self.settings

        @db.write_transaction
        async def claim(tx: Transaction) -> list[tuple[str, str]]:
            return await pending.claim(tx, KIND, settings.batch, settings.lease)

        claimed = await claim()
        if not claimed:
            return 0
        heads = [head_id for head_id, _ in claimed]
        began = time.monotonic()
        try:

            @db.read_transaction
            async def find(tx: Transaction) -> tuple[store.Found, set[str]]:
                return await store.find_for_heads(tx, heads)

            found, incomplete = await find()
            found_at = time.monotonic()
            counts = await store.write_found(
                db, found, replace_for_heads=[h for h in heads if h not in incomplete]
            )

            # (last: a head is done only when all it gave is written)
            @db.write_transaction
            async def complete(tx: Transaction) -> None:
                await pending.complete(tx, KIND, claimed)
                for seed, rule in found.overflowed.items():
                    await store.count_overflow(tx, rule, seed)

            await complete()
        except BaseException:
            # (given back, to be tried again: a claim that is not completed would wait for its lease to run out)
            try:

                @db.write_transaction
                async def release(tx: Transaction) -> None:
                    await pending.release(tx, KIND, heads)

                await release()
            except Exception:
                logger.exception("Could not give back the claims of a failed batch")
            raise
        stats = self.stats
        stats.batches += 1
        stats.heads += len(claimed)
        stats.new += counts["new"]
        stats.removed += counts["removed"]
        stats.rows += found.rows
        stats.overflows += len(found.overflowed)
        stats.seconds_finding += found_at - began
        stats.seconds_writing += time.monotonic() - found_at
        stats.last_batch_at = time.time()
        logger.debug(
            "Derived: %s heads, %s rows, %s new, %s removed (%.0f ms finding, %.0f ms writing)",
            len(claimed),
            found.rows,
            counts["new"],
            counts["removed"],
            (found_at - began) * 1000,
            (time.monotonic() - found_at) * 1000,
        )
        return len(claimed)

    async def drain(self) -> int:
        """Do every batch there is now. Gives how many heads were done"""
        done = 0
        while True:
            claimed = await self.process_batch()
            if not claimed:
                return done
            done += claimed
            await self.take_lease()

    # -- rules --

    async def sync_rules(self, force: list[str] | None = None) -> dict[str, str]:
        """Bring the stored facts of each rule up to date with the rule: build again a new rule, a changed one, one
        whose last build did not finish, and those in `force`; remove what a removed rule derived. Gives what was done
        to each"""
        db = database()

        @db.read_transaction
        async def states(tx: Transaction) -> dict[str, dict[str, Any]]:
            return await store.rule_states(tx)

        known = await states()
        done: dict[str, str] = {}
        for name, rule in DerivedRegistry.checked.items():
            state = known.get(name)
            if (
                force is not None
                and name in force
                or state is None
                or state["hash"] != rule.hash
                or state["state"] != "ready"
            ):
                await self.rebuild(rule)
                done[name] = "built"
        for name in known:
            if name not in DerivedRegistry.checked:
                await self.remove_rule(name)
                done[name] = "removed"
        return done

    async def rebuild(self, rule: CheckedRule) -> dict[str, Any]:
        """Derive everything the rule derives, from all the nodes of the class of one of its places (the one with
        fewest), keeping what is there and is found again; then delete what was not found"""
        db = database()
        settings = self.settings
        generation = str(uuid.uuid4())
        began = time.monotonic()

        @db.write_transaction
        async def mark(tx: Transaction, state: str) -> None:
            await store.set_rule_state(tx, rule.name, rule.hash, state)

        await mark("building")

        @db.read_transaction
        async def sizes(tx: Transaction) -> list[tuple[int, Any]]:
            return [
                (await store.count_of_class(tx, seed.model.__name__), seed)
                for seed in rule.seeds
            ]

        _, seed = min(await sizes(), key=lambda pair: pair[0])

        @db.read_transaction
        async def all_ids(tx: Transaction) -> list[str]:
            return await store.ids_of_class(tx, seed.model.__name__)

        ids = await all_ids()
        counts = {"seeds": len(ids), "rows": 0, "new": 0, "removed": 0, "overflows": 0}
        for start in range(0, len(ids), settings.rebuild_chunk):
            chunk = ids[start : start + settings.rebuild_chunk]
            found = store.Found()

            @db.read_transaction
            async def find(
                tx: Transaction, chunk: list[str], found: store.Found
            ) -> None:
                await store.run_seeded(tx, rule, seed.node, chunk, found)

            await find(chunk, found)
            written = await store.write_found(db, found, generation=generation)
            if found.overflowed:

                @db.write_transaction
                async def overflowed(tx: Transaction, seeds: list[str]) -> None:
                    for node in seeds:
                        await store.count_overflow(tx, rule.name, node)

                await overflowed(list(found.overflowed))
            counts["rows"] += found.rows
            counts["new"] += written["new"]
            counts["overflows"] += len(found.overflowed)
            await self.take_lease()
        counts["removed"] = await self.remove_justifications(rule.name, generation)
        await mark("ready")
        counts["seconds"] = round(time.monotonic() - began, 3)
        self.stats.rebuilds[rule.name] = counts
        logger.info("Rule %s built: %s", rule.name, counts)
        return counts

    async def remove_justifications(self, rule: str, generation: str | None) -> int:
        db = database()
        removed = 0
        while True:

            @db.write_transaction
            async def remove(tx: Transaction) -> int:
                return await store.remove_justifications(
                    tx, rule, generation, self.settings.remove_chunk
                )

            gone = await remove()
            removed += gone
            if gone < self.settings.remove_chunk:
                return removed

    async def remove_rule(self, name: str) -> None:
        await self.remove_justifications(name, None)
        db = database()

        @db.write_transaction
        async def forget(tx: Transaction) -> None:
            await (
                await tx.run(
                    f"MATCH (r:{store.RULE_STATE} {{name: $name}}) DELETE r",
                    name=name,
                )
            ).consume()

        await forget()
        logger.info("Rule %s removed, with what it derived", name)

    # -- the loop --

    async def run(self, settings: Any = None) -> None:
        """Runs until cancelled (a `BackgroundTask`)"""
        self._loop = asyncio.get_running_loop()
        self._wake = asyncio.Event()
        try:
            while not await self.take_lease():
                await asyncio.sleep(self.settings.idle)
            await self.sync_rules()
            batch, delay = self.settings.batch, 1.0
            while True:
                self._wake.clear()
                try:
                    await self.drain()
                except Exception:
                    # (most often a write that met saves too many times: the claims were given back. Smaller batches
                    # meet fewer; the size grows back as they go through)
                    self.stats.failures += 1
                    self.settings.batch = max(10, self.settings.batch // 2)
                    logger.warning(
                        "Derived: a batch failed; trying again in %.0f s, %s heads at a time",
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
            try:
                await self.give_up_lease()
            except Exception:
                logger.debug("The lease was not given up", exc_info=True)


# The worker of this process (the server's background task; the tests' `run_pending_derivations`)
worker = Worker()


async def run_pending_derivations() -> dict[str, Any]:
    """Bring every rule up to date, and do all the pending work now (for tests and scripts: no waiting for the
    background). Gives what was done"""
    await worker.take_lease()
    try:
        rules = await worker.sync_rules()
        heads = await worker.drain()
    finally:
        await worker.give_up_lease()
    return {"rules": rules, "heads": heads}


async def pending_status() -> dict[str, Any]:
    db = database()

    @db.read_transaction
    async def read(tx: Transaction) -> dict[str, Any]:
        return {
            "pending": await pending.count(tx, KIND),
            "rules": await store.rule_states(tx),
        }

    return await read()
