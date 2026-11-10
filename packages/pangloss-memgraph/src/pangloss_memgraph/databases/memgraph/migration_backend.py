"""What `pangloss migrate` needs of a database backend.

A backend (its `Storage`, named by `STORAGE`) has a `migration_backend` module with these:

- `structure() -> {"indexes": [...], "constraints": [...]}`: the structure the database needs besides
  the models, for the snapshot: the migrations make it (`AddIndex`, `AddConstraint`...);
- `async ensure_ready()`: what the backend needs to keep the record of migrations;
- `async applied() -> {(app, name): record}`: the migrations that have been applied (or began);
- `async backups() -> [dict]`, `async backup_notice() -> str | None`, `async restore(path)` (optional): the
  snapshots there are, how long a new one lasts, and putting the database back to one;
- `async has_data() -> bool` (optional): whether the database holds anything but the record;
- `async lock(who)` / `async unlock()`: so that only one `migrate` runs; `lock` raises
  `PanglossMigrationError` if another has the lock;
- `async backup() -> str`: a snapshot of the whole database, kept by the database (Memgraph's own
  snapshot, on the server); returns where it is;
- `async unapply(migrations, state, fake=False, progress=None) -> state`: undo migrations whose
  `changes` are the changes that undo them (the last applied first), starting from the snapshot
  after them; the record of each (and of those it `replaces`) is removed. Always in one transaction a migration (so one that
  fails has changed nothing);
- `async dry_run(migrations, state) -> [MigrationReport]`: what each change would do, tried in a
  transaction that is rolled back (changes to the database's indexes and constraints are not tried);
- `async apply(migrations, state, fake=False, progress=None) -> state`: apply migrations in
  order, recording each, starting from the snapshot `state`; returns the snapshot after them.

What is the same for every Cypher database (the record itself, the lock, applying and undoing) is
`pangloss_cypher.migrations.record`, named here; what is Memgraph's own is written here.

See `docs/migrations.md`.
"""

import logging
import re
from typing import Any

import neo4j
from pangloss_cypher import Database
from pangloss_cypher.migrations.record import (
    LOCK_ID as LOCK_ID,
    applied as applied,
    apply as apply,
    dry_run as dry_run,
    has_data as has_data,
    lock as lock,
    open_session as open_session,
    progress_saver as progress_saver,
    record as record,
    stored_progress as stored_progress,
    unapply as unapply,
    unlock as unlock,
)
from pangloss_models import PanglossMigrationError

from pangloss_memgraph.databases.memgraph.database import current
from pangloss_memgraph.databases.memgraph.initialise_database import run_statement
from pangloss_memgraph.databases.memgraph.initialise_database import (
    structure as initialise_structure,
)

logger = logging.getLogger("pangloss.memgraph.migrations")

CONSTRAINTS = [
    "CREATE CONSTRAINT ON (n:PGMigration) ASSERT n.app, n.name IS UNIQUE",
    "CREATE CONSTRAINT ON (n:PGMigrationLock) ASSERT n.id IS UNIQUE",
]


def structure() -> dict[str, Any]:
    """The indexes and constraints the database needs, for the snapshot (see
    `initialise_database.structure`): migrations make them"""
    return initialise_structure()


async def ensure_ready(database: Database | None = None) -> None:
    database = database or current()
    driver = await database.ensure_driver()
    name = database.settings.DATABASE.DATABASE_NAME
    existing = await run_statement(driver, name, "SHOW CONSTRAINT INFO")
    have = {
        (row["label"], tuple(row["properties"]))
        for row in existing
        if row["constraint type"] == "unique"
    }
    if ("PGMigration", ("app", "name")) not in have:
        await run_statement(driver, name, CONSTRAINTS[0])
    if ("PGMigrationLock", ("id",)) not in have:
        await run_statement(driver, name, CONSTRAINTS[1])


