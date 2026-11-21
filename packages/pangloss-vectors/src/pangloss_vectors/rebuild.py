"""A rebuild: every vector of a part (or of every part) computed again into a new generation, the profiles that weigh
it combined from it, the switch, and the old generations dropped (`pangloss vectors rebuild`, the admin job
`vectors_rebuild`). A search meanwhile reads the generation in use, whole, until the switch.

Only one rebuild runs on a database at a time: it holds a lease (`PGVectorsRebuild`), taken under the backend's lock
(`ensure_lock`, `lock`) so that two cannot take it at once, renewed while it runs, and given up at the end. A second
rebuild is refused (`VectorsRebuildBusy`, which names who holds it and since when); a lease that was not given up (the
process stopped) runs out after `LEASE_SECONDS`. (Two rebuilds at once would take the same generation numbers.)

(implementation_docs/vectors.md, "Rebuild and status")
"""

import asyncio
import contextlib
import dataclasses
import datetime
import os
import socket
import time
import uuid
from collections.abc import AsyncGenerator, Callable, Iterable
from typing import Any

from pangloss_core import backend
from pangloss_models import PanglossRuntimeError

from pangloss_vectors import store
from pangloss_vectors.parts import Part, VectorRow, part, parts, profiles
from pangloss_vectors.settings import graph_sees
from pangloss_vectors.status import part_reasons, unavailable

LEASE = "PGVectorsRebuild"
LOCK_KEY = "pangloss_vectors.rebuild"
# (seconds a lease holds unless renewed; it is renewed four times as often)
LEASE_SECONDS = 60.0

type Progress = Callable[[int, int, str], None]


class VectorsRebuildBusy(PanglossRuntimeError):
    """Another rebuild holds the lease of this database: a rebuild does not run beside it"""


@dataclasses.dataclass(frozen=True)
class PartRebuilt:
    part: str
    generation: int
    count: int
    seconds: float
    dropped: int
    """Vectors of older generations deleted"""


@dataclasses.dataclass(frozen=True)
class ProfileRebuilt:
    profile: str
    generation: int
    count: int
    seconds: float
    dropped: int
    why: str
    """`"with the X part"`, or why it was combined again alone (its weights changed, it was never built)"""


@dataclasses.dataclass
class Rebuilt:
    """What a rebuild did"""

    parts: list[PartRebuilt] = dataclasses.field(default_factory=list)
    profiles: list[ProfileRebuilt] = dataclasses.field(default_factory=list)
    skipped: dict[str, str] = dataclasses.field(default_factory=dict)
    """What was not done, and why: by `part <name>` or `profile <name>`"""
    seconds: float = 0.0


# ---------------------------------------------------------------------------
# The lease
# ---------------------------------------------------------------------------


TAKE_QUERY = f"""
MERGE (l:{LEASE} {{key: 'rebuild'}})
RETURN l.holder AS holder, l.by AS by, l.since AS since, l.until AS until
"""

HOLD_QUERY = f"""
MATCH (l:{LEASE} {{key: 'rebuild'}})
SET l.holder = $me, l.by = $by, l.since = $since, l.until = $until
"""

RENEW_QUERY = f"""
MATCH (l:{LEASE} {{key: 'rebuild'}}) WHERE l.holder = $me
SET l.until = $until
RETURN count(l) AS kept
"""

GIVE_UP_QUERY = f"""
MATCH (l:{LEASE} {{key: 'rebuild'}}) WHERE l.holder = $me
REMOVE l.holder, l.by, l.since, l.until
"""


def _who() -> str:
    from pangloss_users import current_request_username

    user = current_request_username.get()
    where = f"process {os.getpid()} on {socket.gethostname()}"
    # (a command, or a job, is no user's: the default name says nothing)
    return f"{user} ({where})" if user and user != "pangloss_default_user" else where


class Lease:
    """The lease of one rebuild"""

    def __init__(self, seconds: float = LEASE_SECONDS) -> None:
        self.id = str(uuid.uuid4())
        self.seconds = seconds
        self.lost = False

    async def take(self) -> None:
        """Take the lease, or raise `VectorsRebuildBusy` naming who holds it"""
        current = backend.current()
        await current.ensure_lock(LOCK_KEY)
        database = current.database()
        now = time.time()

        @database.write_transaction
        async def take(tx: Any) -> tuple[str, float] | None:
            await current.lock(tx, LOCK_KEY)
            record = await (await tx.run(TAKE_QUERY)).single()
            if (
                record is not None
                and record["holder"] not in (None, self.id)
                and (record["until"] or 0) > now
            ):
                return record["by"] or "another rebuild", record["since"] or now
            await (
                await tx.run(
                    HOLD_QUERY,
                    me=self.id,
                    by=_who(),
                    since=now,
                    until=now + self.seconds,
                )
            ).consume()
            return None

        held = await take()
        if held is not None:
            by, since = held
            when = datetime.datetime.fromtimestamp(since, datetime.UTC).strftime(
                "%Y-%m-%d %H:%M:%S UTC"
            )
            raise VectorsRebuildBusy(
                f"Another rebuild of the vectors is running on this database: {by}, since {when}. Wait for it to "
                f"finish (a rebuild that was stopped gives the lease up after {self.seconds:g} s)"
            )

    async def renew(self) -> bool:
        database = backend.current().database()

        @database.write_transaction
        async def renew(tx: Any) -> bool:
            record = await (
                await tx.run(RENEW_QUERY, me=self.id, until=time.time() + self.seconds)
            ).single()
            return bool(record and record["kept"])

        return await renew()

    async def give_up(self) -> None:
        database = backend.current().database()

        @database.write_transaction
        async def give_up(tx: Any) -> None:
            await (await tx.run(GIVE_UP_QUERY, me=self.id)).consume()

        await give_up()

    def check(self) -> None:
        """Raise if the lease was lost (it ran out, and another rebuild took it)"""
        if self.lost:
            raise VectorsRebuildBusy(
                "The rebuild's lease ran out and another rebuild took it: this one stopped"
            )

    @contextlib.asynccontextmanager
    async def kept(self) -> AsyncGenerator[None]:
        """Renewed in the background while the block runs; given up after it"""

        async def keep() -> None:
            while True:
                await asyncio.sleep(self.seconds / 4)
                try:
                    if not await self.renew():
                        self.lost = True
                        return
                except Exception:  # noqa: BLE001
                    # (tried again at the next beat: the lease holds for four)
                    continue

        task = asyncio.create_task(keep())
        try:
            yield
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            await self.give_up()


