"""What `pangloss migrate` needs of a database backend.

A backend package (`DATABASE_MODULE`) supplies a `migration_backend` module with these:

- `async ensure_ready()`: what the backend needs to keep the record of migrations, and its
  structure as far as migrations do not make it (indexes and constraints; not enums);
- `async applied() -> {(app, name): record}`: the migrations that have been applied (or began);
- `async lock(who)` / `async unlock()`: so that only one `migrate` runs; `lock` raises
  `PanglossMigrationError` if another has the lock;
- `async dry_run(migrations, state) -> [MigrationReport]`: what each change would do, tried in a
  transaction that is rolled back (changes to the database's enums are not tried);
- `async apply(migrations, state, fake=False, progress=None) -> state`: apply migrations in
  order, recording each, starting from the snapshot `state`; returns the snapshot after them.

See `docs/migrations.md`.
"""

import datetime
import time
from collections.abc import Callable
from typing import Any

import neo4j
from pangloss_models.exceptions import PanglossMigrationError
from pangloss_models.migrations.files import Migration
from pangloss_models.migrations.reports import MigrationReport
from pangloss_models.migrations.state import apply_change as apply_to_snapshot
from pangloss_users import current_request_username

from pangloss_memgraph.databases.memgraph.database import Database
from pangloss_memgraph.databases.memgraph.initialise_database import (
    initialise_database,
    run_statement,
)
from pangloss_memgraph.databases.memgraph.migrations import (
    Progress,
    apply_changes,
    apply_changes_in_batches,
)
from pangloss_memgraph.databases.memgraph.migrations import dry_run as try_changes

LOCK_ID = "migrate"
CONSTRAINTS = [
    "CREATE CONSTRAINT ON (n:PGMigration) ASSERT n.app, n.name IS UNIQUE",
    "CREATE CONSTRAINT ON (n:PGMigrationLock) ASSERT n.id IS UNIQUE",
]


async def ensure_ready(database: Database | None = None) -> None:
    database = database or Database.default
    if not hasattr(database, "driver"):
        await database._initialise_driver()
    await initialise_database(database, enums=False)
    name = database.settings.DATABASE.DATABASE_NAME
    existing = await run_statement(database.driver, name, "SHOW CONSTRAINT INFO")
    have = {(row["label"], tuple(row["properties"])) for row in existing if row["constraint type"] == "unique"}
    if ("PGMigration", ("app", "name")) not in have:
        await run_statement(database.driver, name, CONSTRAINTS[0])
    if ("PGMigrationLock", ("id",)) not in have:
        await run_statement(database.driver, name, CONSTRAINTS[1])


def _session(database: Database) -> neo4j.AsyncSession:
    return database.driver.session(database=database.settings.DATABASE.DATABASE_NAME)


async def applied(database: Database | None = None) -> dict[tuple[str, str], dict[str, Any]]:
    database = database or Database.default
    if not hasattr(database, "driver"):
        await database._initialise_driver()
    async with _session(database) as session:
        result = await session.run("MATCH (m:PGMigration) RETURN properties(m) AS record")
        records = [row["record"] async for row in result]
    return {(r["app"], r["name"]): r for r in records}


async def lock(who: str | None = None, database: Database | None = None) -> None:
    database = database or Database.default
    if not hasattr(database, "driver"):
        await database._initialise_driver()
    async with _session(database) as session:
        try:
            result = await session.run(
                "CREATE (:PGMigrationLock {id: $id, acquired_when: $when, acquired_by: $who})",
                id=LOCK_ID,
                when=datetime.datetime.now(datetime.UTC),
                who=who or current_request_username.get(),
            )
            await result.consume()  # (a statement runs when its result is read)
        except neo4j.exceptions.ClientError as error:
            if "unique" in str(error).lower():
                raise PanglossMigrationError(
                    "Another migrate is running, or was stopped without finishing: "
                    "`pangloss migrate --unlock` removes the lock"
                ) from error
            raise


async def unlock(database: Database | None = None) -> None:
    database = database or Database.default
    if not hasattr(database, "driver"):
        await database._initialise_driver()
    async with _session(database) as session:
        result = await session.run("MATCH (l:PGMigrationLock {id: $id}) DELETE l", id=LOCK_ID)
        await result.consume()


async def record(
    database: Database,
    migration: Migration,
    status: str,
    fake: bool = False,
    duration: float | None = None,
    error: str | None = None,
) -> None:
    async with _session(database) as session:
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
# `migrate --batch-size` does not say
DEFAULT_BATCH_SIZE = 5000


async def stored_progress(database: Database, migration: Migration) -> Progress:
    """How far an earlier run of the migration got (nothing, if it was not stopped part way)"""
    async with _session(database) as session:
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
        parameters = {"app": migration.app, "name": migration.name, "cursor": progress.to_json()}
        if tx is not None:
            result = await tx.run(query, **parameters)
            await result.consume()
            return
        async with _session(database) as session:
            result = await session.run(query, **parameters)
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
    database = database or Database.default
    if not hasattr(database, "driver"):
        await database._initialise_driver()

    def say(migration: Migration, what: str) -> None:
        if progress:
            progress(migration, what)

    for migration in migrations:
        started = time.monotonic()
        if fake:
            for change in migration.changes:
                state = apply_to_snapshot(state, change)
            await record(database, migration, "applied", fake=True, duration=0.0)
            say(migration, "faked")
            continue

        size = batch_size or (None if migration.atomic else DEFAULT_BATCH_SIZE)
        start = await stored_progress(database, migration) if size else Progress()
        if start.change or start.after:
            say(migration, f"going on from change {start.change + 1}")
        else:
            say(migration, "applying")
        await record(database, migration, "running")
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
            await record(
                database,
                migration,
                "failed",
                duration=time.monotonic() - started,
                error=f"{type(error).__name__}: {error}"[:2000],
            )
            say(migration, "failed")
            raise
        await record(database, migration, "applied", duration=time.monotonic() - started)
        async with _session(database) as session:  # (nothing is left to go on from)
            result = await session.run(
                "MATCH (m:PGMigration {app: $app, name: $name}) SET m.cursor = null",
                app=migration.app,
                name=migration.name,
            )
            await result.consume()
        say(migration, "applied")
    return state


async def dry_run(
    migrations: list[Migration], state: dict[str, Any], database: Database | None = None
) -> list[MigrationReport]:
    """What each change of the migrations would do to the data, changing nothing. Each migration
    is tried after the ones before it have been (as the snapshot says, not as the data is: a change
    that depends on an earlier one's effect on the data is counted against the data as it is)."""
    database = database or Database.default
    reports: list[MigrationReport] = []
    for migration in migrations:
        change_reports, state = await try_changes(database, state, list(migration.changes))
        reports.append(MigrationReport(migration.app, migration.name, change_reports))
    return reports
