"""Work left pending by writes, for an installed app to do in the background (`pangloss_models.hooks.pending_work`).

    (:PGPending {key: "derive:<head id>", kind: "derive", head_id, token, at, claimed_until, claim})

A write marks each head node it writes (and the entities it makes) with each kind of work the apps ask for its class,
in the write's own transaction: so a write that is committed is never forgotten. One node per kind and head, however
many times the head is written; each mark gives it a new `token`. A worker:

1. **claims** some (`claim`): those not claimed, or whose claim has run out (`claimed_until`), are given a claim and a
   time until which it holds; it gets each one's head id and token. (`before=`: only those marked before a time, the
   oldest first, for a worker whose work waits for another kind's; `renew` gives the claims more time while the work
   goes on);
2. does the work, reading the heads as they are now;
3. **completes** them (`complete`), in the transaction that writes what it found: a node is deleted only if its token
   is still the one claimed. A head written again while it was worked on has a new token, so it stays pending, and is
   done again.

A worker that stops between 1 and 3 leaves its claims, which run out, and are claimed again. A head that is marked
again while it is claimed is no longer claimed: its new mark can be claimed at once.

**What an update took away.** A mark says which head was written, not what it was before. For a kind that asks
(`hooks.pending_keeps_before`), an update reads the tree it is about to replace (`tree_before`) and its mark keeps
the ids of what that tree referred to and the labels of its nodes (`before_refs`, `before_labels`), joined
with what the mark already had: a head may be written twice before it is claimed. The worker reads them with
`before_of`. (A delete needs none of this: a deleted head keeps its nodes and edges.)

**What a write said.** A create or an update of a head gives `mark_written` its instructions
(`hooks.checked_instructions`), and `hooks.instructed_work` is asked with them: a kind it answers `True` is marked as
above, one it answers `False` has its mark taken off (`unmark`), claimed or not; a worker that held the claim then
completes nothing (`complete` finds no mark of its token, and gives 0). Every other write gives none, and nothing is
asked.
"""

import dataclasses
import time
import uuid
from collections.abc import Iterable, Mapping
from typing import Any, LiteralString, cast

from pangloss_models import hooks

from pangloss_core import backend

from pangloss_cypher import fragments, transaction

# (a transaction of the kit's writes, or of an add-on's worker, which has the backend's `Transaction`)
type Transaction = transaction.Transaction | backend.Transaction

LABEL = "PGPending"


def key_of(kind: str, head_id: str) -> str:
    return f"{kind}:{head_id}"


def now() -> float:
    """(Times are seconds since the epoch: compared the same way by every backend)"""
    return time.time()


# (a mark of a head that is claimed takes the claim off it: the claim was of the work the head needed before this
# write, which whoever holds it still completes or not by its token, and what the head needs now can be claimed at
# once, not when the old claim has run out)
MARK_QUERY = f"""
UNWIND $marks AS mark
MERGE (p:{LABEL} {{key: mark.key}})
SET p.kind = mark.kind, p.head_id = mark.head_id, p.token = mark.token, p.at = $at
REMOVE p.claimed_until, p.claim
"""


# (each list gains what it does not have yet. A mark that is completed is deleted, so the lists start again)
MARK_BEFORE_QUERY = (
    MARK_QUERY
    + """
SET p.before_refs = coalesce(p.before_refs, [])
        + [ref IN $before_refs WHERE NOT ref IN coalesce(p.before_refs, [])],
    p.before_labels = coalesce(p.before_labels, [])
        + [label IN $before_labels WHERE NOT label IN coalesce(p.before_labels, [])]
"""
)


@dataclasses.dataclass
class Before:
    """What a head's tree was before an update replaced it (or before several did)"""

    refs: set[str] = dataclasses.field(default_factory=set)
    """The ids of what its nodes referred to: entities, and the nodes of the tree itself that a relation is to (a
    stand-in for an entity is one)"""
    labels: set[str] = dataclasses.field(default_factory=set)
    """The labels of its nodes"""


async def mark(
    tx: Transaction, kind: str, head_ids: Iterable[Any], before: Before | None = None
) -> None:
    """Mark the heads as pending for the kind of work (in the transaction of the write). `before`: what the tree of
    the head was before this write, kept on the mark with what it already has (for one head)"""
    marks = [
        {
            "key": key_of(kind, str(head_id)),
            "kind": kind,
            "head_id": str(head_id),
            "token": str(uuid.uuid4()),
        }
        for head_id in head_ids
    ]
    if not marks:
        return
    if before is None:
        await (await tx.run(MARK_QUERY, marks=marks, at=now())).consume()
    else:
        await (
            await tx.run(
                MARK_BEFORE_QUERY,
                marks=marks,
                at=now(),
                before_refs=sorted(before.refs),
                before_labels=sorted(before.labels),
            )
        ).consume()


