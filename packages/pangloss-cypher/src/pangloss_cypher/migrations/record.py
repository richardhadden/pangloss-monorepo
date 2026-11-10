"""The record of migrations in a Cypher database, and applying them: what a backend's `migration_backend` module is,
but for what is the database's own (the constraints of the record, the indexes, snapshots), which each backend has.

- `applied()`, `has_data()`: what the record says, and whether there is anything else in the database;
- `lock()` / `unlock()`: a `PGMigrationLock` node, which a uniqueness constraint lets only one `migrate` make;
- `apply()` / `unapply()`: the migrations in order, each recorded as `running`, then `applied` or `failed`;
- `dry_run()`: what each change would do to the data, changing nothing.

A backend names these in its own `migration_backend` (`from pangloss_cypher.migrations.record import ...`), where the
CLI and the API find them. What is logged goes to the backend's own logger (`pangloss.memgraph.migrations`), as it
did when each backend had a copy of this. See `docs/migrations.md`.
"""

import datetime
import logging
import time
from collections.abc import Callable
from typing import Any

import neo4j
from pangloss_models import PanglossMigrationError
from pangloss_models.migrations import Migration
from pangloss_models.migrations import apply_change as apply_to_snapshot
from pangloss_models.migrations.reports import MigrationReport
from pangloss_users import current_request_username

from pangloss_cypher.migrations.runner import (
    Progress,
    apply_changes,
    apply_changes_in_batches,
)
from pangloss_cypher.migrations.runner import dry_run as try_changes
from pangloss_cypher.transactions import Database, current

LOCK_ID = "migrate"


def logger_of(database: Database) -> logging.Logger:
    """The logger of the backend the database is of: `pangloss.<backend>.migrations`"""
    name = getattr(getattr(database, "dialect", None), "name", "cypher")
    return logging.getLogger(f"pangloss.{name}.migrations")


def open_session(database: Database) -> neo4j.AsyncSession:
    """(once the driver is made: `ensure_driver`)"""
    assert database.driver is not None
    return database.driver.session(database=database.settings.DATABASE.DATABASE_NAME)


async def has_data(database: Database | None = None) -> bool:
    """Whether the database holds anything besides the record of migrations (so that `migrate` can
    say that a database made before migrations needs `--fake`)"""
    database = database or current()
    await database.ensure_driver()
    async with open_session(database) as session:
        result = await session.run(
            "MATCH (n) WHERE NOT n:PGMigration AND NOT n:PGMigrationLock RETURN n LIMIT 1"
        )
        return await result.single() is not None


async def applied(
    database: Database | None = None,
) -> dict[tuple[str, str], dict[str, Any]]:
    database = database or current()
    await database.ensure_driver()
    async with open_session(database) as session:
        result = await session.run(
            "MATCH (m:PGMigration) RETURN properties(m) AS record"
        )
        records = [row["record"] async for row in result]
    return {(r["app"], r["name"]): r for r in records}


async def lock(who: str | None = None, database: Database | None = None) -> None:
    database = database or current()
    await database.ensure_driver()
    async with open_session(database) as session:
        try:
            result = await session.run(
                "CREATE (:PGMigrationLock {id: $id, acquired_when: $when, acquired_by: $who})",
                id=LOCK_ID,
                when=datetime.datetime.now(datetime.UTC),
                who=who or current_request_username.get(),
            )
            await result.consume()  # (a statement runs when its result is read)
            logger_of(database).info(
                "Migration lock taken by %r", who or current_request_username.get()
            )
        except neo4j.exceptions.ClientError as error:
            if "unique" in str(error).lower():
                logger_of(database).error(
                    "Migration lock is held by another migrate (or a stopped one)"
                )
                raise PanglossMigrationError(
                    "Another migrate is running, or was stopped without finishing: "
                    "`pangloss migrate --unlock` removes the lock"
                ) from error
            raise


