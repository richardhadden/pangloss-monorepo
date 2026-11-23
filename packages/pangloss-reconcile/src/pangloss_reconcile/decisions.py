"""What was offered for a stand-in, and what was chosen of it: kept so that reconciliation can learn from the decisions
people make (step 11.4 of implementation_docs/similarity-build-plan.md; implementation_docs/reconcile.md, "Decisions
kept"). Two kinds of plain node (not models: in no list, search, RDF or vectors), made by this package's migration
(`structure.py`):

    (:PGReconcileShown {stand_in, user, at, rows, profile, signature, parts, weights, features})
        what the stored route offered a user for a stand-in: one for each stand-in and user, replaced by the next
        request of that user for that stand-in (`keep_shown`)
    (:PGReconcileExample {stand_in, at, rows, profile, signature, parts, weights, features, taken})
        what was offered and which row was chosen: one for each stand-in, replaced by a later decision (`heard`)

`rows` is JSON: the ten best of the items found by the hand-set score (`Found.best`, before the cut by the least
score and `limit`), each `{id, type, scores, shared, score, displayed}` (`shared` the count of the document's entities
it is named with; `displayed` whether it was in the answer the person was given), by score and then id. `parts` is
JSON, each scored part's stored signature; `weights` JSON, `settings.weights()`; `signature` the profile's, of the
vectors in use. **Ids and numbers only**: no label of anything, and who decided is not in an example.

An example is made only of a decision that reached the database, by the person the list was shown to, soon after:
`heard`, a listener of `hooks.resolved` (raised after the write; never for review's `in_form`), when the resolution is
`direct`, by the user a shown record is of, within `RECONCILE_SHOWN_FOR` minutes of it (and not before it). Any
resolution of the stand-in removes its shown records, of every user, and one that makes no example removes an earlier
example of it; `sweep` removes those older than that, and those whose stand-in is no longer
a node of a document. `RECONCILE_KEEP_DECISIONS = False` writes nothing."""

import asyncio
import datetime
import json
import logging
from collections.abc import Collection, Mapping
from typing import Any

from pangloss_models import PanglossReadOnlyError, hooks

from pangloss_reconcile import settings

logger = logging.getLogger("pangloss.reconcile")

SHOWN = "PGReconcileShown"
EXAMPLE = "PGReconcileExample"

# The version of what a row of `rows` holds and how its numbers are made (each part's cosine, `shared`'s score and
# count, the score): raised when any of that changes, so that examples of another version are not learnt from
FEATURES = 1

# How many shown records the sweep removes in one transaction
SWEEP_PAGE = 1000

# How many times a shown record's write is tried when another request for the same stand-in and user made it at the
# same moment (the second meets the unique constraint, and then finds the first's)
WRITE_TRIES = 3

KEEP_QUERY = f"""
MERGE (s:{SHOWN} {{stand_in: $stand_in, user: $user}})
SET s.at = $at, s.rows = $rows, s.profile = $profile, s.signature = $signature, s.parts = $parts,
    s.weights = $weights, s.features = $features
"""

SHOWN_QUERY = f"""
MATCH (s:{SHOWN} {{stand_in: $stand_in}})
RETURN s.user AS user, s.at AS at, s.rows AS rows, s.profile AS profile, s.signature AS signature,
    s.parts AS parts, s.weights AS weights, s.features AS features
"""

EXAMPLE_QUERY = f"""
MERGE (e:{EXAMPLE} {{stand_in: $stand_in}})
SET e.at = $at, e.rows = $rows, e.profile = $profile, e.signature = $signature, e.parts = $parts,
    e.weights = $weights, e.features = $features, e.taken = $taken
"""

FORGET_QUERY = f"""
MATCH (e:{EXAMPLE} {{stand_in: $stand_in}})
DELETE e
"""

REMOVE_QUERY = f"""
MATCH (s:{SHOWN} {{stand_in: $stand_in}})
DELETE s
"""

