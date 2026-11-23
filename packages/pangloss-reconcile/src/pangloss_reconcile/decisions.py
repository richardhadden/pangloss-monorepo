"""What was offered for a stand-in, and what was chosen of it: kept so that reconciliation can learn from the decisions
people make (step 11.4 of implementation_docs/similarity-build-plan.md; implementation_docs/reconcile.md, "Decisions
kept"). Two kinds of plain node (not models: in no list, search, RDF or vectors), made by this package's migration
(`structure.py`):

    (:PGReconcileShown {stand_in, user, at, rows, profile, signature, parts, weights, features, least})
        what the stored route offered a user for a stand-in: one for each stand-in and user, replaced by the next
        request of that user for that stand-in (`keep_shown`)
    (:PGReconcileExample {stand_in, at, rows, profile, signature, parts, weights, features, least, taken})
        what was offered and which row was chosen: one for each stand-in, replaced by a later decision (`heard`)

`rows` is JSON: the ten best of the items found by the hand-set score (`Found.best`, before the cut by the least
score and `limit`), each `{id, type, scores, shared, score, displayed}` (`shared` the count of the document's entities
it is named with; `displayed` whether it was in the answer the person was given), by score and then id. `parts` is
JSON, the stored signature of each part the weights weigh (but `shared`) that has been built; `weights` JSON, `settings.weights()`; `signature` the profile's, of the
vectors in use. **Ids and numbers only**: no label of anything, and who decided is not in an example.

What makes the numbers of rows comparable (`SIGNATURES`) is said by one function, `today`, which the stored route
writes, and which a fit (`fits.py`, step 11.5) and step 11.6 compare an example or a fit with (`of_today`).

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
    s.weights = $weights, s.features = $features, s.least = $least
"""

SHOWN_QUERY = f"""
MATCH (s:{SHOWN} {{stand_in: $stand_in}})
RETURN s.user AS user, s.at AS at, s.rows AS rows, s.profile AS profile, s.signature AS signature,
    s.parts AS parts, s.weights AS weights, s.features AS features, s.least AS least
"""

EXAMPLE_QUERY = f"""
MERGE (e:{EXAMPLE} {{stand_in: $stand_in}})
SET e.at = $at, e.rows = $rows, e.profile = $profile, e.signature = $signature, e.parts = $parts,
    e.weights = $weights, e.features = $features, e.least = $least, e.taken = $taken
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


# (the properties that make the numbers of rows comparable, as a shown record, an example and a fit hold them)
SIGNATURES = ("profile", "signature", "parts", "weights", "features", "least")


def today(states: Any) -> dict[str, Any]:
    """What makes the numbers of rows comparable today, as a record holds it (`SIGNATURES`): the profile
    (`RECONCILE_PROFILE`) and its signature of the vectors in use (`""` if it has not been built), the signature of
    each part the weights weigh above 0 that has been built (JSON), the weights (`settings.weights()`, JSON),
    `FEATURES`, and `RECONCILE_LEAST_SCORE` (`least`: which rows are displayed, and so the head of a list, depends on
    it). What the stored route keeps, and what a fit (`fits.py`) and step 11.6 take an example or a fit to be of today
    by: the same six values"""
    from pangloss_reconcile.score import SHARED

    name = settings.profile()
    weights = settings.weights()
    profile_state = states.profiles.get(name)
    return {
        "profile": name,
        "signature": profile_state.signature if profile_state is not None else "",
        "parts": json.dumps(
            {
                part: states.parts[part].signature
                for part in sorted(weights)
                if part != SHARED and part in states.parts
            },
            sort_keys=True,
        ),
        "weights": json.dumps(weights, sort_keys=True),
        "features": FEATURES,
        "least": settings.least_score(),
    }


def of_today(record: Mapping[str, Any], now: Mapping[str, Any]) -> bool:
    """Whether a record (an example, a fit) is of today (`today`): its six values those of `now`, and the profile
    built (a signature that is not empty)"""
    return bool(now["signature"]) and all(
        record.get(name) == now[name] for name in SIGNATURES
    )


def record_of(found: Any, answer: Mapping[str, Any], states: Any) -> dict[str, Any]:
    """The properties of a shown record of an unknown, but for its stand-in, user and time: the rows, and what makes
    their numbers comparable (`today`)"""
    rows = rows_of(found, displayed_in(answer, found.unknown.id))
    return {"rows": json.dumps(rows), **today(states)}


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


async def write_example(
    tx: Any,
    stand_in: str,
    at: datetime.datetime,
    record: Mapping[str, Any],
    taken: str | None,
) -> None:
    """(in a write transaction) The example of a stand-in, replacing an earlier one: the rows of `record` (JSON, as a
    shown record holds them) and its signatures (`SIGNATURES`), decided at `at`, `taken` the id of the row taken or
    None"""
    await (
        await tx.run(
            EXAMPLE_QUERY,
            stand_in=stand_in,
            at=at,
            rows=record["rows"],
            **{name: record[name] for name in SIGNATURES},
            taken=taken,
        )
    ).consume()


EXAMPLES_QUERY = f"""
MATCH (e:{EXAMPLE})
RETURN e.stand_in AS stand_in, e.at AS at, e.rows AS rows, e.profile AS profile, e.signature AS signature,
    e.parts AS parts, e.weights AS weights, e.features AS features, e.least AS least, e.taken AS taken
ORDER BY stand_in
"""


async def examples() -> list[dict[str, Any]]:
    """Every example kept, by stand-in: its properties, `at` a datetime (UTC), `rows` read from JSON"""
    from pangloss_cypher.values import native_datetime

    database = _database()

    @database.read_transaction
    async def read(tx: Any) -> list[dict[str, Any]]:
        result = await tx.run(EXAMPLES_QUERY)
        return [record.data() async for record in result]

    return [
        {
            **found,
            "at": _utc(native_datetime(found["at"])),
            "rows": json.loads(found["rows"] or "[]"),
        }
        for found in await read()
    ]


def _utc(value: Any) -> Any:
    if isinstance(value, datetime.datetime) and value.tzinfo is None:
        return value.replace(tzinfo=datetime.UTC)
    return value


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
            await write_example(
                tx,
                stand_in,
                resolution.at,
                record,
                entity if entity in ids else None,
            )
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


SWEEPABLE_QUERY = f"""
MATCH (s:{SHOWN})
OPTIONAL MATCH (n:PGIndexableNode {{id: s.stand_in}})
WITH s, n
WHERE s.at < $before OR n IS NULL OR n.head_node_id IS NULL
RETURN count(s) AS n
"""


async def sweepable() -> int:
    """How many shown records `sweep` would remove now, removing none (a read of the same query)"""
    before = datetime.datetime.now(datetime.UTC) - datetime.timedelta(
        minutes=settings.shown_for()
    )
    database = _database()

    @database.read_transaction
    async def count(tx: Any) -> int:
        record = await (await tx.run(SWEEPABLE_QUERY, before=before)).single()
        return int(record["n"]) if record else 0

    return await count()


def install() -> None:
    """(`pangloss_reconcile._install`)"""
    if heard not in hooks.resolved:
        hooks.resolved.append(heard)