async def unlock(database: Database | None = None) -> None:
    database = database or current()
    await database.ensure_driver()
    async with open_session(database) as session:
        result = await session.run(
            "MATCH (l:PGMigrationLock {id: $id}) DELETE l", id=LOCK_ID
        )
        await result.consume()
        logger_of(database).info("Migration lock released")


async def record(
    database: Database,
    migration: Migration,
    status: str,
    fake: bool = False,
    duration: float | None = None,
    error: str | None = None,
) -> None:
    async with open_session(database) as session:
        result = await session.run(
            """
            MERGE (m:PGMigration {app: $app, name: $name})
            SET m.status = $status, m.checksum = $checksum, m.schema_hash = $schema_hash,
                m.applied_when = $when, m.applied_by = $who, m.fake = $fake,
                m.duration = $duration, m.error = $error
            """,
            app=migration.app,
            name=migration.name,
            status=status,
            checksum=migration.checksum,
            schema_hash=migration.schema_hash,
            when=datetime.datetime.now(datetime.UTC),
            who=current_request_username.get(),
            fake=fake,
            duration=duration,
            error=error,
        )
        await result.consume()


# How many nodes a batch is, for a migration that is made in batches (`atomic = False`) when
# `migrate --batch-size` and the migration's `batch_size` do not say
DEFAULT_BATCH_SIZE = 5000


async def stored_progress(database: Database, migration: Migration) -> Progress:
    """How far an earlier run of the migration got (nothing, if it was not stopped part way)"""
    async with open_session(database) as session:
        result = await session.run(
            "MATCH (m:PGMigration {app: $app, name: $name}) RETURN m.status AS status, m.cursor AS cursor",
            app=migration.app,
            name=migration.name,
        )
        row = await result.single()
    if row is None or row["status"] == "applied":
        return Progress()
    return Progress.from_json(row["cursor"])


def progress_saver(database: Database, migration: Migration):
    async def save(tx, progress: Progress) -> None:
        query = "MATCH (m:PGMigration {app: $app, name: $name}) SET m.cursor = $cursor"
        parameters = {
            "app": migration.app,
            "name": migration.name,
            "cursor": progress.to_json(),
        }
        if tx is not None:
            result = await tx.run(query, **parameters)
            await result.consume()
            return
        async with open_session(database) as session:
            result = await session.run(query, **parameters)  # ty: ignore[invalid-argument-type]
            await result.consume()

    return save


async def apply(
    migrations: list[Migration],
    state: dict[str, Any],
    fake: bool = False,
    progress: Callable[[Migration, str], None] | None = None,
    database: Database | None = None,
    batch_size: int | None = None,
) -> dict[str, Any]:
    """Apply migrations in order, starting from the snapshot `state`; each is recorded as
    running, then applied (or failed, with the error). A failed one stops the rest.

    A migration is made in one transaction (all or nothing) unless `batch_size` is given, or it is
    `atomic = False`: then it is made in batches of that many nodes (`DEFAULT_BATCH_SIZE`), each its
    own transaction, with how far it has got kept in the record. One that stopped part way goes on
    from there the next time."""
    database = database or current()
    await database.ensure_driver()

    def say(migration: Migration, what: str) -> None:
        if progress:
            progress(migration, what)

    logger_of(database).info(
        "Migrate: %s to apply%s",
        len(migrations),
        " (fake: recorded only)" if fake else "",
    )
    for migration in migrations:
        started = time.monotonic()
        if fake:
            for change in migration.changes:
                state = apply_to_snapshot(state, change)
            await record(database, migration, "applied", fake=True, duration=0.0)
            say(migration, "faked")
            continue

        size = (
            batch_size
            or migration.batch_size
            or (None if migration.atomic else DEFAULT_BATCH_SIZE)
        )
        start = await stored_progress(database, migration) if size else Progress()
        if start.change or start.after:
            say(migration, f"going on from change {start.change + 1}")
        else:
            say(migration, "applying")
        await record(database, migration, "running")
        logger_of(database).info(
            "Applying %s.%s (%s changes, %s)",
            migration.app,
            migration.name,
            len(migration.changes),
            f"batches of {size}" if size else "one transaction",
        )
        try:
            if size:
                state = await apply_changes_in_batches(
                    database,
                    state,
                    list(migration.changes),
                    size,
                    start=start,
                    save=progress_saver(database, migration),
                )
            else:
                state = await apply_changes(database, state, list(migration.changes))
        except Exception as error:
            logger_of(database).error(
                "Migration %s.%s failed after %.1f s: %s: %s",
                migration.app,
                migration.name,
                time.monotonic() - started,
                type(error).__name__,
                error,
            )
            await record(
                database,
                migration,
                "failed",
                duration=time.monotonic() - started,
                error=f"{type(error).__name__}: {error}"[:2000],
            )
            say(migration, "failed")
            raise
        await record(
            database, migration, "applied", duration=time.monotonic() - started
        )
        logger_of(database).info(
            "Applied %s.%s in %.1f s",
            migration.app,
            migration.name,
            time.monotonic() - started,
        )
        async with open_session(database) as session:  # (nothing is left to go on from)
            result = await session.run(
                "MATCH (m:PGMigration {app: $app, name: $name}) SET m.cursor = null",
                app=migration.app,
                name=migration.name,
            )
            await result.consume()
        say(migration, "applied")
    return state