# (a stand-in still in a document is a node below a head, as `stored.NODE_QUERY` finds it)
SWEEP_QUERY = f"""
MATCH (s:{SHOWN})
OPTIONAL MATCH (n:PGIndexableNode {{id: s.stand_in}})
WITH s, n
WHERE s.at < $before OR n IS NULL OR n.head_node_id IS NULL
WITH s LIMIT $limit
DELETE s
RETURN count(*) AS n
"""


def _database() -> Any:
    from pangloss_core import backend

    return backend.current().database()


def _installed() -> bool:
    """Whether the app is installed in the project's settings (a process that imported it without installing it
    keeps nothing)"""
    from pangloss_core import settings as core_settings

    found = core_settings.__dict__.get("SETTINGS")
    return settings.APP in list(getattr(found, "INSTALLED_APPS", None) or [])


def _native(value: Any) -> Any:
    return value.to_native() if hasattr(value, "to_native") else value


def rows_of(found: Any, displayed: Collection[str]) -> list[dict[str, Any]]:
    """The rows of what was offered for an unknown (`Found.best`, as ranked): ids and numbers only"""
    return [
        {
            "id": candidate.id,
            "type": candidate.type,
            "scores": dict(candidate.scores),
            "shared": len(candidate.shared),
            "score": candidate.score,
            "displayed": candidate.id in displayed,
        }
        for candidate in found.best
    ]


def displayed_in(answer: Mapping[str, Any], unknown_id: str) -> set[str]:
    """The ids of the candidates an answer gave for an unknown (those the reader may see, after `api.answer`'s
    views)"""
    return {
        candidate["id"]
        for unknown in answer.get("unknowns", [])
        if unknown["id"] == unknown_id
        for candidate in unknown["candidates"]
    }


def record_of(found: Any, answer: Mapping[str, Any], states: Any) -> dict[str, Any]:
    """The properties of a shown record of an unknown, but for its stand-in, user and time: the rows, and what makes
    their numbers comparable (the profile and its signature, each scored part's signature, the weights, `FEATURES`)"""
    from pangloss_reconcile.score import SHARED

    name = answer["profile"]
    rows = rows_of(found, displayed_in(answer, found.unknown.id))
    scored = sorted({part for row in rows for part in row["scores"] if part != SHARED})
    profile_state = states.profiles.get(name)
    return {
        "rows": json.dumps(rows),
        "profile": name,
        "signature": profile_state.signature if profile_state is not None else "",
        "parts": json.dumps(
            {
                part: states.parts[part].signature
                for part in scored
                if part in states.parts
            },
            sort_keys=True,
        ),
        "weights": json.dumps(settings.weights(), sort_keys=True),
        "features": FEATURES,
    }


def _a_conflict(error: Exception) -> bool:
    """Whether a write failed because another made the same record at the same moment (the unique constraint: Neo4j's
    `ConstraintError`, Memgraph's commit refused for a unique constraint)"""
    import neo4j.exceptions

    if isinstance(error, neo4j.exceptions.ConstraintError):
        return True
    return (
        isinstance(error, neo4j.exceptions.Neo4jError)
        and "constraint" in str(error).lower()
    )


async def keep_shown(
    found: Any, answer: Mapping[str, Any], states: Any, user: str
) -> None:
    """(the stored route, after its answer is made, when its `status` is `"ok"`) Keep what was offered `user` for the
    unknown `found` (`candidates.Found`): one record for the stand-in and user, replacing an earlier one, in one
    write. Nothing with `RECONCILE_KEEP_DECISIONS` false, nor while the database is being migrated; a failure is
    logged, and never fails the answer"""
    if not settings.keep_decisions():
        return
    try:
        properties = {
            **record_of(found, answer, states),
            "stand_in": found.unknown.id,
            "user": user,
            "at": datetime.datetime.now(datetime.UTC),
        }
        database = _database()

        @database.write_transaction
        async def write(tx: Any) -> None:
            await (await tx.run(KEEP_QUERY, **properties)).consume()

        for tried in range(1, WRITE_TRIES + 1):
            try:
                await write()
                return
            except Exception as error:
                if tried == WRITE_TRIES or not _a_conflict(error):
                    raise
                await asyncio.sleep(0.01 * tried)
    except PanglossReadOnlyError:
        # (the database is being migrated: nothing is written, as no write is, and that is no failure)
        return
    except Exception:
        logger.exception(
            "What was offered for the stand-in %s could not be kept", found.unknown.id
        )


