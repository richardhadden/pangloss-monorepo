"""The worker that suggests who the stand-ins of a document are (step 10.5d of implementation_docs/similarity-build-plan.md;
implementation_docs/reconcile.md, "The worker that suggests"): Pangloss's own toolchain.

A save of a document that may hold a stand-in leaves it marked (`marking.py`, the kind `reconcile`). The worker, in a
loop, claims a few marked heads, the oldest first and only those whose writes have reached the vectors (below), and
for each, cheapest first:

1. **is it to be touched at all**: the head read once (`rewriting.read_head`). Left alone, its mark completed and why
   logged (at info), when it is gone or deleted, an entity (no document a person reviews: `marking` marks none),
   published (`meta.published`: the user's word, only unpublished documents), of a class people do not write, or
   holding no stand-in now (`marking.suggestible`), or its stored form cannot be planned (`stored.Unplannable`);
2. **its stand-ins**: of its stored plan, read once (`stored.plan_of_view`), the unknowns (`unknowns_of`), and **which
   shape the place of each takes**, by trial (`rewriting.prepare_rewrite`, nothing written): the stand-in replaced by
   a `RECONCILE_SUGGEST_AS` whose target is one `WeightedAlternative` of a placeholder at 100 per cent, then one
   placeholder entity (`target_of`, the one place the two shapes are made). Each is skipped while it was tried with
   today's digest (`PGReconcileTried`, `digest`: what the decision is made of today, the stand-in's own label, class
   and URIs, where it sits, `place_of`, and the shape found);
3. one whose place takes neither shape is left, and noted as tried;
4. **is a part it would change cited** (`cited`: a citation, from a document that is not deleted, of the stand-in, of
   a node above it, of the head, or of any node of a head whose class cites the field it is in with it,
   `cited_with`): the head is left whole, its mark completed, logged. Asked by a read before any candidate is
   asked; the update's own refusal (`PanglossCitedError`) stays behind it, as any other refusal;
5. **the candidates** of those left, as the stored route asks them (`candidates_of(plan, see_unpublished=True,
   limit=candidates.DISPLAYED, only=...)`), in groups of at most `RECONCILE_MOST_UNKNOWNS`; the fit in use read once
   for the batch; `suggest.decide_for` for each. Candidates that are not `ok` (the profile's state changed since the
   batch was claimed): nothing of the head written or noted, its claim given back, the mark kept, and the drain
   stops (`waiting`);
6. `judged`: with a project's judge (`RECONCILE_SUGGEST_WITH`, step 10.5c'; `judging.py`), each stand-in asked of it,
   outside any transaction, as the toolchain and not as an admin, with plain data (`Judging.asked`: copies), a sync
   one in the worker's own threads (`judging.Threads`), its answer checked (`judging.checked`) and, when it gives its
   own alternatives, tried before the write by the write's own checks as far as they do not write (`Judging.tried`:
   the head's `Update` with that one suggestion in the stand-in's place, its validators and before-hooks, its
   entities there, not deleted, not merged away, and every reference the suggestion adds checked as the write checks
   it); what it is given made as it runs, and the classes the place takes (`Judging.takes`) and the trial each in a
   copy of the worker's context (`_apart`). A judge that fails (raises,
   times out, finds the threads all busy, answers badly, or suggests what the write would refuse) leaves that mention
   as it is, logged, **not noted as tried**, and with nothing of the worker's in its place; the other mentions are
   written as if it had not been asked. A place the document's own validators refuse an identification in (met while
   the judge's data is made) takes no suggestion: the judge is not asked of it, and it goes on as with no judge. With
   no judge, nothing of it is made: the decision unchanged;
7. **one update**, if anything was decided (`rewriting.rewrite`, based on the version read, as the toolchain user
   `RECONCILE_TOOLCHAIN`, `instructions={"suggest": False}`, which takes the head's mark off in the update's own
   transaction): each stand-in decided replaced by a suggestion with a new id (`text` its label, `uris` its URIs,
   `identified_by` the toolchain, `toolchain_version` the profile and the fit used, the target in the shape found,
   the relation's own properties kept). **First in its transaction** (`before_write`, `still_mine`): the head still
   unpublished and its mark still the one claimed, both locked; else nothing written, and a head published meanwhile
   is left as a published one is, one whose mark was taken off or made again is dropped (`moved`: whatever marked it
   owns the mark). A version that moved on (`PanglossVersionConflictError`): nothing written, the claim given back,
   the mark kept. Any other refusal: logged, the mark completed, the stand-ins left for a reason of their own noted as
   tried (not those decided). A failure that is not a refusal: the claims given back, the error raised, and at the
   `FAILURES`th in a row of a head the head taken as refused (logged at error, nothing noted). Nothing decided: the
   mark completed by its token, the stand-ins noted as tried;
8. **what it saw is kept** (`PGReconcileSuggested`, one for each suggestion, by its id: the head, the stand-in, when,
   the rows of `Found.best` with `displayed` the list decided on (a judge or not), the alternatives and their shape,
   today's signatures, `judged: true` when a project's judge changed what was written; no user; none with `RECONCILE_KEEP_DECISIONS` false: a person's confirmation of it is an example,
   `decisions.confirmed`, step 10.5f) and the stand-ins left, and those replaced, as tried (`PGReconcileTried`; a replaced one with
   the suggestion's id, so that a restore of the version before finds it tried), **in the update's own transaction**
   (`hooks.in_write`, while `marking.keeping` names the head; cleared before the write's listeners run, so that a task
   they start does not carry it), so that nothing can be written without the other.

**Waiting.** A batch is not claimed while a rebuild of the vectors holds its lease, or while the profile candidates
are found by is not `ok` (`Waiting`, read in the claim's transaction), and only marks made before the oldest mark of
the vectors' kind are claimed (the writes that left them have reached the vectors); the worker's own updates leave
vectors marks newer than any mark it would claim, and are not waited for. With `pangloss_vectors` installed and its
worker never running, nothing is claimed, and `pending_status` says so.

**One worker at a time** (a lease on the `PGReconcileWorker` node, as the vectors worker's), few heads claimed at a
time (`Settings.batch`, 5), the lease and the claims renewed while it works (a mention asked takes 1 to 2.5 s at size).
The toolchain is checked before each batch (`toolchain_user`): made if absent (kind `toolchain`, nothing to log in
with), refused, and the worker stopped, if it is a person or disabled (`ToolchainRefused`)."""

import asyncio
import contextlib
import contextvars
import dataclasses
import datetime
import hashlib
import json
import logging
import time
import uuid
from collections.abc import (
    AsyncGenerator,
    Collection,
    Coroutine,
    Iterable,
    Mapping,
    Sequence,
)
from typing import Any, Literal, cast
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

from pangloss_reconcile import decisions, judging, marking, settings
from pangloss_reconcile.judging import Verdict
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