async def backup(database: Database | None = None) -> str:
    """Take a snapshot of the database (`CREATE SNAPSHOT`), and say where it is kept.

    The snapshot is of the whole of Memgraph and is written on the server, not here. Memgraph
    keeps only the newest few (`--storage-snapshot-retention-count`, 3 by default), so a later
    snapshot can remove it; copy it away if it has to be kept."""
    database = database or current()
    await database.ensure_driver()
    async with open_session(
        database
    ) as session:  # (an auto-commit session: not in a transaction)
        try:
            result = await session.run("CREATE SNAPSHOT")
            rows = await result.data()
        except neo4j.exceptions.Neo4jError as error:
            raise PanglossMigrationError(
                f"Cannot take a snapshot: {error.message}"
            ) from error
    where = str(rows[0]["path"]) if rows else "(the snapshot directory of the server)"
    logger.info("Snapshot taken: %s", where)
    return where


async def backups(database: Database | None = None) -> list[dict[str, Any]]:
    """The snapshots the server has (`SHOW SNAPSHOTS`): `path`, `creation_time` and `size`, newest first"""
    database = database or current()
    await database.ensure_driver()
    async with open_session(database) as session:
        result = await session.run("SHOW SNAPSHOTS")
        rows = await result.data()
    return sorted(rows, key=lambda row: row["creation_time"], reverse=True)


async def backup_notice(database: Database | None = None) -> str | None:
    """How long a snapshot lasts, if the server makes its own and keeps only a few: each new one
    pushes the oldest out, so a backup is gone after that many have been made after it"""
    database = database or current()
    await database.ensure_driver()
    async with open_session(database) as session:
        result = await session.run("SHOW CONFIG")
        config = {row["name"]: row["current_value"] for row in await result.data()}
    try:
        keep = int(config["storage_snapshot_retention_count"])
        every = int(config.get("storage_snapshot_interval_sec") or 0)
    except KeyError, ValueError:
        return None
    if not every:
        return f"Memgraph keeps the newest {keep} snapshots: this one is removed after {keep} more are made"
    minutes = max(1, keep * every // 60)
    return (
        f"Memgraph makes a snapshot every {every} s and keeps {keep}: this one is removed in about "
        f"{minutes} minutes. Raise `--storage-snapshot-retention-count`, or copy it from the server"
    )


async def restore(path: str, database: Database | None = None) -> None:
    """Put the database back to a snapshot (`RECOVER SNAPSHOT ... FORCE`): everything in it is
    replaced by what the snapshot has, the record of migrations with it. Only a snapshot the server
    lists can be used."""
    database = database or current()
    known = {row["path"] for row in await backups(database)}
    if path not in known:
        raise PanglossMigrationError(
            f"{path} is not a snapshot the server has (`pangloss backups` lists them)"
        )
    async with open_session(database) as session:
        try:
            result = await session.run(f'RECOVER SNAPSHOT "{path}" FORCE')  # ty: ignore[invalid-argument-type]
            await result.consume()
        except neo4j.exceptions.Neo4jError as error:
            raise PanglossMigrationError(
                f"Cannot restore {path}: {error.message}"
            ) from error
    await rebuild_text_indexes(database)


async def rebuild_text_indexes(database: Database) -> None:
    """Make the text indexes again. A recovered snapshot has them, but their files (which are kept
    beside the snapshot, not in it) are not there, so every write of a node they cover would fail."""
    driver = await database.ensure_driver()
    name = database.settings.DATABASE.DATABASE_NAME
    rows = await run_statement(driver, name, "SHOW INDEX INFO")
    for row in rows:
        match = re.match(r"label_text \(name: (\w+)\)", row["index type"])
        if not match:
            continue
        index, label, prop = match.group(1), row["label"], row["property"][0]
        await run_statement(driver, name, f"DROP TEXT INDEX {index}")
        await run_statement(
            driver, name, f"CREATE TEXT INDEX {index} ON :{label}({prop})"
        )