def keeps_before(
    *models: type | None, instructions: Mapping[str, str] | None = None
) -> bool:
    """Whether a write of a head of one of the classes leaves a mark that keeps what the head was before.
    `instructions`: those of the create or update of the first class (`hooks.instructed_work`, asked for it alone, as
    `mark_written` asks it)"""
    if not hooks.pending_keeps_before:
        return False
    if hooks.pending_work and any(
        kind in hooks.pending_keeps_before
        for model in models
        if model is not None
        for kind in hooks.pending_kinds(model)
    ):
        return True
    if instructions is None or not hooks.instructed_work or models[0] is None:
        return False
    return any(
        marked and kind in hooks.pending_keeps_before
        for kind, marked in hooks.instructed_kinds(models[0], instructions).items()
    )


# (two queries: each finds its nodes by an index. What is computed is not "referred to": `asserted`)
TREE_BEFORE_QUERIES = tuple(
    f"""
    MATCH (node:{label} {{{key}: $id}})
    RETURN labels(node) AS labels,
           [(node)-[edge]->(entity:PGIndexableNode)
            WHERE {fragments.forward("edge")} AND {fragments.asserted("edge")} | entity.id] AS refs
    """
    for label, key in (("HeadNode", "id"), ("PGIndexableNode", "head_node_id"))
)


async def tree_before(tx: Transaction, head_id: Any) -> Before:
    """The tree of a head as it is now, for an update that is about to replace it"""
    before = Before()
    for query in TREE_BEFORE_QUERIES:
        async for record in await tx.run(cast(LiteralString, query), id=str(head_id)):
            before.labels.update(record["labels"])
            before.refs.update(str(ref) for ref in record["refs"])
    return before


BEFORE_QUERY = f"""
UNWIND $keys AS key
MATCH (p:{LABEL} {{key: key}})
RETURN p.head_id AS head_id, coalesce(p.before_refs, []) AS refs, coalesce(p.before_labels, []) AS labels
"""


async def before_of(
    tx: Transaction, kind: str, head_ids: Iterable[Any]
) -> dict[str, Before]:
    """What the marks of these heads keep of what the heads were before (only those that keep something)"""
    keys = [key_of(kind, str(head_id)) for head_id in head_ids]
    found: dict[str, Before] = {}
    if keys:
        async for record in await tx.run(BEFORE_QUERY, keys=keys):
            if record["refs"] or record["labels"]:
                found[record["head_id"]] = Before(
                    set(record["refs"]), set(record["labels"])
                )
    return found


async def mark_written(
    tx: Transaction,
    model: type,
    head_id: Any,
    created_entities: Iterable[Any] = (),
    *,
    less: Iterable[str] = (),
    before: Before | None = None,
    instructions: Mapping[str, str] | None = None,
) -> None:
    """Mark a head node that a write wrote (and the entities it made) with the work the installed apps want done
    after a write of its class. Nothing, if none wants any. `less`: kinds that are not marked (whoever writes what
    it computed itself, `set_computed`, need not work it out again). `before`: what the head's tree was before an
    update (`tree_before`), kept on the marks of the kinds that ask for it.

    `instructions`: given only by a create and an update of a head, what the write said (checked; `{}` if it said
    nothing). Then `hooks.instructed_work` is asked, after the kinds of `pending_work`, and its answers applied: a mark
    for `True`, a standing mark taken off for `False` (`unmark`). `None` (every other write): it is not asked"""
    instructed = instructions is not None and bool(hooks.instructed_work)
    if not hooks.pending_work and not instructed:
        return
    left_out = set(less)
    entities = tuple(created_entities)
    if hooks.pending_work:
        by_kind: dict[str, list[Any]] = {}
        for kind in hooks.pending_kinds(model):
            if kind in left_out:
                continue
            if before is not None and kind in hooks.pending_keeps_before:
                await mark(tx, kind, [head_id], before)
            else:
                by_kind.setdefault(kind, []).append(head_id)
        for entity in entities:
            for kind in hooks.pending_kinds(entity._owner):
                if kind not in left_out:
                    by_kind.setdefault(kind, []).append(entity.id)
        for kind, ids in by_kind.items():
            await mark(tx, kind, ids)
    if instructed:
        await _apply_instructed(
            tx,
            model,
            head_id,
            entities,
            instructions,
            left_out,
            before,
        )


async def _apply_instructed(
    tx: Transaction,
    model: type,
    head_id: Any,
    entities: tuple[Any, ...],
    instructions: Mapping[str, str],
    left_out: set[str],
    before: Before | None,
) -> None:
    """(`mark_written`) what `hooks.instructed_work` answers for the head and the entities the write made"""
    marked: dict[str, list[Any]] = {}
    unmarked: dict[str, list[Any]] = {}
    for kind, yes in hooks.instructed_kinds(model, instructions).items():
        if kind in left_out:
            continue
        if yes and before is not None and kind in hooks.pending_keeps_before:
            await mark(tx, kind, [head_id], before)
        else:
            (marked if yes else unmarked).setdefault(kind, []).append(head_id)
    for entity in entities:
        for kind, yes in hooks.instructed_kinds(entity._owner, instructions).items():
            if kind not in left_out:
                (marked if yes else unmarked).setdefault(kind, []).append(entity.id)
    for kind, ids in marked.items():
        await mark(tx, kind, ids)
    for kind, ids in unmarked.items():
        await unmark(tx, kind, ids)


