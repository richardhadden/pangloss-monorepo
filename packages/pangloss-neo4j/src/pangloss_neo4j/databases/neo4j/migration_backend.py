"""What `pangloss migrate` needs of a database backend.

A backend (its `Storage`, named by `STORAGE`) has a `migration_backend` module with these:

- `structure() -> {"indexes": [...], "constraints": [...]}`: the structure the database needs besides
  the models, for the snapshot: the migrations make it (`AddIndex`, `AddConstraint`...);
- `async ensure_ready()`: what the backend needs to keep the record of migrations;
- `async applied() -> {(app, name): record}`: the migrations that have been applied (or began);
- `async backups()`, `async backup_notice()`, `async restore(path)`, `async backup()` (optional, and left out here:
  Neo4j Community has no online snapshot, so `pangloss migrate --backup` says that this database cannot take one; the way
  to make a backup of Neo4j is `neo4j-admin database dump`, with the database stopped);
- `async has_data() -> bool` (optional): whether the database holds anything but the record;
- `async lock(who)` / `async unlock()`: so that only one `migrate` runs; `lock` raises
  `PanglossMigrationError` if another has the lock;
- `async unapply(migrations, state, fake=False, progress=None) -> state`: undo migrations whose
  `changes` are the changes that undo them (the last applied first), starting from the snapshot
  after them; the record of each (and of those it `replaces`) is removed. Always in one transaction a migration (so one that
  fails has changed nothing);
- `async dry_run(migrations, state) -> [MigrationReport]`: what each change would do, tried in a
  transaction that is rolled back (changes to the database's indexes and constraints are not tried);
- `async apply(migrations, state, fake=False, progress=None) -> state`: apply migrations in
  order, recording each, starting from the snapshot `state`; returns the snapshot after them.

What is the same for every Cypher database (the record itself, the lock, applying and undoing) is
`pangloss_cypher.migrations.record`, named here; what is Neo4j's own is written here.

See `implementation_docs/migrations.md`.
"""

from typing import Any

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

from pangloss_neo4j.databases.neo4j.database import current
from pangloss_neo4j.databases.neo4j.initialise_database import (
    structure as initialise_structure,
)
from pangloss_neo4j.databases.neo4j.schema import (
    create_constraint_statement,
    has_constraint,
    list_constraints,
    run_statement,
)

CONSTRAINTS = [
    {"kind": "unique", "label": "PGMigration", "properties": ["app", "name"]},
    {"kind": "unique", "label": "PGMigrationLock", "properties": ["id"]},
]


def structure() -> dict[str, Any]:
    """The indexes and constraints the database needs, for the snapshot (see
    `initialise_database.structure`): migrations make them"""
    return initialise_structure()


async def ensure_ready(database: Database | None = None) -> None:
    database = database or current()
    driver = await database.ensure_driver()
    name = database.settings.DATABASE.DATABASE_NAME
    existing = await list_constraints(driver, name)
    for entry in CONSTRAINTS:
        if has_constraint(existing, entry) is None:
            await run_statement(driver, name, create_constraint_statement(entry))