# ---------------------------------------------------------------------------
# A rebuild
# ---------------------------------------------------------------------------


async def _rebuild_part(
    made: Part, lease: Lease, done: Rebuilt, combined_now: set[str]
) -> None:
    started = time.monotonic()
    generation = await store.next_generation()
    written = 0

    async def write(rows: Iterable[VectorRow]) -> None:
        nonlocal written
        lease.check()
        written += await store.write_generation(made.name, generation, rows)

    await made.rebuild(write)
    part_seconds = time.monotonic() - started
    combined: list[tuple[store.Combined, float]] = []
    for offset, profile_name in enumerate(store.profiles_weighing(made.name), start=1):
        lease.check()
        begun = time.monotonic()
        combined.append(
            (
                await store.combine(
                    profile_name,
                    generation + offset,
                    using={made.name: generation},
                ),
                time.monotonic() - begun,
            )
        )
    lease.check()
    await store.switch(
        store.Built(
            made.name,
            generation,
            written,
            signature=made.signature(),
            graph_sees=graph_sees(),
        ),
        [made_ for made_, _ in combined],
    )
    begun = time.monotonic()
    dropped = await store.drop_older(made.name, generation)
    done.parts.append(
        PartRebuilt(
            made.name,
            generation,
            written,
            round(part_seconds + time.monotonic() - begun, 3),
            dropped,
        )
    )
    for made_, seconds in combined:
        begun = time.monotonic()
        gone = await store.drop_older_profile(made_.profile, made_.generation)
        done.profiles.append(
            ProfileRebuilt(
                made_.profile,
                made_.generation,
                made_.count,
                round(seconds + time.monotonic() - begun, 3),
                gone,
                f"with the {made.name} part",
            )
        )
        combined_now.add(made_.profile)


def _recombine_reason(
    name: str, weights: dict[str, float], state: store.ProfileState | None
) -> str | None:
    """Why a profile not combined in this rebuild is combined again alone: it was never built, or its weights or
    dimension are not those of its state"""
    lay = store.layout(name, weights)
    if state is None:
        return "it had never been built"
    if dict(state.weights) != dict(lay.weights):
        return "its weights changed"
    if state.dimension != lay.dimension:
        return "its dimension changed"
    return None


async def _recombine(name: str, why: str, lease: Lease, done: Rebuilt) -> None:
    lease.check()
    begun = time.monotonic()
    made = await store.combine(name, await store.next_generation())
    lease.check()
    await store.switch(None, [made])
    gone = await store.drop_older_profile(name, made.generation)
    done.profiles.append(
        ProfileRebuilt(
            name,
            made.generation,
            made.count,
            round(time.monotonic() - begun, 3),
            gone,
            why,
        )
    )


async def rebuild(
    part_name: str | None = None, *, progress: Progress | None = None
) -> Rebuilt:
    """Rebuild one part (`part_name`) or every registered part, in the order of their names: a new generation of its
    vectors, each profile that weighs it combined from that, the switch, the older generations dropped. Then each
    profile not combined so whose weights or dimension are not those it was built with (or that was never built) is
    combined again from the parts in use, unless one of its parts is due for a rebuild itself. A part whose
    `requires` the backend lacks is skipped and said. Raises `VectorsRebuildBusy` if another rebuild is running"""
    started = time.monotonic()
    names = [part(part_name).name] if part_name is not None else list(parts())
    done = Rebuilt()
    lease = Lease()
    await lease.take()
    async with lease.kept():
        combined_now: set[str] = set()
        steps = len(names) + 1
        for step, name in enumerate(names, start=1):
            made = part(name)
            if progress is not None:
                progress(step, steps, f"the {name} part")
            why_not = unavailable(made)
            if why_not is not None:
                done.skipped[f"part {name}"] = why_not
                continue
            await _rebuild_part(made, lease, done, combined_now)
        if progress is not None:
            progress(steps, steps, "the profiles")
        found = await store.states()
        sees = graph_sees()
        for name, weights in profiles().items():
            if name in combined_now or not weights:
                continue
            why = _recombine_reason(name, weights, found.profiles.get(name))
            if why is None:
                continue
            behind = [
                p
                for p in sorted(weights)
                if p in found.parts
                and unavailable(part(p)) is None
                and part_reasons(part(p), found.parts[p], sees)
            ]
            if behind:
                done.skipped[f"profile {name}"] = (
                    f"{why}, but the {', '.join(behind)} part it weighs has to be rebuilt first "
                    f"(pangloss vectors rebuild --part {behind[0]})"
                )
                continue
            await _recombine(name, why, lease, done)
    done.seconds = round(time.monotonic() - started, 3)
    return done