UNMARK_QUERY = f"""
UNWIND $keys AS key
MATCH (p:{LABEL} {{key: key}})
DELETE p
"""


async def unmark(tx: Transaction, kind: str, head_ids: Iterable[Any]) -> None:
    """Take the marks of the kind off these heads, claimed or not (in the transaction of the write that says so). A
    worker that holds a claim of one completes nothing (`complete` finds no mark of its token)"""
    keys = [key_of(kind, str(head_id)) for head_id in head_ids]
    if keys:
        await (await tx.run(UNMARK_QUERY, keys=keys)).consume()


CLAIM_QUERY = f"""
MATCH (p:{LABEL})
WHERE p.kind = $kind AND (p.claimed_until IS NULL OR p.claimed_until < $now)
WITH p LIMIT $limit
SET p.claimed_until = $until, p.claim = $claim
RETURN p.head_id AS head_id, p.token AS token
"""


# (the oldest first, and only those marked before a time: a worker whose work must wait for another kind's)
CLAIM_BEFORE_QUERY = f"""
MATCH (p:{LABEL})
WHERE p.kind = $kind AND (p.claimed_until IS NULL OR p.claimed_until < $now) AND p.at < $before
WITH p ORDER BY p.at LIMIT $limit
SET p.claimed_until = $until, p.claim = $claim
RETURN p.head_id AS head_id, p.token AS token
"""


async def claim(
    tx: Transaction,
    kind: str,
    limit: int,
    lease: float,
    *,
    before: float | None = None,
) -> list[tuple[str, str]]:
    """Claim up to `limit` pending heads of the kind, for `lease` seconds: their ids and tokens. `before`: only those
    marked before that time (`now()`'s seconds), the oldest first"""
    at = now()
    params: dict[str, Any] = {
        "kind": kind,
        "now": at,
        "until": at + lease,
        "limit": limit,
        "claim": str(uuid.uuid4()),
    }
    if before is None:
        result = await tx.run(CLAIM_QUERY, **params)
    else:
        result = await tx.run(CLAIM_BEFORE_QUERY, **params, before=before)
    return [(record["head_id"], record["token"]) async for record in result]


RENEW_QUERY = f"""
UNWIND $held AS held
MATCH (p:{LABEL} {{key: held.key}})
WHERE p.token = held.token AND p.claimed_until IS NOT NULL
SET p.claimed_until = $until
RETURN count(p) AS renewed
"""


async def renew(
    tx: Transaction, kind: str, held: Iterable[tuple[str, str]], lease: float
) -> int:
    """Give the claims of these heads (id, token) `lease` seconds more from now, while the work on them goes on: those
    whose mark is still the one claimed (not marked again, taken off or completed meanwhile). Gives how many"""
    rows = [{"key": key_of(kind, head_id), "token": token} for head_id, token in held]
    if not rows:
        return 0
    result = await tx.run(RENEW_QUERY, held=rows, until=now() + lease)
    record = await result.single()
    return record["renewed"] if record else 0


COMPLETE_QUERY = f"""
UNWIND $done AS done
MATCH (p:{LABEL} {{key: done.key}})
WHERE p.token = done.token
DELETE p
RETURN count(*) AS completed
"""


async def complete(tx: Transaction, kind: str, done: Iterable[tuple[str, str]]) -> int:
    """The work on these heads (id, token) is done: their marks go, if they were not marked again since. Gives how
    many went"""
    rows = [{"key": key_of(kind, head_id), "token": token} for head_id, token in done]
    if not rows:
        return 0
    result = await tx.run(COMPLETE_QUERY, done=rows)
    record = await result.single()
    return record["completed"] if record else 0


RELEASE_QUERY = f"""
UNWIND $keys AS key
MATCH (p:{LABEL} {{key: key}})
REMOVE p.claimed_until, p.claim
"""


async def release(tx: Transaction, kind: str, head_ids: Iterable[str]) -> None:
    """Give back claims without completing them (the work failed: it is tried again by the next claim)"""
    keys = [key_of(kind, head_id) for head_id in head_ids]
    if keys:
        await (await tx.run(RELEASE_QUERY, keys=keys)).consume()


COUNT_QUERY = f"""
MATCH (p:{LABEL})
WHERE p.kind = $kind
RETURN count(p) AS pending,
       count(CASE WHEN p.claimed_until IS NOT NULL AND p.claimed_until >= $now THEN 1 END) AS claimed,
       min(p.at) AS oldest
"""


async def count(tx: Transaction, kind: str) -> dict[str, Any]:
    """How many heads are pending for the kind, how many of them are claimed, and when the oldest was marked"""
    result = await tx.run(COUNT_QUERY, kind=kind, now=now())
    record = await result.single()
    return dict(record) if record else {"pending": 0, "claimed": 0, "oldest": None}