# How many times in a row a head may raise something that is not a refusal before it is taken as refused (its mark
# completed): until then its claim is given back and the error raised, as for any failure
FAILURES = 3

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
    judge_failures: int = 0
    """Stand-ins a project's judge failed for (left as they were, not noted as tried)"""
    last_batch_at: float | None = None


class ToolchainRefused(Exception):
    """`RECONCILE_TOOLCHAIN` names a person, or a user who is disabled: the worker does not write as them, and stops"""


@dataclasses.dataclass(frozen=True)
class Outcome:
    """What became of one claimed head: `written` (an update with suggestions), `nothing` (nothing decided: the mark
    completed), `left` (left alone, `why`: the mark completed), `conflict` (the version moved on: the claim given
    back, the mark kept), `refused` (the update was refused, or the head failed `FAILURES` times, `why`: the mark
    completed), `moved` (its mark was taken off or made again since it was claimed: nothing written, nothing
    completed), `waiting` (the profile is not `ok` now: the claim given back, the mark kept)"""

    head: str
    what: Literal[
        "written", "nothing", "left", "conflict", "refused", "moved", "waiting"
    ]
    why: str = ""
    suggestions: int = 0
    tried: int = 0


@dataclasses.dataclass(frozen=True)
class Judge:
    """A project's judge (`RECONCILE_SUGGEST_WITH`): its name, the function, the seconds it is given for a
    stand-in (`RECONCILE_SUGGEST_TIMEOUT`), and the worker's own threads a sync one runs in (`judging.Threads`)"""

    name: str
    function: Any
    timeout: float
    threads: judging.Threads = dataclasses.field(default_factory=judging.Threads)


