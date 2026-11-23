"""The worker that suggests who the stand-ins of a document are (step 10.5d of implementation_docs/similarity-build-plan.md;
implementation_docs/reconcile.md, "The worker that suggests"): Pangloss's own toolchain.

A save of a document that may hold a stand-in leaves it marked (`marking.py`, the kind `reconcile`). The worker, in a
loop, claims a few marked heads, the oldest first and only those whose writes have reached the vectors (below), and
for each, cheapest first:

1. **is it to be touched at all**: the head read once (`rewriting.read_head`). Left alone, its mark completed and why
   logged (at info), when it is gone or deleted, published (`meta.published`: the user's word, only unpublished
   documents), of a class people do not write, or holding no stand-in now (`marking.suggestible`), or its stored
   form cannot be planned (`stored.Unplannable`);
2. **its stand-ins**: of its stored plan, read once (`stored.plan_of_view`), the unknowns (`unknowns_of`), each
   skipped while it was tried with today's digest (`PGReconcileTried`, `digest`: what the decision is made of today,
   and the stand-in's own label, class and URIs);
3. **which shape its place takes**, by trial (`rewriting.prepare_rewrite`, nothing written): the stand-in replaced by
   a `RECONCILE_SUGGEST_AS` whose target is one `WeightedAlternative` of a placeholder at 100 per cent, then one
   placeholder entity (`target_of`, the one place the two shapes are made); neither validates: the stand-in is left,
   and noted as tried;
4. **is a part it would change cited** (`cited`: a citation, from a document that is not deleted, of the stand-in, of
   a node above it, of the head, or of any node of a head whose class cites the field it is in with it,
   `cited_with`): the head is left whole, its mark completed, logged. Asked by a read before any candidate is
   asked; the update's own refusal (`PanglossCitedError`) stays behind it, as any other refusal;
5. **the candidates** of those left, as the stored route asks them (`candidates_of(plan, see_unpublished=True,
   limit=candidates.DISPLAYED, only=...)`), in groups of at most `RECONCILE_MOST_UNKNOWNS`; the fit in use read once
   for the batch; `suggest.decide_for` for each. A stand-in whose candidates are not `ok` (the profile not built, a
   rebuild due) is left, not noted as tried;
6. `judged` (a project's judge, step 10.5c', to come): the decision unchanged;
7. **one update**, if anything was decided (`rewriting.rewrite`, based on the version read, as the toolchain user
   `RECONCILE_TOOLCHAIN`, `instructions={"suggest": False}`, which takes the head's mark off in the update's own
   transaction): each stand-in decided replaced by a suggestion with a new id (`text` its label, `uris` its URIs,
   `identified_by` the toolchain, `toolchain_version` the profile and the fit used, the target in the shape found,
   the relation's own properties kept). A version that moved on (`PanglossVersionConflictError`): nothing written,
   the claim given back, the mark kept. Any other refusal: logged, the mark completed, the stand-ins noted as tried.
   A failure that is not a refusal: the claims given back, the error raised. Nothing decided: the mark completed by
   its token, the stand-ins noted as tried;
8. **what it saw is kept** (`PGReconcileSuggested`, one for each suggestion, by its id: the head, the stand-in, when,
   the rows of `Found.best` with `displayed` the list decided on, the alternatives and their shape, today's
   signatures; no user) and the stand-ins left (`PGReconcileTried`), **in the update's own transaction**
   (`hooks.in_write`, while `marking.keeping` names the head), so that nothing can be written without the other.

**Waiting.** A batch is not claimed while a rebuild of the vectors holds its lease, and only marks made before the
oldest mark of the vectors' kind are claimed (the writes that left them have reached the vectors); the worker's own
updates leave vectors marks newer than any mark it would claim, and are not waited for. With `pangloss_vectors`
installed and its worker never running, nothing is claimed, and `pending_status` says so.

**One worker at a time** (a lease on the `PGReconcileWorker` node, as the vectors worker's), few heads claimed at a
time (`Settings.batch`, 5), the lease and the claims renewed while it works (a mention asked takes 1 to 2.5 s at size).
The toolchain is checked before each batch (`toolchain_user`): made if absent (kind `toolchain`, nothing to log in
with), refused, and the worker stopped, if it is a person or disabled (`ToolchainRefused`)."""

import asyncio
import contextlib
import dataclasses
import datetime
import hashlib
import json
import logging
import time
import uuid
from collections.abc import AsyncGenerator, Collection, Iterable, Mapping, Sequence
from typing import Any, Literal
from uuid import UUID

from pangloss_core import Transaction, backend
from pangloss_cypher import fragments, pending
from pangloss_models import (
    PanglossInitialisationError,
    PanglossReadOnlyError,
    PanglossUserDisabledError,
    PanglossUserNotFoundError,
    PanglossVersionConflictError,
    PanglossWriteError,
    rewriting,
)
from pydantic import ValidationError

from pangloss_reconcile import decisions, marking, settings
from pangloss_reconcile.marking import KIND
from pangloss_reconcile.suggest import Alternative, Decision

