"""What a migration does to stored criteria (implementation_docs/matches-criteria.md, "Migrations that make a pattern
invalid").

A description's criteria name classes, fields, enum values and wrappers, so a change of the models can make them
wrong. Two things are done, in two places, because a migration is not always one transaction (a change of an index is
made between transactions; a migration in batches is many):

- **In each change of the data** (`hooks.migration_changes`, `in_migration`), in that change's transaction: every
  stored pattern is brought through the change (`pangloss_models.migrations.patterns`: a renamed field is renamed in
  it). One the change makes wrong is **broken** (`broken`, and `broken_since`: the migration), and keeps its
  candidates; its condition is left in place. Undoing the migration that broke it clears it (the condition is right
  again). A migration is not an edit: no `PGUpdate`, no version, no history.
- **After `pangloss migrate`** (`hooks.after_migrate`, `after_migrate`), if the database is then where the models of
  the code are: every description's criteria are checked as the worker checks them, what is worked out of them is
  worked out again (a renamed class changes `depends_on`), a broken one that passes now is cleared, and the documents
  of those that changed, or whose criteria touch a class the migrations could have altered, are marked for the worker.

The criteria of a shared description (`Description`) are walked in each change as a mention's are. It has no
`broken` of its own: when a change breaks its criteria, every mention that cites it is broken. After the migrations,
a mention is checked by its effective criteria (the shared ones and its own: `effective`).

A migration written by hand (`RunPython`) can rewrite the criteria itself with `rewrite`.
"""

import inspect
import logging
from collections.abc import Callable
from typing import Any

from pangloss_core import Transaction, backend
from pangloss_cypher import computed, pending
from pangloss_models import ModelRegistry, PanglossSearchError, hooks
from pangloss_models.migrations import patterns

from pangloss_models.citations import CITATION

from pangloss_criteria import effective
from pangloss_criteria.effective import FIELD, cited_id, shared_of, stored
from pangloss_criteria.evaluate import check_criteria
from pangloss_criteria.holders import KIND
from pangloss_criteria.models import DESCRIPTION, NAME, WORKED_OUT, worked_out
from pangloss_criteria.pattern import SearchPattern

logger = logging.getLogger("pangloss.criteria.migrating")

CHUNK = 500
"""Descriptions written in one statement"""

# Every description with criteria of its own (a place of a mark with none is not walked: it has nothing to walk)
READ_QUERY = f"""
    MATCH (d:{NAME})
    WHERE d.criteria IS NOT NULL
    RETURN d.id AS id, d.criteria AS criteria, d.broken AS broken, d.broken_since AS broken_since
    ORDER BY id
"""

WRITE_QUERY = f"""
    UNWIND $rows AS row
    MATCH (d:PGIndexableNode {{id: row.id}})
    WHERE d:{NAME}
    SET d.criteria = row.criteria, d.broken = row.broken, d.broken_since = row.broken_since
"""

# Every shared description: its criteria are a stored pattern too, walked as a mention's are
SHARED_READ_QUERY = f"""
    MATCH (s:{DESCRIPTION})
    WHERE s.criteria IS NOT NULL
    RETURN s.id AS id, s.criteria AS criteria
    ORDER BY id
"""

SHARED_WRITE_QUERY = f"""
    UNWIND $rows AS row
    MATCH (s:PGIndexableNode {{id: row.id}})
    WHERE s:{DESCRIPTION}
    SET s.criteria = row.criteria
"""

# (a shared description has no `broken` of its own: the mentions that cite it are broken, by what broke it. One
# broken already keeps its first reason)
BREAK_CITERS_QUERY = f"""
    UNWIND $rows AS row
    MATCH (citation:{CITATION} {{target_id: row.id}})<-[edge:{FIELD}]-(d:{NAME})
    WHERE NOT coalesce(edge.reverse, false) AND d.broken IS NULL
    SET d.broken = row.broken, d.broken_since = row.broken_since
"""

# (undoing the migration that broke them: what broke them is undone, and the condition was left in place)
CLEAR_QUERY = f"""
    MATCH (d:{NAME})
    WHERE d.broken_since = $migration
    SET d.broken = null, d.broken_since = null
"""


async def _read(tx: Any) -> list[dict[str, Any]]:
    return [dict(row) async for row in await tx.run(READ_QUERY)]


async def _write(tx: Any, rows: list[dict[str, Any]]) -> None:
    for start in range(0, len(rows), CHUNK):
        await (await tx.run(WRITE_QUERY, rows=rows[start : start + CHUNK])).consume()


def since_of(step: hooks.MigrationStep) -> str | None:
    """What a description broken by this change says it is broken since: the migration; of a migration being
    undone, said so (so that it is not taken for one that undoing the migration clears)"""
    if step.migration is None:
        return None
    return f"{step.migration} (undone)" if step.undoing else step.migration