def _fresh(shown_at: Any, decided_at: datetime.datetime, minutes: float) -> bool:
    shown = _native(shown_at)
    if not isinstance(shown, datetime.datetime):
        return False
    if shown.tzinfo is None:
        shown = shown.replace(tzinfo=datetime.UTC)
    # (a list dated after the decision was not seen before it: a request still on its way when the person decided)
    return (
        datetime.timedelta(0)
        <= decided_at - shown
        < datetime.timedelta(minutes=minutes)
    )


async def heard(resolution: hooks.Resolution) -> None:
    """(`hooks.resolved`) A stand-in was resolved: in one write transaction, the shown records of it read; if the
    resolution was made directly (`direct`) by a user who was shown a list for it within `RECONCILE_SHOWN_FOR`
    minutes, the example of the stand-in written from that list (replacing an earlier one), `taken` the row that is
    the entity put in its place or null, and otherwise an earlier example of the stand-in removed (it was resolved
    before, and is there again: that decision was undone); and every shown record of the stand-in removed. Nothing with
    `RECONCILE_KEEP_DECISIONS` false. (The transaction may be run again by the driver: it does only what can be done
    twice)"""
    if not _installed() or not settings.keep_decisions():
        return
    minutes = settings.shown_for()
    stand_in = str(resolution.stand_in_id)
    entity = str(resolution.entity_id)
    database = _database()

    @database.write_transaction
    async def decide(tx: Any) -> None:
        result = await tx.run(SHOWN_QUERY, stand_in=stand_in)
        shown = [record.data() async for record in result]
        mine = [record for record in shown if record["user"] == resolution.user]
        if resolution.direct and mine and _fresh(mine[0]["at"], resolution.at, minutes):
            record = mine[0]
            ids = {row["id"] for row in json.loads(record["rows"] or "[]")}
            await (
                await tx.run(
                    EXAMPLE_QUERY,
                    stand_in=stand_in,
                    at=resolution.at,
                    rows=record["rows"],
                    profile=record["profile"],
                    signature=record["signature"],
                    parts=record["parts"],
                    weights=record["weights"],
                    features=record["features"],
                    taken=entity if entity in ids else None,
                )
            ).consume()
        else:
            # (a stand-in resolved again was there again: the earlier decision was undone, by a restore say, and
            # is no example of what it is now said to be)
            await (await tx.run(FORGET_QUERY, stand_in=stand_in)).consume()
        if shown:
            await (await tx.run(REMOVE_QUERY, stand_in=stand_in)).consume()

    try:
        await decide()
    except PanglossReadOnlyError:
        return


async def sweep(*, page: int = SWEEP_PAGE) -> int:
    """Remove the shown records older than `RECONCILE_SHOWN_FOR` minutes (no example can be made of them now), and
    those whose stand-in is no longer a node of a document (it went with a rewrite of its document), in pages. Gives
    how many went"""
    before = datetime.datetime.now(datetime.UTC) - datetime.timedelta(
        minutes=settings.shown_for()
    )
    database = _database()

    @database.write_transaction
    async def remove(tx: Any) -> int:
        record = await (await tx.run(SWEEP_QUERY, before=before, limit=page)).single()
        return int(record["n"]) if record else 0

    total = 0
    while True:
        gone = await remove()
        total += gone
        if gone < page:
            return total


def install() -> None:
    """(`pangloss_reconcile._install`)"""
    if heard not in hooks.resolved:
        hooks.resolved.append(heard)