logger = logging.getLogger("pangloss.reconcile.worker")

LEASE_LABEL = "PGReconcileWorker"
SUGGESTED = "PGReconcileSuggested"
TRIED = "PGReconcileTried"

# What `target_of` makes: a `WeightedAlternative` of the library (by its name: this package does not import the
# library) with each alternative's `percent`, or the one entity
WEIGHTED = "WeightedAlternative"
PERCENT = "percent"
type Shape = Literal["alternatives", "one"]
SHAPES: tuple[Shape, ...] = ("alternatives", "one")

# What a refusal of the update is not: the database being migrated, the toolchain gone or disabled since it was
# checked. The claims are given back and the error raised, as for any failure
NOT_REFUSALS = (
    PanglossReadOnlyError,
    PanglossUserNotFoundError,
    PanglossUserDisabledError,
)

# The toolchain's full name, when the worker makes it
TOOLCHAIN_NAME = "Pangloss's reconciliation"


@dataclasses.dataclass
class Settings:
    batch: int = 5
    """Heads claimed at once (few: each may take seconds a stand-in)"""
    lease: float = 30.0
    """Seconds the worker's lease and its claims hold, unless renewed (renewed every quarter of it while it works)"""
    idle: float = 10.0
    """Seconds between looks for work when nothing wakes it"""
    paused: float = 1.0
    """Seconds between looks while it waits for the vectors"""


@dataclasses.dataclass
class Stats:
    batches: int = 0
    heads: int = 0
    updates: int = 0
    """Documents written with suggestions"""
    suggestions: int = 0
    tried: int = 0
    """Stand-ins left and noted as tried"""
    left: dict[str, int] = dataclasses.field(default_factory=dict)
    """Heads left alone, by why"""
    conflicts: int = 0
    refused: int = 0
    waiting: int = 0
    """Turns that claimed nothing while marks were waiting for the vectors, or a rebuild held its lease"""
    failures: int = 0
    last_batch_at: float | None = None


class ToolchainRefused(Exception):
    """`RECONCILE_TOOLCHAIN` names a person, or a user who is disabled: the worker does not write as them, and stops"""


@dataclasses.dataclass(frozen=True)
class Outcome:
    """What became of one claimed head: `written` (an update with suggestions), `nothing` (nothing decided: the mark
    completed), `left` (left alone, `why`: the mark completed), `conflict` (the version moved on: the claim given
    back, the mark kept), `refused` (the update was refused, `why`: the mark completed)"""

    head: str
    what: Literal["written", "nothing", "left", "conflict", "refused"]
    why: str = ""
    suggestions: int = 0
    tried: int = 0


@dataclasses.dataclass(frozen=True)
class Seen:
    """What a batch is decided by, read once for it: the states of the vectors, today's signatures, the "none of
    these" model of the fit in use when it can be used (and its id), the toolchain, and the digest of the settings of
    the decision"""

    states: Any
    today: dict[str, Any]
    fit: Any
    fit_id: str | None
    toolchain: str
    decided_by: str


def database() -> Any:
    return backend.current().database()


# --- the shapes of a suggestion ----------------------------------------------------------------------------------


def target_of(
    shape: Shape, alternatives: Sequence[Alternative]
) -> list[dict[str, Any]]:
    """The target of a suggestion in a shape, from the alternatives decided (the likeliest first): one
    `WeightedAlternative` of them all with their per cent, or the first alone"""
    if not alternatives:
        raise ValueError("A suggestion has one alternative or more")
    if shape == "alternatives":
        return [
            {
                "type": WEIGHTED,
                "alternatives": [
                    {
                        "type": one.type,
                        "id": one.id,
                        "edge_properties": {PERCENT: one.percent},
                    }
                    for one in alternatives
                ],
            }
        ]
    first = alternatives[0]
    return [{"type": first.type, "id": first.id}]


def suggestion(
    part: Mapping[str, Any],
    shape: Shape,
    alternatives: Sequence[Alternative],
    *,
    id: Any,
    suggest_as: str,
    toolchain: str,
    version: str,
) -> dict[str, Any]:
    """What a stand-in (`part`, as an `Update` takes it) becomes: a `suggest_as` of a new id, its label as `text`, its
    URIs, the toolchain and its version, the target in the shape, and the properties of the relation to it kept (as
    review's reconciliation keeps them)"""
    made: dict[str, Any] = {
        "type": suggest_as,
        "id": id,
        "text": part.get("label") or "",
        "uris": [str(uri) for uri in part.get("uris") or ()],
        "identified_by": toolchain,
        "toolchain_version": version,
        "target": target_of(shape, alternatives),
    }
    if part.get("edge_properties") is not None:
        made["edge_properties"] = part["edge_properties"]
    return made


def placeholder_type(type_name: str) -> str:
    """A class of entity a placeholder of what a stand-in stands for may be: the class, or the first below it that is
    not abstract"""
    from pangloss_vectors.fields import NotAClass, classes_of

    try:
        found = classes_of(type_name)
    except NotAClass:
        return type_name
    return type_name if type_name in found else (found[0] if found else type_name)