async def in_migration(tx: Transaction, step: hooks.MigrationStep) -> None:
    """(`hooks.migration_changes`) every stored pattern brought through a change, in its transaction. It may be run
    twice for one change: a pattern brought through a change already is left as it is by it"""
    if step.undoing and step.migration is not None:
        await (await tx.run(CLEAR_QUERY, migration=step.migration)).consume()
    if not patterns.may_alter(step.change):
        return
    rows: list[dict[str, Any]] = []
    for row in await _read(tx):
        try:
            data = SearchPattern(row["criteria"]).data
        except ValueError:
            # (not a pattern that can be read: the check after the migration says so)
            continue
        result = patterns.upgrade(data, step.change, step.before, step.after)
        broken, since = row["broken"], row["broken_since"]
        if result.broken is not None and broken is None:
            broken, since = str(result.broken), since_of(step)
        if not result.changed and broken == row["broken"]:
            continue
        rows.append(
            {
                "id": row["id"],
                "criteria": SearchPattern(result.pattern).text()
                if result.changed
                else row["criteria"],
                "broken": broken,
                "broken_since": since,
            }
        )
    await _write(tx, rows)
    shared = await _walk_shared(tx, step)
    if rows or shared:
        logger.info(
            "Criteria: %s of %s rewritten by %s",
            len(rows) + shared,
            step.migration or "a change",
            step.change.describe(),
        )


async def _walk_shared(tx: Transaction, step: hooks.MigrationStep) -> int:
    """(`in_migration`) the criteria of every shared description brought through the change; the mentions that cite
    one the change breaks are broken, since the migration. Gives how many were written"""
    rewritten: list[dict[str, Any]] = []
    broken: list[dict[str, Any]] = []
    async for row in await tx.run(SHARED_READ_QUERY):
        try:
            data = SearchPattern(row["criteria"]).data
        except ValueError:
            continue
        result = patterns.upgrade(data, step.change, step.before, step.after)
        if result.changed:
            rewritten.append(
                {"id": row["id"], "criteria": SearchPattern(result.pattern).text()}
            )
        if result.broken is not None:
            broken.append(
                {
                    "id": row["id"],
                    "broken": str(result.broken),
                    "broken_since": since_of(step),
                }
            )
    for start in range(0, len(rewritten), CHUNK):
        await (
            await tx.run(SHARED_WRITE_QUERY, rows=rewritten[start : start + CHUNK])
        ).consume()
    for start in range(0, len(broken), CHUNK):
        await (
            await tx.run(BREAK_CITERS_QUERY, rows=broken[start : start + CHUNK])
        ).consume()
    return len(rewritten)


type Rewriting = Callable[[SearchPattern], SearchPattern | Any | None]


async def rewrite(tx: Transaction, function: Rewriting) -> int:
    """For a migration written by hand (`RunPython`), in its transaction: `function` is given every stored pattern
    (a `SearchPattern`), and gives the pattern it is to be (a `SearchPattern`, or anything one is made from), or None
    to leave it. It may be `async`. Gives how many were rewritten. Whether the criteria fit the models is checked
    after the migrations (`after_migrate`)

        async def secretaries(tx, state):
            await pangloss_criteria.rewrite(tx, lambda pattern: ...)

        changes = [RunPython(function=secretaries)]"""
    rows: list[dict[str, Any]] = []
    shared: list[dict[str, Any]] = []
    # (the criteria of mentions, and of shared descriptions)
    every = [(row, rows) for row in await _read(tx)] + [
        (dict(row), shared) async for row in await tx.run(SHARED_READ_QUERY)
    ]
    for row, into in every:
        try:
            pattern = SearchPattern(row["criteria"])
        except ValueError:
            continue
        made = function(pattern)
        if inspect.isawaitable(made):
            made = await made
        if made is None:
            continue
        text = SearchPattern(made).text()
        if text != row["criteria"]:
            into.append({**row, "criteria": text})
    await _write(tx, rows)
    for start in range(0, len(shared), CHUNK):
        await (
            await tx.run(SHARED_WRITE_QUERY, rows=shared[start : start + CHUNK])
        ).consume()
    return len(rows) + len(shared)


# --- after the migrations ---------------------------------------------------------------------------------------------

AFTER_READ_QUERY = f"""
    MATCH (d:{NAME})
    WITH d, {cited_id("d")} AS cites
    WHERE d.criteria IS NOT NULL OR cites IS NOT NULL
    RETURN d.id AS id, d.head_node_id AS head, d.head_node_type AS head_type, d.criteria AS criteria,
           cites, d.stands_for AS stands_for, d.broken AS broken, d.broken_since AS broken_since,
           {", ".join(f"d.{name} AS {name}" for name in WORKED_OUT)}
    ORDER BY id
"""