async def unapply(
    migrations: list[Migration],
    state: dict[str, Any],
    fake: bool = False,
    progress: Callable[[Migration, str], None] | None = None,
    database: Database | None = None,
    batch_size: int | None = None,
) -> dict[str, Any]:
    """Undo migrations, last first: `migration.changes` are the changes that undo each (see
    `pangloss_models.migrations.reverse`), `state` the snapshot after them all. The record of a
    migration is removed when it has been undone, so it is to be applied again; one that fails
    stops the rest, and is still recorded as it was (nothing of it was changed, as it is made in
    one transaction, except the indexes and constraints that cannot be).

    In batches (`batch_size`, or the migration's `batch_size` or `atomic = False`) it is not one
    transaction: one that stops part way has undone part, and is run again from the start, which is
    harmless as what is undone is not there to undo again."""
    database = database or current()
    await database.ensure_driver()
    for migration in migrations:
        logger_of(database).info(
            "Undoing %s.%s%s", migration.app, migration.name, " (fake)" if fake else ""
        )
        if progress:
            progress(migration, "faked" if fake else "undoing")
        if fake:
            for change in migration.changes:
                state = apply_to_snapshot(state, change)
        else:
            size = (
                batch_size
                or migration.batch_size
                or (None if migration.atomic else DEFAULT_BATCH_SIZE)
            )
            if size:
                state = await apply_changes_in_batches(
                    database, state, list(migration.changes), size
                )
            else:
                state = await apply_changes(database, state, list(migration.changes))
        async with open_session(database) as session:
            result = await session.run(
                "UNWIND $keys AS key MATCH (m:PGMigration {app: key[0], name: key[1]}) DELETE m",
                keys=[list(migration.key), *(list(r) for r in migration.replaces)],
            )
            await result.consume()
        logger_of(database).info("Undone %s.%s", migration.app, migration.name)
        if progress:
            progress(migration, "undone")
    return state


async def dry_run(
    migrations: list[Migration], state: dict[str, Any], database: Database | None = None
) -> list[MigrationReport]:
    """What each change of the migrations would do to the data, changing nothing. Each migration
    is tried after the ones before it have been (as the snapshot says, not as the data is: a change
    that depends on an earlier one's effect on the data is counted against the data as it is)."""
    database = database or current()
    reports: list[MigrationReport] = []
    for migration in migrations:
        change_reports, state = await try_changes(
            database, state, list(migration.changes)
        )
        reports.append(MigrationReport(migration.app, migration.name, change_reports))
    return reports