@dataclasses.dataclass(frozen=True)
class Seen:
    """What a batch is decided by, read once for it: the states of the vectors, today's signatures, the "none of
    these" model of the fit in use when it can be used (and its id), the toolchain, the digest of the settings of
    the decision, and the project's judge if one is configured"""

    states: Any
    today: dict[str, Any]
    fit: Any
    fit_id: str | None
    toolchain: str
    decided_by: str
    judge: Judge | None = None


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
    fields: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """What a stand-in (`part`, as an `Update` takes it) becomes: a `suggest_as` of a new id, its label as `text`, its
    URIs, the toolchain and its version, the target in the shape, and the properties of the relation to it kept (as
    review's reconciliation keeps them); and `fields`, further fields of the class a project's judge gave (none of
    those the worker fills: `judging.checked` refuses them)"""
    made: dict[str, Any] = {
        **(fields or {}),
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
    """What the worker's suggestions say was used: the profile, the fit in use when it was used, and the project's
    judge when one was configured for the batch (whether or not it changed the decision)"""
    used = f"profile {seen.today['profile']}"
    if seen.fit_id is not None:
        used = f"{used}, fit {seen.fit_id}"
    return used if seen.judge is None else f"{used}, judge {seen.judge.name}"


# --- what has been tried -----------------------------------------------------------------------------------------


def decided_by(fit_id: str | None, judge: str | None = None) -> str:
    """The settings a decision is made by, as text: what a stand-in tried is noted with, beside today's signatures.
    The project's judge's name only when one is configured (so that with none the text is what it was before there
    could be one, and a judge turned on, or changed, asks again for what was tried)"""
    from pangloss_reconcile.candidates import DISPLAYED

    made: dict[str, Any] = {
        "above": settings.suggest_above(),
        "most": settings.suggest_most(),
        "within": settings.suggest_within(),
        "new_above": settings.new_above(),
        "fit": fit_id,
        "as": settings.suggest_as(),
        "displayed": DISPLAYED,
    }
    if judge is not None:
        made["judge"] = judge
    return json.dumps(made, sort_keys=True)


def digest(
    today: Mapping[str, Any],
    decided: str,
    unknown: Any,
    uris: Iterable[Any],
    *,
    place: Sequence[str],
    shape: Shape | None,
) -> str:
    """What a stand-in is tried by: today's signatures (`decisions.today`), the settings of the decision
    (`decided_by`), the stand-in's own label, class and URIs (a stand-in edited is asked again), where it sits (`place`,
    the field names from the head down to it, `place_of`) and the shape its place takes (`None`: none). A stand-in is
    skipped while what it was noted with is this: one moved to a field that takes another shape, or one, is asked
    again"""
    text = json.dumps(
        {
            "today": {name: today[name] for name in decisions.SIGNATURES},
            "decided": decided,
            "stand_in": [unknown.label, unknown.type, sorted(str(uri) for uri in uris)],
            "place": list(place),
            "shape": shape or "none",
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

# (`suggested`: the id of the suggestion written in its place, for a stand-in replaced; null for one left)
TRIED_WRITE_QUERY = f"""
UNWIND $rows AS row
MERGE (t:{TRIED} {{stand_in: row.stand_in}})
SET t.head = row.head, t.digest = row.digest, t.at = row.at, t.suggested = row.suggested
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

# (a stand-in tried that is no longer a node of a document, and that neither the record of the suggestion written in
# its place (`t.suggested`, by its id), nor an example of it (`PGReconcileExample`, by the stand-in's id), nor the
# example a person's confirmation made of that suggestion (by the suggestion's id, step 10.5f) still names: while one
# does, a restore that brings the stand-in back finds it tried. Each is found by an index)
SWEEP_TRIED_QUERY = f"""
MATCH (t:{TRIED})
OPTIONAL MATCH (n:PGIndexableNode {{id: t.stand_in}})
WITH t, n
WHERE n IS NULL OR n.head_node_id IS NULL
OPTIONAL MATCH (s:{SUGGESTED} {{id: t.suggested}})
OPTIONAL MATCH (e:{decisions.EXAMPLE} {{stand_in: t.stand_in}})
OPTIONAL MATCH (c:{decisions.EXAMPLE} {{stand_in: t.suggested}})
WITH t, s, e, c
WHERE s IS NULL AND e IS NULL AND c IS NULL
DELETE t
RETURN count(*) AS n
"""


async def sweep_kept() -> tuple[int, int]:
    """(`decisions.sweep`) Remove what the worker kept that nothing can use now: the rows of a suggestion that is no
    longer one (confirmed, or gone), never by age; and then the stand-ins tried that are no longer in a document, unless
    the record of the suggestion written in a stand-in's place, an example of the stand-in, or the example made of
    that suggestion's confirmation still names it (so a
    stand-in the worker replaced stays tried while its suggestion is one, and a restore of the version before it finds
    it tried). Gives how many of each went"""
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
def as_toolchain(name: str, *, admin: bool | None = None):
    """The writes in the block are the toolchain's (`current_request_username`, as the commands set it), and it sees
    what is not published. `current_request_is_admin` is left as it is (True outside a request: the worker's write
    is under it, as a command's is) unless `admin` is given: the project's judge is called with `admin=False`, as the
    toolchain, which is no admin"""
    from pangloss_users import (
        current_request_is_admin,
        current_request_username,
        see_unpublished,
    )

    user = current_request_username.set(name)
    seeing = see_unpublished.set(True)
    is_admin = None if admin is None else current_request_is_admin.set(admin)
    try:
        yield
    finally:
        if is_admin is not None:
            current_request_is_admin.reset(is_admin)
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


@dataclasses.dataclass(frozen=True)
class Waiting:
    """What the worker waits for, read in one transaction: whether a rebuild of the vectors holds its lease, when the
    oldest mark of the vectors' kind was made (None: there is none), and the state of the profile candidates are
    found by (`RECONCILE_PROFILE`: `"ok"`, `"pending"`, not built, or `"rebuild_due"`, as a search of it would say).
    With the vectors not installed, nothing (`"ok"`)"""

    rebuilding: bool = False
    oldest: float | None = None
    profile: str = "ok"

    @property
    def held(self) -> bool:
        """Nothing is claimed: a rebuild in hand, or the profile not `ok`"""
        return self.rebuilding or self.profile != "ok"


def profile_status(states: Any) -> str:
    """The state of the profile candidates are found by, as `nearest` would answer a search of it: `"pending"` (not
    built), `"rebuild_due"` (its vectors in use are of another dimension than its parts make today), or `"ok"`"""
    from pangloss_vectors import store

    name = settings.profile()
    state = states.profiles.get(name)
    if state is None:
        return "pending"
    if state.dimension != store.layout(name).dimension:
        return "rebuild_due"
    return "ok"


async def _waiting(tx: Transaction) -> Waiting:
    """What the worker waits for, read in the transaction given (`Waiting`)"""
    if not _vectors_installed():
        return Waiting()
    from pangloss_vectors import KIND as VECTORS
    from pangloss_vectors import store
    from pangloss_vectors.rebuild import LEASE as REBUILD_LEASE

    held = await (await tx.run(REBUILD_HELD_QUERY.format(label=REBUILD_LEASE))).single()
    rebuilding = (
        held is not None
        and held["holder"] is not None
        and (held["until"] or 0) > time.time()
    )
    oldest = await (await tx.run(OLDEST_QUERY, kind=VECTORS)).single()
    return Waiting(
        rebuilding,
        oldest["oldest"] if oldest else None,
        profile_status(await store._states(tx)),
    )


# (in the transaction of the worker's update, before anything is read or written: the head's lock and the mark's
# taken (Neo4j reads what is committed: so nothing can change either between this read and the commit; on Memgraph a
# change committed meanwhile makes this transaction run again), then whether the head is published, and the token of
# its mark)
MARK_LOCK_QUERY = """
MATCH (p:PGPending {key: $key})
SET p.pg_lock = true
REMOVE p.pg_lock
"""

STILL_MINE_QUERY = f"""
OPTIONAL MATCH (head:HeadNode {{id: $id}})
OPTIONAL MATCH (p:PGPending {{key: $key}})
RETURN {fragments.published("head")} AS published, p.token AS token
"""


class _Moved(Exception):
    """(raised in the worker's update, which is then not made) the head was published, or its mark taken off or made
    again, since it was read"""

    def __init__(self, published: bool, token: str | None) -> None:
        super().__init__(
            "published meanwhile"
            if published
            else "its mark was taken off meanwhile"
            if token is None
            else "it was marked again meanwhile"
        )
        self.published = published
        self.token = token


def still_mine(head_id: str, token: str) -> Any:
    """What the worker's update runs first in its own transaction (`before_write`): `_Moved` unless the head is still
    unpublished and its mark is still the one claimed (`token`)"""
    from pangloss_cypher.pending import key_of
    from pangloss_cypher.transactions import dialect

    key = key_of(KIND, head_id)

    async def check(tx: Any) -> None:
        await dialect().before_replace(tx, head_id)
        await (await tx.run(MARK_LOCK_QUERY, key=key)).consume()
        found = await (await tx.run(STILL_MINE_QUERY, id=head_id, key=key)).single()
        published = bool(found and found["published"])
        held = found["token"] if found else None
        if published or held != token:
            raise _Moved(published, held)

    return check


class Worker:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()
        self.id = str(uuid.uuid4())
        self.stats = Stats()
        self._wake: asyncio.Event | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        # (the failures in a row of each head that raised what is not a refusal, in this process)
        self._failures: dict[str, int] = {}
        # (whether the last batch had a head come back `waiting`: the drain stops)
        self._held_back = False
        # (the threads a sync judge runs in: the worker's own, let go when it stops)
        self.threads = judging.Threads()

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
        a rebuild of the vectors holds its lease, or the profile candidates are found by is not `ok` (`Waiting`:
        nothing is claimed)"""
        settings_ = self.settings

        @database().write_transaction
        async def claim(tx: Transaction) -> list[tuple[str, str]] | None:
            waiting = await _waiting(tx)
            if waiting.held:
                return None
            return await pending.claim(
                tx, KIND, settings_.batch, settings_.lease, before=waiting.oldest
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
        configured = settings.judge()
        judge = (
            None
            if configured is None
            else Judge(
                configured[0],
                configured[1],
                settings.suggest_timeout(),
                self.threads,
            )
        )
        return Seen(
            states=states,
            today=today,
            fit=Model.from_json(fit["none"]) if used and fit is not None else None,
            fit_id=str(fit["id"]) if used and fit is not None else None,
            toolchain=toolchain or await toolchain_user(),
            decided_by=decided_by(
                str(fit["id"]) if used and fit is not None else None,
                None if judge is None else judge.name,
            ),
            judge=judge,
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
        the outcome says (the module's steps 1 to 8). Raises what is not a refusal, the claim given back; but the
        `FAILURES`th time in a row a head raises something that is not one of `NOT_REFUSALS` (in this process: a
        restart counts again), it is taken as refused: logged at error with what it raised, its mark completed, none
        of its stand-ins noted as tried"""
        from pangloss_users import see_unpublished

        head_id = claimed[0]
        seeing = see_unpublished.set(True)
        try:
            outcome = await self._process(claimed, seen or await self.seen())
        except NOT_REFUSALS:
            with contextlib.suppress(Exception):
                await self._release([head_id])
            raise
        except Exception as error:
            failed = self._failures[head_id] = self._failures.get(head_id, 0) + 1
            if failed < FAILURES:
                with contextlib.suppress(Exception):
                    await self._release([head_id])
                raise
            del self._failures[head_id]
            logger.error(
                "Reconcile: %s failed %s times in a row, and is left as refused: %s",
                head_id,
                failed,
                error,
                exc_info=error,
            )
            await self._complete(claimed)
            self.stats.refused += 1
            return Outcome(head_id, "refused", f"failed {failed} times: {error}")
        except BaseException:
            with contextlib.suppress(Exception):
                await self._release([head_id])
            raise
        finally:
            see_unpublished.reset(seeing)
        self._failures.pop(head_id, None)
        return outcome

    async def _process(self, claimed: tuple[str, str], seen: Seen) -> Outcome:
        from pangloss_models import Entity, ModelRegistry
        from pangloss_models.utils import editable
        from pangloss_vectors.unknowns import unknowns_of

        from pangloss_reconcile.stored import Unplannable, plan_of_view

        head_id, token = claimed

        # 1. whether it is to be touched at all
        @database().read_transaction
        async def read(tx: Transaction) -> dict[str, Any] | None:
            return await (await tx.run(HEAD_QUERY, id=head_id)).single()

        row = await read()
        if row is None or row["deleted"]:
            return await self._left(claimed, "head", "gone or deleted")
        type_name = str(row["type"])
        model: Any = ModelRegistry._model_dict.get(type_name)
        if isinstance(model, type) and issubclass(model, Entity):
            # (an entity is no document a person reviews: `marking` marks none, but a mark may be left by hand)
            return await self._left(
                claimed, type_name, "an entity: not a document a person reviews"
            )
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

        # 2. its stand-ins, and by trial the shape each one's place takes (nothing written: the shape and the place
        # are in the digest, so that a stand-in moved is asked again); those not tried with today's digest
        unknowns = unknowns_of(plan)
        parts = _parts_by_id(editable(view.model_dump()), {u.id for u in unknowns})
        present = [u for u in unknowns if u.id in parts]
        above = _above(plan)
        shapes: dict[str, Shape | None] = {
            unknown.id: await _shape_of(model, head_id, unknown, seen, as_read)
            for unknown in present
        }
        digests = {
            u.id: digest(
                seen.today,
                seen.decided_by,
                u,
                parts[u.id].get("uris") or (),
                place=place_of(u.id, above),
                shape=shapes[u.id],
            )
            for u in present
        }
        noted = await tried_of(list(digests))
        fresh = [u for u in present if noted.get(u.id) != digests[u.id]]
        if not fresh:
            await self._complete(claimed)
            return Outcome(head_id, "nothing", "no stand-in to ask about")

        # 3. those whose place takes no suggestion
        untakable = [u for u in fresh if shapes[u.id] is None]
        takable = [u for u in fresh if shapes[u.id] is not None]

        def tried_row(unknown: Any, suggested: str | None = None) -> dict[str, Any]:
            return {
                "stand_in": unknown.id,
                "head": head_id,
                "digest": digests[unknown.id],
                "at": datetime.datetime.now(datetime.UTC),
                "suggested": suggested,
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
        decided: dict[str, tuple[Any, Verdict]] = {}
        left = list(untakable)
        found_all = await _candidates(plan, [u.id for u in takable])
        not_ok = sorted({found.status for found in found_all if found.status != "ok"})
        if not_ok:
            # (the state of the profile changed since the batch was claimed: the head waits for it, as a batch does)
            await self._release([head_id])
            logger.info(
                "Reconcile: %s %s waits: the profile is %s; its claim given back",
                type_name,
                head_id,
                ", ".join(not_ok),
            )
            return Outcome(head_id, "waiting", f"the profile is {', '.join(not_ok)}")

        async def refused(error: Exception, left: list[Any]) -> Outcome:
            # (the head's update refused: those left for a reason of their own noted as tried, not those decided)
            logger.info(
                "Reconcile: %s %s is left: its update with suggestions was refused: %s",
                type_name,
                head_id,
                error,
            )
            await self._complete(claimed, [tried_row(u) for u in left])
            self.stats.refused += 1
            self.stats.tried += len(left)
            return Outcome(head_id, "refused", str(error), tried=len(left))

        # (a project's judge: what it is given made only when there is one, as the judge runs: the toolchain, not an
        # admin)
        asking = None
        failed = 0
        if seen.judge is not None:
            with as_toolchain(seen.toolchain, admin=False):
                asking = await Judging.of(
                    seen,
                    seen.judge,
                    model,
                    head_id,
                    view,
                    as_read,
                    plan,
                    parts,
                    shapes,
                    found_all,
                )
        judgements = [
            (found, await self._judged(view, found, seen, asking))
            for found in found_all
        ]
        for found, verdict in judgements:
            if isinstance(verdict, JudgeFailed):
                failure = verdict
                # (the mention left as it is, not noted as tried: the next trigger asks again; the rest of the head
                # goes on)
                failed += 1
                logger.warning(
                    "Reconcile: the judge %s failed for the stand-in %s (%r) of %s %s, which is left as it is and "
                    "will be asked again: %s",
                    failure.judge,
                    found.unknown.id,
                    found.unknown.label,
                    type_name,
                    head_id,
                    failure,
                    exc_info=failure.error,
                )
                continue
            if verdict.decision.suggested:
                decided[found.unknown.id] = (found, verdict)
            else:
                left.append(found.unknown)
        self.stats.judge_failures += failed

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
            shape = shapes[stand_in]
            assert shape is not None
            verdict = decided[stand_in][1]
            return suggestion(
                part,
                shape,
                verdict.decision.alternatives,
                id=new_ids[stand_in],
                suggest_as=suggest_as,
                toolchain=seen.toolchain,
                version=version,
                fields=verdict.fields,
            )

        kept = Kept(
            head=head_id,
            # (none with `RECONCILE_KEEP_DECISIONS` false: no example is made of a confirmation then, step 10.5f)
            suggested=[
                _suggested_row(
                    new_ids[stand_in],
                    head_id,
                    stand_in,
                    at,
                    found,
                    verdict.decision,
                    cast(Shape, shapes[stand_in]),
                    seen,
                    # (decided by the judge's own alternatives: its record, and the example of its
                    # confirmation, say so)
                    judged=verdict.by_judge,
                )
                for stand_in, (found, verdict) in decided.items()
            ]
            if settings.keep_decisions()
            else [],
            # (a stand-in replaced is noted as tried too, with the suggestion's id: restored, it is not asked again)
            tried=[tried_row(u) for u in left]
            + [
                tried_row(found.unknown, new_ids[stand_in])
                for stand_in, (found, _) in decided.items()
            ],
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
                    # (the head still unpublished and still this claim's, checked in the update's transaction)
                    before_write=still_mine(head_id, token),
                    instructions={marking.NAME: False},
                )
        except _Moved as moved:
            if moved.published:
                return await self._left(claimed, type_name, "published")
            logger.info(
                "Reconcile: %s %s is dropped, nothing written: %s (whatever marked it does it again)",
                type_name,
                head_id,
                moved,
            )
            return Outcome(head_id, "moved", str(moved))
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
            # (only those left for a reason of their own: those decided were not written, and are not tried)
            return await refused(error, left)
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

    async def _judged(
        self, view: Any, found: Any, seen: Seen, asking: Judging | None
    ) -> Verdict | JudgeFailed:
        """(`judged` of one stand-in, by the worker's own decision) the verdict, or the judge's failure for it"""
        from pangloss_reconcile.suggest import decide_for

        try:
            return await judged(
                view, found.unknown, found, decide_for(found, seen.fit), asking=asking
            )
        except JudgeFailed as failure:
            return failure

    # -- a batch --

    async def process_batch(self) -> int:
        """A few marked heads claimed and done (`process`), once what it writes as and with is checked (`ready`:
        only when something was claimed, so that a project with nothing marked is asked nothing of it). Gives how
        many were claimed (0 if none could be: `stats.waiting` counts the turns a rebuild, the profile or the vectors
        held it back; a head that came back `waiting` counts one too, and the drain stops there). `ToolchainRefused`,
        or `PanglossInitialisationError` for `RECONCILE_SUGGEST_AS`, with the claims given back"""
        self._held_back = False
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
                    outcome = await self.process(each, seen)
                    done.append(each[0])
                    if outcome.what == "waiting":
                        self._held_back = True
        except BaseException:
            # (what was not done is given back, to be tried again)
            with contextlib.suppress(Exception):
                await self._release([h for h, _ in claimed if h not in done])
            raise
        stats = self.stats
        stats.batches += 1
        stats.heads += len(claimed)
        stats.last_batch_at = time.time()
        if self._held_back:
            stats.waiting += 1
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
            if self._held_back:
                return done
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
            self.threads.shutdown()
            try:
                await self.give_up_lease()
            except Exception:
                logger.debug("The lease was not given up", exc_info=True)


async def ready() -> str:
    """What the worker checks before it writes: the class it writes (`RECONCILE_SUGGEST_AS`: a model with the fields it
    fills), and who it writes as (`toolchain_user`). Gives the toolchain's username"""
    settings.check_suggest_as()
    return await toolchain_user()


def place_of(id: str, above: Mapping[str, tuple[str, str]]) -> list[str]:
    """Where a node of a plan sits: the names of the fields from the head down to it (`above`, `_above` of the plan)"""
    fields: list[str] = []
    while id in above:
        id, field = above[id]
        fields.append(field)
    return fields[::-1]


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


class JudgeFailed(Exception):
    """A project's judge failed for one stand-in (it raised, did not answer in time, answered badly, or suggested what
    the write would refuse): said with what was wrong, and `error`, what it raised, if it raised"""

    def __init__(
        self, judge: str, message: str, error: BaseException | None = None
    ) -> None:
        super().__init__(message)
        self.judge = judge
        self.error = error


# (the entities a judge names, looked up as the write would look them up: there, not deleted, not merged away, and
# of the class it says)
ENTITIES_QUERY = """
UNWIND $ids AS id
OPTIONAL MATCH (n:PGIndexableNode {id: id})
RETURN id, labels(n) AS labels, coalesce(n.deleted, false) AS deleted, n.merged_into AS merged_into
"""


def _types_of(plan: Any) -> dict[str, str]:
    """The class of each node of a plan, by id (the head's too)"""
    from pangloss_cypher.write_plan import PlannedNode

    found: dict[str, str] = {str(plan.head.id): str(plan.head.type)}
    for source, relation, _first in plan.walk():
        found.setdefault(source.id, source.type)
        if isinstance(relation.target, PlannedNode):
            found.setdefault(relation.target.id, relation.target.type)
    return found


@dataclasses.dataclass
class Judging:
    """What a project's judge is asked with for the stand-ins of one head (`judged`): made once for the head, and only
    when a judge is configured (`of`): the head read, its plan, its parts, the shapes found, and the candidates as the
    stored route answers them (one read for the head)"""

    seen: Seen
    judge: Judge
    model: Any
    head_id: str
    view: Any
    read: Any
    plan: Any
    parts: dict[str, dict[str, Any]]
    shapes: Mapping[str, Shape | None]
    answered: dict[str, list[dict[str, Any]]]
    document: dict[str, Any]
    above: dict[str, tuple[str, str]]
    types: dict[str, str]

    @classmethod
    async def of(
        cls,
        seen: Seen,
        judge: Judge,
        model: Any,
        head_id: str,
        view: Any,
        read: Any,
        plan: Any,
        parts: dict[str, dict[str, Any]],
        shapes: Mapping[str, Shape | None],
        found: Sequence[Any],
    ) -> Judging:
        from pangloss_reconcile.api import answered
        from pangloss_reconcile.candidates import DISPLAYED

        given, _ = (
            await answered(list(found), see_unpublished=True)
            if found
            else ({"unknowns": []}, None)
        )
        by_id = {
            unknown["id"]: [
                {
                    "id": candidate["id"],
                    "type": candidate["type"],
                    "label": candidate.get("label"),
                    "score": candidate["score"],
                    "scores": dict(candidate["scores"]),
                    "shared": [
                        {
                            "id": one["id"],
                            "type": one["type"],
                            "label": one.get("label"),
                            "documents": one["documents"],
                        }
                        for one in candidate["shared"]
                    ],
                }
                for candidate in unknown["candidates"][:DISPLAYED]
            ]
            for unknown in given["unknowns"]
        }
        return cls(
            seen=seen,
            judge=judge,
            model=model,
            head_id=head_id,
            view=view,
            read=read,
            plan=plan,
            parts=parts,
            shapes=shapes,
            answered=by_id,
            document=view.model_dump(mode="json", by_alias=False),
            above=_above(plan),
            types=_types_of(plan),
        )

    def replacement(
        self,
        unknown: Any,
        shape: Shape,
        alternatives: Sequence[Alternative],
        fields: Mapping[str, Any] | None = None,
        *,
        id: str | None = None,
    ) -> Any:
        """The change that puts a suggestion of these alternatives in the stand-in's place (and nothing else), of the
        id given (a new one if not)"""
        made = id or str(uuid.uuid4())

        def replace(part: dict[str, Any]) -> dict[str, Any]:
            return suggestion(
                part,
                shape,
                alternatives,
                id=made,
                suggest_as=settings.suggest_as(),
                toolchain=self.seen.toolchain,
                version=toolchain_version(self.seen),
                fields=fields,
            )

        return lambda data: rewriting.replaced(data, unknown.id, replace)

    async def takes(self, unknown: Any, shape: Shape) -> list[str]:
        """The classes of entity the stand-in's place takes in its shape: of the trial of the shape (a placeholder in
        it), planned as the write plans it (nothing read), the classes its reference is checked against. What the
        document's own validators refuse here (`ValidationError`, `PanglossWriteError`) is raised as it is: `judged`
        takes it that the place takes no suggestion"""
        from pangloss_cypher.write_functions import to_db_model
        from pangloss_cypher.write_plan import ReferenceToExisting, plan_update
        from pangloss_models import Entity, ModelRegistry

        placeholder = Alternative(
            str(uuid.uuid4()), placeholder_type(unknown.type), 100
        )
        prepared = await rewriting.prepare_rewrite(
            self.model,
            UUID(self.head_id),
            self.replacement(unknown, shape, [placeholder]),
            read=self.read,
        )
        if not isinstance(prepared, rewriting.Prepared):
            return []
        planned = plan_update(to_db_model(prepared.update))
        for _source, relation, _first in planned.walk():
            target = relation.target
            if (
                isinstance(target, ReferenceToExisting)
                and target.value == placeholder.id
            ):
                # (of entities only: a place may take a stand-in, a document, beside them)
                return sorted(
                    name
                    for name in target.allowed_types
                    if isinstance(found := ModelRegistry._model_dict.get(name), type)
                    and issubclass(found, Entity)
                )
        return []

    def asked(
        self, unknown: Any, decision: Decision, takes: Sequence[str]
    ) -> judging.Asked:
        """What the judge is given about one stand-in: plain data, made for this call (copies: nothing the worker
        reads afterwards; `takes` is the worker's own list, given as a tuple)"""
        import copy

        shape = cast(Shape, self.shapes[unknown.id])
        parent = self.above.get(unknown.id)
        return judging.Asked(
            stand_in={
                "id": unknown.id,
                "label": unknown.label,
                "stood_for": unknown.type,
                "uris": [str(uri) for uri in self.parts[unknown.id].get("uris") or ()],
                "place": place_of(unknown.id, self.above),
                "held_by": self.types.get(parent[0]) if parent else None,
            },
            document=copy.deepcopy(self.document),
            candidates=copy.deepcopy(self.answered.get(unknown.id, [])),
            decision={
                "alternatives": [
                    {"id": one.id, "type": one.type, "percent": one.percent}
                    for one in decision.alternatives
                ],
                "reason": decision.reason,
            },
            takes={"shape": shape, "classes": tuple(takes)},
        )

    async def tried(self, unknown: Any, verdict: Verdict, takes: Sequence[str]) -> None:
        """What only the write can find of a judge's own alternatives, found before it by the write's own checks, as
        far as they do not write (`JudgeFailed`), on the head's `Update` with that one suggestion in the stand-in's
        place: first a class the place does not take (`takes`, the worker's own list: the clearest message); the
        `Update` not valid (an unknown field of the class, a value it does not take) or refused as the write's model
        is made (`to_db_model`: a class's `@update_validator`); the `@before_create`s and `@before_update`s the write
        runs (`write_checks.check_before_update`, after `fill_labels`, as the write runs them); then, in one read
        transaction, an entity of the judge's that is not there, is deleted, or was merged into another (named: the
        write would write the survivor, not what the judge said), and the write's own check of every reference the
        suggestion adds (`validate_write.check_references_exist` of the suggestion's part of the plan: there, not
        deleted, of a class the place takes by `has_allowed_label`, so a type of a typology switched off is
        refused), the references in its `fields` too. Run as the write is (`as_toolchain`)"""
        from pangloss_cypher.validate_write import check_references_exist
        from pangloss_cypher.write_functions import read_labels, to_db_model
        from pangloss_cypher.write_plan import PlannedNode, WritePlan, plan_update
        from pangloss_models.label_templates import fill_labels
        from pangloss_models.write_checks import check_before_update

        name = self.judge.name
        alternatives = verdict.decision.alternatives
        shape = cast(Shape, self.shapes[unknown.id])
        foreign = [one for one in alternatives if one.type not in takes]
        if foreign:
            raise JudgeFailed(
                name,
                f"it suggests {', '.join(f'{one.type} {one.id}' for one in foreign)}: this place takes "
                f"{', '.join(takes) or 'no entity'}",
            )
        made = str(uuid.uuid4())
        view = self.view

        async def as_it_is() -> Any:
            return view

        try:
            prepared = await rewriting.prepare_rewrite(
                self.model,
                UUID(self.head_id),
                self.replacement(unknown, shape, alternatives, verdict.fields, id=made),
                read=self.read,
            )
            if not isinstance(prepared, rewriting.Prepared):
                raise JudgeFailed(
                    name, "what it suggests could not be put in the stand-in's place"
                )
            db_instance = to_db_model(prepared.update)
            await fill_labels(db_instance, read_labels)
            await check_before_update(db_instance, as_it_is)
        except NOT_REFUSALS:
            raise
        except (ValidationError, PanglossWriteError) as error:
            raise JudgeFailed(
                name, f"what it suggests would be refused by the write: {error}"
            ) from None
        part = next(
            (
                relation.target
                for _source, relation, _first in plan_update(db_instance).walk()
                if isinstance(relation.target, PlannedNode)
                and relation.target.id == made
            ),
            None,
        )

        @database().read_transaction
        async def read(tx: Transaction) -> dict[str, dict[str, Any]]:
            result = await tx.run(
                ENTITIES_QUERY, ids=sorted({one.id for one in alternatives})
            )
            found = {
                str(row["id"]): {
                    "labels": row["labels"],
                    "deleted": row["deleted"],
                    "merged_into": row["merged_into"],
                }
                async for row in result
            }
            if part is not None and not any(
                not (node := found.get(one.id) or {}).get("labels")
                or node["deleted"]
                or node["merged_into"] is not None
                for one in alternatives
            ):
                # (the write's own check, on the suggestion's part of the plan alone: what the rest of the head
                # names is the head's, not the judge's)
                await check_references_exist(
                    cast(Any, tx), WritePlan(head=part, is_update=True)
                )
            return found

        try:
            found = await read()
        except PanglossWriteError as error:
            raise JudgeFailed(
                name, f"what it suggests would be refused by the write: {error}"
            ) from None
        wrong = []
        for one in alternatives:
            node = found.get(one.id) or {}
            if not node.get("labels"):
                wrong.append(f"{one.type} {one.id} is not there")
            elif node["deleted"]:
                wrong.append(f"{one.type} {one.id} is deleted")
            elif node["merged_into"] is not None:
                wrong.append(
                    f"{one.type} {one.id} was merged into {node['merged_into']} (name that one)"
                )
        if wrong:
            raise JudgeFailed(
                name, f"it suggests what cannot be written: {'; '.join(wrong)}"
            )


async def judged(
    view: Any,
    unknown: Any,
    found: Any,
    decision: Decision,
    *,
    asking: Judging | None = None,
) -> Verdict:
    """Between the decision and the write, outside any transaction: with no judge (`asking` None), the decision
    unchanged. With one: what the place takes found (`Judging.takes`, as the toolchain and not as an admin, in a copy
    of the context); it is asked (`Judging.asked`, `judging.call` within its timeout, as the toolchain and not as an
    admin), its answer checked (`judging.checked`), and its own alternatives tried before the write (`Judging.tried`,
    as the write runs, in a copy of the context). `JudgeFailed` if it raised (its own `CancelledError` too), did not
    answer in time, found the worker's threads all busy, answered badly, or suggested what the write would refuse.
    A place the document's own validators refuse an identification in (met in `Judging.takes`) takes no suggestion:
    the judge is not asked, and the decision is unchanged, as with no judge"""
    if asking is None:
        return Verdict(decision)
    judge = asking.judge
    shape = cast(Shape, asking.shapes[unknown.id])
    try:
        # (the worker's own list, which the answer is checked against: the judge is given a copy. Made as the judge
        # runs, and apart: what the document's validators set reaches neither the worker nor its write)
        with as_toolchain(asking.seen.toolchain, admin=False):
            takes = await _apart(asking.takes(unknown, shape))
    except NOT_REFUSALS:
        raise
    except (PanglossWriteError, ValidationError) as error:
        # (the document refuses an identification in this place: it takes no suggestion, the judge is not asked of
        # it, and it goes on as with no judge: the worker's decision, left and noted as tried if it is nothing, and
        # refused by the write if it is not)
        logger.debug(
            "Reconcile: the judge %s is not asked of the stand-in %s (%r): its place takes no suggestion: %s",
            judge.name,
            unknown.id,
            unknown.label,
            error,
        )
        return Verdict(decision)
    asked = asking.asked(unknown, decision, takes)
    try:
        with as_toolchain(asking.seen.toolchain, admin=False):
            answer = await judging.call(
                judge.function, asked, judge.timeout, threads=judge.threads
            )
    except judging.TimedOut:
        raise JudgeFailed(
            judge.name, f"it did not answer within {judge.timeout:g} s"
        ) from None
    except judging.Busy as error:
        raise JudgeFailed(judge.name, str(error)) from None
    except judging.JudgeCancelled as error:
        raise JudgeFailed(judge.name, str(error), error) from None
    except Exception as error:  # noqa: BLE001
        raise JudgeFailed(
            judge.name, f"it raised {type(error).__name__}: {error}", error
        ) from None
    try:
        verdict = judging.checked(answer, shape, decision)
    except judging.BadAnswer as error:
        raise JudgeFailed(judge.name, f"its answer is refused: {error}") from None
    if verdict.by_judge and verdict.decision.suggested:
        # (as the write runs, and apart: what its before-hooks note reaches neither the worker nor the write)
        with as_toolchain(asking.seen.toolchain):
            await _apart(asking.tried(unknown, verdict, takes))
    return verdict


async def _apart[T](work: Coroutine[Any, Any, T]) -> T:
    """`work` run to its end in a copy of the context (its own task, awaited, and cancelled with the worker's): what
    it sets there (`ContextVar.set`: a before-hook's notes, such as the library's `confirmed_in_write`) reaches
    neither the worker nor what it does next"""
    return await asyncio.create_task(work, context=contextvars.copy_context())


def _suggested_row(
    id: str,
    head: str,
    stand_in: str,
    at: datetime.datetime,
    found: Any,
    decision: Decision,
    shape: Shape,
    seen: Seen,
    *,
    judged: bool = False,
) -> dict[str, Any]:
    """What is kept of a suggestion written (`PGReconcileSuggested`): ids and numbers only, as a shown record keeps
    them (`decisions.rows_of` of the worker's own candidates, `displayed` the list the worker's decision was made on,
    a project's judge or not), the alternatives written and their shape, and today's signatures; and `judged: true`
    when a project's judge changed what was written (its own alternatives), absent otherwise. No user"""
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
        **({"judged": True} if judged else {}),
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
        worker.threads.shutdown()
        await worker.give_up_lease()


# --- what is stored: the trigger (step 10.5e) -----------------------------------------------------------------------

# Heads read at a time by `mark_stored` (each page one read and one write)
PAGE = 1000


class NotSuggestible(ValueError):
    """`mark_stored` was given a name that is no class that can hold a stand-in (nor one above such a class)"""


@dataclasses.dataclass(frozen=True)
class Marked:
    """What `mark_stored` did: the heads it marked, those that had a mark of the kind already (left as they were, or,
    with `again`, marked again), the stand-ins both hold, and the stand-ins tried that were forgotten (`again`)"""

    marked: int = 0
    already: int = 0
    stand_ins: int = 0
    forgotten: int = 0

    def as_json(self) -> dict[str, int]:
        return {
            "marked": self.marked,
            "already": self.already,
            "standIns": self.stand_ins,
            "forgotten": self.forgotten,
        }


# (a page of the heads that hold a stand-in of one class, by its label (an index of every document class's label),
# after the last head of the page before: a head is the stand-in's `head_node_id`, or the stand-in itself)
STORED_PAGE_QUERY = """
MATCH (s:{label})
WITH s, coalesce(s.head_node_id, s.id) AS head
WHERE head > $after
WITH head, collect(s.id) AS stand_ins
ORDER BY head
LIMIT $page
RETURN head, stand_ins
"""

# (of those, the heads that the worker would not leave: of a class given, not deleted, unpublished)
STORED_HEADS_QUERY = f"""
UNWIND $heads AS id
MATCH (h:HeadNode {{id: id}})
WHERE h.type IN $types AND NOT {fragments.deleted("h")} AND NOT {fragments.published("h")}
RETURN h.id AS id, h.type AS type
"""

FORGET_STAND_INS_QUERY = f"""
UNWIND $ids AS id
MATCH (t:{TRIED} {{stand_in: id}})
DELETE t
RETURN count(*) AS n
"""


def stand_in_labels() -> list[str]:
    """The labels a stand-in is found by: those of the stand-ins' documents (`marking.stand_in_documents`), less one
    whose class is below another of them (its nodes have the label of the class above)"""
    from pangloss_models import ModelRegistry

    names = sorted(marking.stand_in_documents())
    models = {name: ModelRegistry._model_dict.get(name) for name in names}

    def below_another(name: str) -> bool:
        model = models[name]
        return isinstance(model, type) and any(
            other != name
            and isinstance(models[other], type)
            and issubclass(model, models[other])  # type: ignore
            for other in names
        )

    return [name for name in names if not below_another(name)]


def classes_to_mark(classes: Sequence[str] | None = None) -> list[str]:
    """The classes of head `mark_stored` marks: every class that can hold a stand-in (`marking.suggestible_classes`),
    or those that are among the classes named or below one of them. `NotSuggestible` for a name that is neither such
    a class nor one above such a class, with the names there are"""
    from pangloss_models import ModelRegistry

    suggestible = sorted(marking.suggestible_classes())
    if classes is None:
        return suggestible
    chosen: set[str] = set()
    unknown = []
    for name in classes:
        named = ModelRegistry._model_dict.get(name)
        found = [
            each
            for each in suggestible
            if isinstance(named, type)
            and issubclass(ModelRegistry._model_dict[each], named)
        ]
        if not found:
            unknown.append(name)
        chosen.update(found)
    if unknown:
        raise NotSuggestible(
            f"{', '.join(repr(name) for name in unknown)}: no class that can hold a stand-in, nor above one. "
            + (
                f"The classes that can: {', '.join(suggestible)}"
                if suggestible
                else "No class can (none of the installed apps has a stand-in, or no model takes one)"
            )
        )
    return sorted(chosen)


async def mark_stored(
    classes: Sequence[str] | None = None, again: bool = False, *, page: int = PAGE
) -> Marked:
    """Leave for the worker the documents already stored that hold a stand-in now (what follows a bulk load, or a
    setting turned on: `pangloss reconcile suggest`, `POST /api/reconcile/suggest`, the admin job `reconcile_suggest`):
    each head of a class that can hold one (`classes`: only those named and those below them, `classes_to_mark`),
    with a stand-in in it, not deleted, unpublished (the worker would leave a published one), and **with no mark of
    the kind**, marked; one that has a mark keeps it as it is, its token and its claim (`pending.mark_unmarked`).
    `again`: first, what was tried of the stand-ins of those heads (marked or not) is forgotten, so that the worker
    asks again for those it left; and a head that has a mark is marked again (a new token, its claim taken off: a
    worker that holds the claim writes nothing of it, `still_mine`, and it is done again).

    In pages of `page` heads, in the order of their ids: each page one read (the stand-ins by their class's label,
    and their heads by `HeadNode(id)`) and one write (the marks, and what is forgotten). After the last page, the
    worker of this process is woken (`hooks.emit_work_marked`, once for each class marked). Gives what it did"""
    from pangloss_models import ModelRegistry, hooks

    types = classes_to_mark(classes)
    labels = stand_in_labels()
    if not types or not labels:
        return Marked()
    db = database()
    after = ""
    marked = already = stand_ins = forgotten = 0
    marked_types: set[str] = set()
    while True:

        @db.read_transaction
        async def read(
            tx: Transaction, after: str = after
        ) -> tuple[list[tuple[str, str, list[str]]], str | None]:
            found: dict[str, list[str]] = {}
            cut: str | None = None
            for label in labels:
                rows = [
                    row
                    async for row in await tx.run(
                        STORED_PAGE_QUERY.format(label=label), after=after, page=page
                    )
                ]
                for row in rows:
                    found.setdefault(str(row["head"]), []).extend(
                        str(id) for id in row["stand_ins"]
                    )
                # (a label whose page is full may have heads after its last: the page ends there)
                if len(rows) >= page:
                    last = str(rows[-1]["head"])
                    cut = last if cut is None else min(cut, last)
            heads = sorted(h for h in found if cut is None or h <= cut)
            if not heads:
                return [], None
            kept = [
                (str(row["id"]), str(row["type"]), sorted(set(found[str(row["id"])])))
                async for row in await tx.run(
                    STORED_HEADS_QUERY, heads=heads, types=types
                )
            ]
            return kept, (heads[-1] if cut is not None else None)

        heads, next_after = await read()

        if heads:

            @db.write_transaction
            async def write(
                tx: Transaction, heads: list[tuple[str, str, list[str]]] = heads
            ) -> tuple[list[str], int]:
                gone = 0
                if again:
                    record = await (
                        await tx.run(
                            FORGET_STAND_INS_QUERY,
                            ids=[id for _, _, ids in heads for id in ids],
                        )
                    ).single()
                    gone = int(record["n"]) if record else 0
                made = await pending.mark_unmarked(
                    tx, KIND, [h for h, _, _ in heads], again=again
                )
                return made, gone

            made, gone = await write()
            new = set(made)
            marked += len(new)
            already += len(heads) - len(new)
            stand_ins += sum(len(ids) for _, _, ids in heads)
            forgotten += gone
            marked_types.update(type_name for h, type_name, _ in heads if h in new)
        if next_after is None:
            break
        after = next_after
    for type_name in sorted(marked_types):
        model = ModelRegistry._model_dict.get(type_name)
        if isinstance(model, type):
            hooks.emit_work_marked(model)
    logger.info(
        "Reconcile: %s documents left for the worker, %s were already (%s stand-ins; %s tried forgotten)",
        marked,
        already,
        stand_ins,
        forgotten,
    )
    return Marked(marked, already, stand_ins, forgotten)


TRIED_LEFT_QUERY = f"""
MATCH (t:{TRIED})
MATCH (n:PGIndexableNode {{id: t.stand_in}})
WHERE n.head_node_id IS NOT NULL
RETURN count(t) AS n
"""

SUGGESTED_UNCONFIRMED_QUERY = f"""
MATCH (s:{SUGGESTED})
MATCH (n:PGIndexableNode {{id: s.id}})
WHERE n.head_node_id IS NOT NULL AND any(label IN labels(n) WHERE label IN $kinds)
RETURN count(s) AS n
"""


async def status() -> dict[str, Any]:
    """`pending_status`, and what the worker kept that is still of use: the stand-ins it tried and left that are still
    in a document (`tried`), and the suggestions it wrote that are still suggestions, not confirmed nor gone
    (`suggested`; by the rule of `sweep_kept`)"""
    from pangloss_models import hooks

    found = await pending_status()
    kinds = hooks.unconfirmed_classes() or [settings.suggest_as()]

    @database().read_transaction
    async def read(tx: Transaction) -> tuple[int, int]:
        tried = await (await tx.run(TRIED_LEFT_QUERY)).single()
        suggested = await (
            await tx.run(SUGGESTED_UNCONFIRMED_QUERY, kinds=kinds)
        ).single()
        return (
            int(tried["n"]) if tried else 0,
            int(suggested["n"]) if suggested else 0,
        )

    found["tried"], found["suggested"] = await read()
    return found


def status_json(found: Mapping[str, Any]) -> dict[str, Any]:
    """`status()` as the API gives it (camelCase)"""
    return {
        "pending": found["pending"],
        "claimed": found["claimed"],
        "oldest": found["oldest"],
        "waitingForVectors": found["waiting_for_vectors"],
        "rebuilding": found["rebuilding"],
        "profile": found["profile"],
        "lease": found["lease"],
        "tried": found["tried"],
        "suggested": found["suggested"],
    }


async def pending_status() -> dict[str, Any]:
    """What is marked and claimed, and when the oldest was marked; how many wait for the vectors (marked after the
    oldest mark of the vectors' kind), whether a rebuild of them holds its lease, and the state of the profile
    candidates are found by (`profile`: `ok`, or `pending`, `rebuild_due`, while nothing is claimed); and who holds the
    worker's lease (`{holder, until}`, or None)"""

    @database().read_transaction
    async def read(tx: Transaction) -> dict[str, Any]:
        found = dict(await pending.count(tx, KIND))
        held = await _waiting(tx)
        waiting = 0
        if held.oldest is not None:
            record = await (
                await tx.run(WAITING_QUERY, kind=KIND, before=held.oldest)
            ).single()
            waiting = int(record["waiting"]) if record else 0
        lease = await (await tx.run(LEASE_READ_QUERY, kind=KIND)).single()
        found["waiting_for_vectors"] = waiting
        found["rebuilding"] = held.rebuilding
        found["profile"] = held.profile
        found["lease"] = (
            {"holder": lease["holder"], "until": lease["until"]}
            if lease is not None and lease["holder"] is not None
            else None
        )
        return found

    return await read()
