"""Work left pending by writes, for an installed app to do in the background (`pangloss_models.hooks.pending_work`).

    (:PGPending {key: "derive:<head id>", kind: "derive", head_id, token, at, claimed_until, claim})

A write marks each head node it writes (and the entities it makes) with each kind of work the apps ask for its class,
in the write's own transaction: so a write that is committed is never forgotten. One node per kind and head, however
many times the head is written; each mark gives it a new `token`. A worker:

1. **claims** some (`claim`): those not claimed, or whose claim has run out (`claimed_until`), are given a claim and a
   time until which it holds; it gets each one's head id and token;
2. does the work, reading the heads as they are now;
3. **completes** them (`complete`), in the transaction that writes what it found: a node is deleted only if its token
   is still the one claimed. A head written again while it was worked on has a new token, so it stays pending, and is
   done again.

A worker that stops between 1 and 3 leaves its claims, which run out, and are claimed again.
"""

import time
import uuid
from collections.abc import Iterable
from typing import Any

from pangloss_models import hooks

from pangloss_core import backend

from pangloss_cypher import transaction

# (a transaction of the kit's writes, or of an add-on's worker, which has the backend's `Transaction`)
type Transaction = transaction.Transaction | backend.Transaction

LABEL = "PGPending"


def key_of(kind: str, head_id: str) -> str:
    return f"{kind}:{head_id}"


def now() -> float:
    """(Times are seconds since the epoch: compared the same way by every backend)"""
    return time.time()


MARK_QUERY = f"""
UNWIND $marks AS mark
MERGE (p:{LABEL} {{key: mark.key}})
SET p.kind = mark.kind, p.head_id = mark.head_id, p.token = mark.token, p.at = $at
"""


async def mark(tx: Transaction, kind: str, head_ids: Iterable[Any]) -> None:
    """Mark the heads as pending for the kind of work (in the transaction of the write)"""
    marks = [
        {
            "key": key_of(kind, str(head_id)),
            "kind": kind,
            "head_id": str(head_id),
            "token": str(uuid.uuid4()),
        }
        for head_id in head_ids
    ]
    if marks:
        await (await tx.run(MARK_QUERY, marks=marks, at=now())).consume()


async def mark_written(
    tx: Transaction, model: type, head_id: Any, created_entities: Iterable[Any] = ()
) -> None:
    """Mark a head node that a write wrote (and the entities it made) with the work the installed apps want done
    after a write of its class. Nothing, if none wants any"""
    if not hooks.pending_work:
        return
    by_kind: dict[str, list[Any]] = {}
    for kind in hooks.pending_kinds(model):
        by_kind.setdefault(kind, []).append(head_id)
    for entity in created_entities:
        for kind in hooks.pending_kinds(entity._owner):
            by_kind.setdefault(kind, []).append(entity.id)
    for kind, ids in by_kind.items():
        await mark(tx, kind, ids)


CLAIM_QUERY = f"""
MATCH (p:{LABEL})
WHERE p.kind = $kind AND (p.claimed_until IS NULL OR p.claimed_until < $now)
WITH p LIMIT $limit
SET p.claimed_until = $until, p.claim = $claim
RETURN p.head_id AS head_id, p.token AS token
"""


async def claim(
    tx: Transaction, kind: str, limit: int, lease: float
) -> list[tuple[str, str]]:
    """Claim up to `limit` pending heads of the kind, for `lease` seconds: their ids and tokens"""
    at = now()
    result = await tx.run(
        CLAIM_QUERY,
        kind=kind,
        now=at,
        until=at + lease,
        limit=limit,
        claim=str(uuid.uuid4()),
    )
    return [(record["head_id"], record["token"]) async for record in result]


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