def toolchain_version(seen: Seen) -> str:
    """What the worker's suggestions say was used: the profile, and the fit in use when it was used"""
    used = f"profile {seen.today['profile']}"
    return used if seen.fit_id is None else f"{used}, fit {seen.fit_id}"


# --- what has been tried -----------------------------------------------------------------------------------------


def decided_by(fit_id: str | None) -> str:
    """The settings a decision is made by, as text: what a stand-in tried is noted with, beside today's signatures"""
    from pangloss_reconcile.candidates import DISPLAYED

    return json.dumps(
        {
            "above": settings.suggest_above(),
            "most": settings.suggest_most(),
            "within": settings.suggest_within(),
            "new_above": settings.new_above(),
            "fit": fit_id,
            "as": settings.suggest_as(),
            "displayed": DISPLAYED,
        },
        sort_keys=True,
    )


def digest(
    today: Mapping[str, Any], decided: str, unknown: Any, uris: Iterable[Any]
) -> str:
    """What a stand-in is tried by: today's signatures (`decisions.today`), the settings of the decision
    (`decided_by`), and the stand-in's own label, class and URIs (a stand-in edited is asked again). A stand-in is
    skipped while what it was noted with is this"""
    text = json.dumps(
        {
            "today": {name: today[name] for name in decisions.SIGNATURES},
            "decided": decided,
            "stand_in": [unknown.label, unknown.type, sorted(str(uri) for uri in uris)],
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(text.encode()).hexdigest()


TRIED_READ_QUERY = f"""
UNWIND $ids AS id
MATCH (t:{TRIED} {{stand_in: id}})
RETURN t.stand_in AS stand_in, t.digest AS digest
"""

TRIED_WRITE_QUERY = f"""
UNWIND $rows AS row
MERGE (t:{TRIED} {{stand_in: row.stand_in}})
SET t.head = row.head, t.digest = row.digest, t.at = row.at
"""

SUGGESTED_WRITE_QUERY = f"""
UNWIND $rows AS row
MERGE (s:{SUGGESTED} {{id: row.id}})
SET s += row
"""

FORGET_ALL_QUERY = f"MATCH (t:{TRIED}) DELETE t RETURN count(*) AS n"

FORGET_QUERY = f"""
MATCH (t:{TRIED})
WHERE t.head IN $heads
DELETE t
RETURN count(*) AS n
"""


async def tried_of(ids: Collection[str]) -> dict[str, str]:
    """The digests the stand-ins of these ids were tried with"""
    if not ids:
        return {}

    @database().read_transaction
    async def read(tx: Transaction) -> dict[str, str]:
        result = await tx.run(TRIED_READ_QUERY, ids=sorted(ids))
        return {row["stand_in"]: row["digest"] async for row in result}

    return await read()


async def forget_tried(heads: Collection[str] | None = None) -> int:
    """Forget that the stand-ins of these heads (all, with None) were tried, so that the worker asks again for them
    when it is next given them (`pangloss reconcile suggest --again`, step 10.5e). Gives how many were forgotten"""

    @database().write_transaction
    async def forget(tx: Transaction) -> int:
        if heads is None:
            record = await (await tx.run(FORGET_ALL_QUERY)).single()
        else:
            record = await (
                await tx.run(FORGET_QUERY, heads=sorted(str(h) for h in heads))
            ).single()
        return int(record["n"]) if record else 0

    return await forget()


async def _note_tried(tx: Transaction, rows: list[dict[str, Any]]) -> None:
    if rows:
        await (await tx.run(TRIED_WRITE_QUERY, rows=rows)).consume()


@dataclasses.dataclass(frozen=True)
class Kept:
    """What the worker keeps in its update's transaction (`marking.keeping`): the head, the rows of each suggestion,
    and the stand-ins left"""

    head: str
    suggested: list[dict[str, Any]]
    tried: list[dict[str, Any]]


async def write_kept(tx: Transaction, op: str, id: Any, kept: Kept) -> None:
    """(`marking.in_write`) in the transaction of the worker's update of `kept.head`, and of no other write: what it
    keeps. (The transaction may be run again: it is `MERGE`d by id)"""
    if op != "update" or str(id) != kept.head:
        return
    if kept.suggested:
        await (await tx.run(SUGGESTED_WRITE_QUERY, rows=kept.suggested)).consume()
    await _note_tried(tx, kept.tried)


# --- the sweep ---------------------------------------------------------------------------------------------------

# (a suggestion no longer a node of a document of a class of suggestion: confirmed, which keeps the node and changes
# its class, or gone)
SWEEP_SUGGESTED_QUERY = f"""
MATCH (s:{SUGGESTED})
OPTIONAL MATCH (n:PGIndexableNode {{id: s.id}})
WITH s, n
WHERE n IS NULL OR n.head_node_id IS NULL OR NOT any(label IN labels(n) WHERE label IN $kinds)
DELETE s
RETURN count(*) AS n
"""

SWEEP_TRIED_QUERY = f"""
MATCH (t:{TRIED})
OPTIONAL MATCH (n:PGIndexableNode {{id: t.stand_in}})
WITH t, n
WHERE n IS NULL OR n.head_node_id IS NULL
DELETE t
RETURN count(*) AS n
"""


async def sweep_kept() -> tuple[int, int]:
    """(`decisions.sweep`) Remove what the worker kept that nothing can use now: the rows of a suggestion that is no
    longer one (confirmed, or gone), never by age; and the stand-ins tried that are no longer in a document. Gives
    how many of each went"""
    from pangloss_models import hooks

    kinds = hooks.unconfirmed_classes() or [settings.suggest_as()]

    @database().write_transaction
    async def remove(tx: Transaction) -> tuple[int, int]:
        suggested = await (await tx.run(SWEEP_SUGGESTED_QUERY, kinds=kinds)).single()
        tried = await (await tx.run(SWEEP_TRIED_QUERY)).single()
        return (
            int(suggested["n"]) if suggested else 0,
            int(tried["n"]) if tried else 0,
        )

    return await remove()


# --- who it writes as ----------------------------------------------------------------------------------------------


async def toolchain_user() -> str:
    """The username the worker writes as (`RECONCILE_TOOLCHAIN`): made, a user of kind `toolchain` with nothing to
    log in with, if there is none; `ToolchainRefused` if it is a person or disabled"""
    from pangloss_users import PanglossUserExistsError, service

    name = settings.toolchain()
    user = await service.get_user(name)
    if user is None:
        try:
            await service.create_toolchain(name, TOOLCHAIN_NAME)
            logger.info(
                "Reconcile: the toolchain %r was made, to write suggestions as", name
            )
        except PanglossUserExistsError:
            # (made meanwhile, by another worker or a person: looked at again)
            user = await service.get_user(name)
    if user is not None:
        if user.kind != "toolchain":
            raise ToolchainRefused(
                f"RECONCILE_TOOLCHAIN names {name!r}, who is a person, not a toolchain: the worker writes its "
                "suggestions only as a toolchain. Name another (one that is not there is made)"
            )
        if user.disabled:
            raise ToolchainRefused(
                f"RECONCILE_TOOLCHAIN names {name!r}, a toolchain that is disabled: the worker does not write as "
                "it. Enable it, or name another"
            )
    return name


@contextlib.contextmanager
def as_toolchain(name: str):
    """The writes in the block are the toolchain's (`current_request_username`, as the commands set it), and it sees
    what is not published"""
    from pangloss_users import current_request_username, see_unpublished

    user = current_request_username.set(name)
    seeing = see_unpublished.set(True)
    try:
        yield
    finally:
        see_unpublished.reset(seeing)
        current_request_username.reset(user)


# --- what is cited ------------------------------------------------------------------------------------------------


def _above(plan: Any) -> dict[str, tuple[str, str]]:
    """Of each node of the plan below its head, the node it is in and the field it is in there"""
    from pangloss_cypher.write_plan import PlannedNode

    found: dict[str, tuple[str, str]] = {}
    for source, relation, _first in plan.walk():
        if isinstance(relation.target, PlannedNode):
            found.setdefault(relation.target.id, (source.id, relation.edges[0][0]))
    return found


def cited_among(
    head_id: str,
    head_model: Any,
    plan: Any,
    stand_ins: Iterable[str],
    targets: Collection[str],
) -> list[str]:
    """Which of the stand-ins sit in a part something cites (`targets`, the ids of what is cited of the head): the
    stand-in, a node above it, or the head; or any node of the head, when the head's class cites the field the
    stand-in is in with every part (`Document.Meta(cited_with=[...])`). No database in it"""
    if not targets:
        return []
    above = _above(plan)
    with_head = set(
        getattr(getattr(head_model, "_meta", None), "cited_with", None) or ()
    )
    part_cited = any(target != head_id for target in targets)
    found = []
    for stand_in in stand_ins:
        chain = [stand_in]
        field = None
        while chain[-1] in above:
            parent, field = above[chain[-1]]
            chain.append(parent)
        if any(node in targets for node in chain) or (
            part_cited and field is not None and field in with_head
        ):
            found.append(stand_in)
    return found


async def cited_targets(head_id: str) -> set[str]:
    """What is cited of a head, by documents that are not deleted (published or not): the ids of the nodes"""
    from pangloss_cypher import citations

    if not citations.any_citations():
        return set()

    # (the core's own reader of what cites a head: given the backend's transaction, as the core's writes give theirs)
    @database().read_transaction
    async def read(tx: Any) -> set[str]:
        return {str(row["target"]) for row in await citations.citing(tx, head_id)}

    return await read()


# --- the worker ----------------------------------------------------------------------------------------------------

HEAD_QUERY = f"""
MATCH (head:HeadNode {{id: $id}})
RETURN head.type AS type, {fragments.deleted("head")} AS deleted
"""

REBUILD_HELD_QUERY = """
MATCH (l:{label} {{key: 'rebuild'}})
RETURN l.holder AS holder, l.until AS until
"""

OLDEST_QUERY = """
MATCH (p:PGPending)
WHERE p.kind = $kind
RETURN min(p.at) AS oldest
"""

WAITING_QUERY = """
MATCH (p:PGPending)
WHERE p.kind = $kind AND p.at >= $before
RETURN count(p) AS waiting
"""

LEASE_READ_QUERY = f"""
MATCH (w:{LEASE_LABEL} {{kind: $kind}})
RETURN w.holder AS holder, w.until AS until
"""


def _vectors_installed() -> bool:
    from pangloss_vectors import installed

    return installed()


async def _waiting(tx: Transaction) -> tuple[bool, float | None]:
    """Whether a rebuild of the vectors holds its lease now, and when the oldest mark of the vectors' kind was made
    (None: there is none, or the vectors are not installed)"""
    if not _vectors_installed():
        return False, None
    from pangloss_vectors import KIND as VECTORS
    from pangloss_vectors.rebuild import LEASE as REBUILD_LEASE

    held = await (await tx.run(REBUILD_HELD_QUERY.format(label=REBUILD_LEASE))).single()
    rebuilding = (
        held is not None
        and held["holder"] is not None
        and (held["until"] or 0) > time.time()
    )
    oldest = await (await tx.run(OLDEST_QUERY, kind=VECTORS)).single()
    return rebuilding, (oldest["oldest"] if oldest else None)


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

    # -- the lease --

    async def take_lease(self) -> bool:
        """Whether this worker is the one that works (it takes the lease, or renews it)"""
        now = time.time()

        @database().write_transaction
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
        @database().write_transaction
        async def give(tx: Transaction) -> None:
            await (
                await tx.run(
                    f"MATCH (w:{LEASE_LABEL} {{kind: $kind, holder: $me}}) REMOVE w.holder, w.until",
                    kind=KIND,
                    me=self.id,
                )
            ).consume()

        await give()

    # -- claiming --

    async def claim(self) -> list[tuple[str, str]] | None:
        """Claim a few marked heads, the oldest first, of those marked before the oldest mark of the vectors; None if
        a rebuild of the vectors holds its lease (nothing is claimed)"""
        settings_ = self.settings

        @database().write_transaction
        async def claim(tx: Transaction) -> list[tuple[str, str]] | None:
            rebuilding, before = await _waiting(tx)
            if rebuilding:
                return None
            return await pending.claim(
                tx, KIND, settings_.batch, settings_.lease, before=before
            )

        return await claim()

    async def renew(self, claimed: list[tuple[str, str]]) -> None:
        """The lease and the claims, given more time"""

        @database().write_transaction
        async def renew(tx: Transaction) -> None:
            await pending.renew(tx, KIND, claimed, self.settings.lease)

        await self.take_lease()
        await renew()

    @contextlib.asynccontextmanager
    async def held(self, claimed: list[tuple[str, str]]) -> AsyncGenerator[None]:
        """The lease and the claims renewed in the background while the block runs"""

        async def keep() -> None:
            while True:
                await asyncio.sleep(self.settings.lease / 4)
                try:
                    await self.renew(claimed)
                except Exception:  # noqa: BLE001
                    # (tried again at the next beat: they hold for four)
                    continue

        task = asyncio.create_task(keep())
        try:
            yield
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    # -- what a batch is decided by --

    async def seen(self, toolchain: str | None = None) -> Seen:
        """What a batch is decided by, read once (the states of the vectors, the fit in use), and the toolchain
        (`toolchain_user`, unless given)"""
        from pangloss_learn import Model
        from pangloss_vectors import store

        from pangloss_reconcile import fits

        states = await store.states()
        today = decisions.today(states)
        fit = await fits.in_use()
        used = fits.usable(fit, today)
        return Seen(
            states=states,
            today=today,
            fit=Model.from_json(fit["none"]) if used and fit is not None else None,
            fit_id=str(fit["id"]) if used and fit is not None else None,
            toolchain=toolchain or await toolchain_user(),
            decided_by=decided_by(str(fit["id"]) if used and fit is not None else None),
        )

    # -- one head --

    async def _complete(
        self, claimed: tuple[str, str], tried: Sequence[dict[str, Any]] = ()
    ) -> None:
        @database().write_transaction
        async def complete(tx: Transaction) -> None:
            await pending.complete(tx, KIND, [claimed])
            await _note_tried(tx, list(tried))

        await complete()

    async def _release(self, head_ids: Iterable[str]) -> None:
        @database().write_transaction
        async def release(tx: Transaction) -> None:
            await pending.release(tx, KIND, list(head_ids))

        await release()

    async def _left(
        self, claimed: tuple[str, str], type_name: str, why: str
    ) -> Outcome:
        logger.info("Reconcile: %s %s is left alone: %s", type_name, claimed[0], why)
        await self._complete(claimed)
        self.stats.left[why.split(":")[0]] = (
            self.stats.left.get(why.split(":")[0], 0) + 1
        )
        return Outcome(claimed[0], "left", why)

    async def process(
        self, claimed: tuple[str, str], seen: Seen | None = None
    ) -> Outcome:
        """Do one claimed head (its id and the token of its mark), and complete its mark or give its claim back as
        the outcome says (the module's steps 1 to 8). Raises what is not a refusal, the claim given back"""
        from pangloss_users import see_unpublished

        seeing = see_unpublished.set(True)
        try:
            return await self._process(claimed, seen or await self.seen())
        except BaseException:
            with contextlib.suppress(Exception):
                await self._release([claimed[0]])
            raise
        finally:
            see_unpublished.reset(seeing)

    async def _process(self, claimed: tuple[str, str], seen: Seen) -> Outcome:
        from pangloss_models import ModelRegistry
        from pangloss_models.utils import editable
        from pangloss_vectors.unknowns import unknowns_of

        from pangloss_reconcile.stored import Unplannable, plan_of_view

        head_id = claimed[0]

        # 1. whether it is to be touched at all
        @database().read_transaction
        async def read(tx: Transaction) -> dict[str, Any] | None:
            return await (await tx.run(HEAD_QUERY, id=head_id)).single()

        row = await read()
        if row is None or row["deleted"]:
            return await self._left(claimed, "head", "gone or deleted")
        type_name = str(row["type"])
        model: Any = ModelRegistry._model_dict.get(type_name)
        if model is None or not marking.people_write(model):
            return await self._left(claimed, type_name, "not written by people")
        if not marking.suggestible(model):
            return await self._left(
                claimed, type_name, "of a class that holds no stand-in"
            )
        view = await rewriting.read_head(model, UUID(head_id))
        if view is None:
            return await self._left(claimed, type_name, "gone or deleted")
        if getattr(view.meta, "published", True):
            return await self._left(claimed, type_name, "published")
        try:
            plan = await plan_of_view(model, view)
        except Unplannable as error:
            return await self._left(claimed, type_name, f"unplannable: {error}")

        async def as_read(_model: Any, _id: UUID) -> Any:
            return view

        # 2. its stand-ins, not tried with today's digest
        unknowns = unknowns_of(plan)
        parts = _parts_by_id(editable(view.model_dump()), {u.id for u in unknowns})
        digests = {
            u.id: digest(seen.today, seen.decided_by, u, parts[u.id].get("uris") or ())
            for u in unknowns
            if u.id in parts
        }
        noted = await tried_of(list(digests))
        fresh = [
            u for u in unknowns if u.id in digests and noted.get(u.id) != digests[u.id]
        ]
        if not fresh:
            await self._complete(claimed)
            return Outcome(head_id, "nothing", "no stand-in to ask about")

        # 3. by trial, the shape each one's place takes
        shapes: dict[str, Shape] = {}
        for unknown in fresh:
            found = await _shape_of(model, head_id, unknown, seen, as_read)
            if found is not None:
                shapes[unknown.id] = found
        untakable = [u for u in fresh if u.id not in shapes]
        takable = [u for u in fresh if u.id in shapes]

        def tried_row(unknown: Any) -> dict[str, Any]:
            return {
                "stand_in": unknown.id,
                "head": head_id,
                "digest": digests[unknown.id],
                "at": datetime.datetime.now(datetime.UTC),
            }

        # 4. whether a part it would change is cited
        if takable:
            cited = cited_among(
                head_id,
                model,
                plan,
                [u.id for u in takable],
                await cited_targets(head_id),
            )
            if cited:
                return await self._left(
                    claimed,
                    type_name,
                    f"cited: something cites a part that holds {', '.join(cited)}",
                )

        # 5. the candidates, as the stored route asks them, in groups; 6. judged
        decided: dict[str, tuple[Any, Decision]] = {}
        left = list(untakable)
        for found in await _candidates(plan, [u.id for u in takable]):
            if found.status != "ok":
                logger.info(
                    "Reconcile: no candidates for %s in %s %s: the profile is %s",
                    found.unknown.id,
                    type_name,
                    head_id,
                    found.status,
                )
                continue
            from pangloss_reconcile.suggest import decide_for

            decision = await judged(
                view, found.unknown, found, decide_for(found, seen.fit)
            )
            if decision.suggested:
                decided[found.unknown.id] = (found, decision)
            else:
                left.append(found.unknown)

        if not decided:
            await self._complete(claimed, [tried_row(u) for u in left])
            self.stats.tried += len(left)
            return Outcome(head_id, "nothing", "nothing decided", tried=len(left))

        # 7. one update, as the toolchain, with 8. what it saw kept in its transaction
        at = datetime.datetime.now(datetime.UTC)
        version = toolchain_version(seen)
        suggest_as = settings.suggest_as()
        new_ids = {stand_in: str(uuid.uuid7()) for stand_in in decided}

        def replace(part: dict[str, Any]) -> dict[str, Any]:
            stand_in = str(part["id"])
            return suggestion(
                part,
                shapes[stand_in],
                decided[stand_in][1].alternatives,
                id=new_ids[stand_in],
                suggest_as=suggest_as,
                toolchain=seen.toolchain,
                version=version,
            )

        kept = Kept(
            head=head_id,
            suggested=[
                _suggested_row(
                    new_ids[stand_in],
                    head_id,
                    stand_in,
                    at,
                    found,
                    decision,
                    shapes[stand_in],
                    seen,
                )
                for stand_in, (found, decision) in decided.items()
            ],
            tried=[tried_row(u) for u in left],
        )
        try:
            with as_toolchain(seen.toolchain), marking.kept_in_write(kept):
                await rewriting.rewrite(
                    model,
                    UUID(head_id),
                    lambda data: rewriting.replaced_where(
                        data, lambda part: str(part.get("id")) in decided, replace
                    ),
                    version=view.meta.version,
                    read=as_read,
                    instructions={marking.NAME: False},
                )
        except PanglossVersionConflictError:
            await self._release([head_id])
            self.stats.conflicts += 1
            logger.info(
                "Reconcile: %s %s changed while its suggestions were worked out: tried again later if it is "
                "still marked",
                type_name,
                head_id,
            )
            return Outcome(head_id, "conflict", "the version moved on")
        except NOT_REFUSALS:
            raise
        except (PanglossWriteError, ValidationError) as error:
            logger.info(
                "Reconcile: %s %s is left: its update with suggestions was refused: %s",
                type_name,
                head_id,
                error,
            )
            every = [*left, *(found.unknown for found, _ in decided.values())]
            await self._complete(claimed, [tried_row(u) for u in every])
            self.stats.refused += 1
            self.stats.tried += len(every)
            return Outcome(head_id, "refused", str(error), tried=len(every))
        self.stats.updates += 1
        self.stats.suggestions += len(decided)
        self.stats.tried += len(left)
        logger.info(
            "Reconcile: %s %s written with %s suggestions (%s stand-ins left)",
            type_name,
            head_id,
            len(decided),
            len(left),
        )
        return Outcome(head_id, "written", suggestions=len(decided), tried=len(left))

    # -- a batch --

    async def process_batch(self) -> int:
        """A few marked heads claimed and done (`process`), once what it writes as and with is checked (`ready`:
        only when something was claimed, so that a project with nothing marked is asked nothing of it). Gives how
        many were claimed (0 if none could be: `stats.waiting` counts the turns a rebuild or the vectors held it
        back). `ToolchainRefused`, or `PanglossInitialisationError` for `RECONCILE_SUGGEST_AS`, with the claims given
        back"""
        claimed = await self.claim()
        if claimed is None:
            self.stats.waiting += 1
            return 0
        if not claimed:
            if await self._any_waiting():
                self.stats.waiting += 1
            return 0
        done: list[str] = []
        try:
            toolchain = await ready()
            async with self.held(claimed):
                seen = await self.seen(toolchain)
                for each in claimed:
                    await self.process(each, seen)
                    done.append(each[0])
        except BaseException:
            # (what was not done is given back, to be tried again)
            with contextlib.suppress(Exception):
                await self._release([h for h, _ in claimed if h not in done])
            raise
        stats = self.stats
        stats.batches += 1
        stats.heads += len(claimed)
        stats.last_batch_at = time.time()
        return len(claimed)

    async def _any_waiting(self) -> bool:
        @database().read_transaction
        async def read(tx: Transaction) -> bool:
            found = await pending.count(tx, KIND)
            return bool(found["pending"]) and found["claimed"] < found["pending"]

        return await read()

    async def drain(self) -> int:
        """Do every batch that can be done now. Gives how many heads were done. `ToolchainRefused` if the toolchain is
        a person or disabled (nothing is written, the claims given back)"""
        done = 0
        while True:
            claimed = await self.process_batch()
            if not claimed:
                return done
            done += claimed
            if not await self.take_lease():
                return done

    async def run(self, settings: Any = None) -> None:
        """Runs until cancelled (a `BackgroundTask`), or until the toolchain is refused (said, at error)"""
        self._loop = asyncio.get_running_loop()
        self._wake = asyncio.Event()
        try:
            while not await self.take_lease():
                await asyncio.sleep(self.settings.idle)
            batch, delay = self.settings.batch, 1.0
            while True:
                self._wake.clear()
                waiting = self.stats.waiting
                try:
                    await self.drain()
                except (ToolchainRefused, PanglossInitialisationError) as error:
                    logger.error("Reconcile: the worker stops: %s", error)
                    return
                except Exception:
                    self.stats.failures += 1
                    self.settings.batch = max(1, self.settings.batch // 2)
                    logger.warning(
                        "Reconcile: a batch failed; trying again in %.0f s, %s heads at a time",
                        delay,
                        self.settings.batch,
                        exc_info=True,
                    )
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 60.0)
                    continue
                delay = 1.0
                self.settings.batch = batch
                wait = (
                    self.settings.paused
                    if self.stats.waiting > waiting
                    else self.settings.idle
                )
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._wake.wait(), wait)
                while not await self.take_lease():
                    await asyncio.sleep(self.settings.idle)
        finally:
            self._wake = None
            self._loop = None
            try:
                await self.give_up_lease()
            except Exception:
                logger.debug("The lease was not given up", exc_info=True)


async def ready() -> str:
    """What the worker checks before it writes: the class it writes (`RECONCILE_SUGGEST_AS`: a model with the fields it
    fills), and who it writes as (`toolchain_user`). Gives the toolchain's username"""
    settings.check_suggest_as()
    return await toolchain_user()


def _parts_by_id(data: Any, ids: Collection[str]) -> dict[str, dict[str, Any]]:
    """The nodes of these ids in a tree as an `Update` takes it"""
    found: dict[str, dict[str, Any]] = {}

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            if str(value.get("id")) in ids:
                found.setdefault(str(value["id"]), value)
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(data)
    return found


async def _shape_of(
    model: Any, head_id: str, unknown: Any, seen: Seen, read: Any
) -> Shape | None:
    """Which shape the place of a stand-in takes, by trial: its document's `Update` validated with the stand-in
    replaced by a suggestion of a placeholder, in each shape in turn (nothing is written, nothing looked up). None:
    neither"""
    placeholder = [Alternative(str(uuid.uuid4()), placeholder_type(unknown.type), 100)]
    for shape in SHAPES:

        def replace(part: dict[str, Any], shape: Shape = shape) -> dict[str, Any]:
            return suggestion(
                part,
                shape,
                placeholder,
                id=str(uuid.uuid4()),
                suggest_as=settings.suggest_as(),
                toolchain=seen.toolchain,
                version=toolchain_version(seen),
            )

        try:
            prepared = await rewriting.prepare_rewrite(
                model,
                UUID(head_id),
                lambda data, replace=replace: rewriting.replaced(
                    data, unknown.id, replace
                ),
                read=read,
            )
        except ValidationError:
            continue
        if isinstance(prepared, rewriting.Prepared):
            return shape
    return None


async def _candidates(plan: Any, ids: list[str]) -> list[Any]:
    """The candidates of these unknowns of the plan, as the stored route asks them (`see_unpublished=True`, the
    dialog's limit), in groups of at most `RECONCILE_MOST_UNKNOWNS`"""
    from pangloss_reconcile.candidates import DISPLAYED, candidates_of

    most = settings.most_unknowns()
    found = []
    for start in range(0, len(ids), most):
        found.extend(
            await candidates_of(
                plan,
                see_unpublished=True,
                limit=DISPLAYED,
                only=ids[start : start + most],
            )
        )
    return found


async def judged(view: Any, unknown: Any, found: Any, decision: Decision) -> Decision:
    """Between the decision and the write: where a project's judge will be asked (step 10.5c'). Now the decision,
    unchanged"""
    return decision


def _suggested_row(
    id: str,
    head: str,
    stand_in: str,
    at: datetime.datetime,
    found: Any,
    decision: Decision,
    shape: Shape,
    seen: Seen,
) -> dict[str, Any]:
    """What is kept of a suggestion written (`PGReconcileSuggested`): ids and numbers only, as a shown record keeps
    them (`decisions.rows_of`, `displayed` the list the decision was made on), the alternatives written and their
    shape, and today's signatures. No user"""
    from pangloss_reconcile.candidates import DISPLAYED

    displayed = {candidate.id for candidate in found.candidates[:DISPLAYED]}
    return {
        "id": id,
        "head": head,
        "stand_in": stand_in,
        "at": at,
        "rows": json.dumps(decisions.rows_of(found, displayed)),
        "alternatives": json.dumps(
            [dataclasses.asdict(one) for one in decision.alternatives]
        ),
        "shape": shape,
        **{name: seen.today[name] for name in decisions.SIGNATURES},
    }


# The worker of this process (the server's background task; `drain` for tests and scripts)
worker = Worker()


async def drain() -> int:
    """Do all the work that can be done now, with this process's worker (for tests and scripts: no waiting for the
    background). Gives how many heads were done"""
    await worker.take_lease()
    try:
        return await worker.drain()
    finally:
        await worker.give_up_lease()


async def pending_status() -> dict[str, Any]:
    """What is marked and claimed, and when the oldest was marked; how many wait for the vectors (marked after the
    oldest mark of the vectors' kind) and whether a rebuild of them holds its lease; and who holds the worker's lease
    (`{holder, until}`, or None)"""

    @database().read_transaction
    async def read(tx: Transaction) -> dict[str, Any]:
        found = dict(await pending.count(tx, KIND))
        rebuilding, before = await _waiting(tx)
        waiting = 0
        if before is not None:
            record = await (
                await tx.run(WAITING_QUERY, kind=KIND, before=before)
            ).single()
            waiting = int(record["waiting"]) if record else 0
        lease = await (await tx.run(LEASE_READ_QUERY, kind=KIND)).single()
        found["waiting_for_vectors"] = waiting
        found["rebuilding"] = rebuilding
        found["lease"] = (
            {"holder": lease["holder"], "until": lease["until"]}
            if lease is not None and lease["holder"] is not None
            else None
        )
        return found

    return await read()