SET_QUERY = """
    UNWIND $rows AS row
    MATCH (d:PGIndexableNode {id: row.id})
    SET d += row.values
"""


def database() -> Any:
    return backend.current().database()


async def after_migrate(migrated: hooks.Migrated) -> None:
    """(`hooks.after_migrate`) once the database is where the models of the code are: every description's criteria
    checked with the worker's check, what is worked out of them worked out again, and the documents of those that
    changed, or whose criteria touch a class the migrations could have altered, left for the worker"""
    if not migrated.complete:
        logger.info(
            "Criteria: the database is not where the models of the code are (%s), so the criteria are not checked "
            "against them: they are checked after the `pangloss migrate` that brings it there",
            "migrations undone" if migrated.undone else "migrations still to apply",
        )
        return
    since = migrated.migrations[-1] if migrated.migrations else None
    affected = set(migrated.affected)
    db = database()

    @db.read_transaction
    async def read(tx: Transaction) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        rows = [dict(row) async for row in await tx.run(AFTER_READ_QUERY)]
        return rows, await shared_of(tx, {row["cites"] for row in rows})

    updates: list[dict[str, Any]] = []
    renewed: dict[str, list[str]] = {}
    heads: dict[str, str] = {}
    rows, shared = await read()
    for row in rows:
        found: dict[str, Any] | None = None
        error: str | None = None
        try:
            # (its effective criteria: with those of the shared description it cites)
            pattern = effective.effective(
                row["criteria"], row["cites"], shared, row["stands_for"] or ()
            )
            assert pattern is not None
            check_criteria(pattern)
            found = worked_out(pattern)
        except (PanglossSearchError, ValueError) as reason:
            error = str(reason)
        values: dict[str, Any] = {}
        if found is not None:
            values = {
                name: value
                for name, value in found.items()
                if stored(row[name]) != stored(value)
            }
            if values:
                # (what the description says is another now: what the next update keeps of it has to know)
                renewed.setdefault(row["head"], []).append(row["id"])
            if row["broken"] is not None:
                values |= {"broken": None, "broken_since": None}
        elif row["broken"] is None:
            values = {"broken": error, "broken_since": since}
        touched = set(row["depends_on"] or []) | set(
            (found or {}).get("depends_on", [])
        )
        if values or touched & affected:
            heads[row["head"]] = row["head_type"]
        if values:
            updates.append({"id": row["id"], "values": values})

    for start in range(0, len(updates), CHUNK):

        @db.write_transaction
        async def write(tx: Transaction, some=updates[start : start + CHUNK]) -> None:
            await (await tx.run(SET_QUERY, rows=some)).consume()

        await write()
    await _renew_bases(renewed, heads)
    marked = sorted(heads)
    for start in range(0, len(marked), CHUNK):

        @db.write_transaction
        async def mark(tx: Transaction, some=marked[start : start + CHUNK]) -> None:
            await pending.mark(tx, KIND, some)

        await mark()
    for model in {ModelRegistry.all_models().get(name) for name in heads.values()}:
        if model is not None:
            hooks.emit_work_marked(model)
    logger.info(
        "Criteria after %s: %s descriptions changed, %s documents left for the worker",
        ", ".join(migrated.migrations) or "the migrations",
        len(updates),
        len(heads),
    )


async def _renew_bases(renewed: dict[str, list[str]], heads: dict[str, str]) -> None:
    """The basis of each description whose criteria (or what is worked out of them) a migration changed, written
    again from its document as it is (`computed.renew_bases`), so that an update that changes nothing keeps its
    candidates. A document that cannot be read as its class now is left: its next update starts it empty"""
    models = ModelRegistry.all_models()
    for head_id, ids in renewed.items():
        model = models.get(heads.get(head_id) or "")
        if model is None:
            continue
        try:
            read = (
                model.get_for_edit  # ty: ignore[unresolved-attribute]
                if getattr(model, "__metatype__", None) == "Entity"
                else model.get  # ty: ignore[unresolved-attribute]
            )
            view = await read(head_id)
            db_instance = model.Update.model_validate(  # ty: ignore[unresolved-attribute]
                view.model_dump()
            )._to_db_model()
            # (what a save works out of the criteria of a mention that cites a shared description, as it would)
            await effective.fill_all(db_instance)
        except Exception:
            logger.debug(
                "Criteria: %s %s could not be read as an update of it",
                model.__name__,
                head_id,
                exc_info=True,
            )
            continue

        @database().write_transaction
        async def write(tx: Any, made=db_instance, ids=ids) -> None:
            await computed.renew_bases(tx, made, ids)

        await write()


__all__ = ["after_migrate", "in_migration", "rewrite", "since_of"]
