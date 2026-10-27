"""Loading a lot of data into an empty database, fast: Memgraph's analytical storage mode.

```python
async with bulk_ingest():
    ...  # write with the models, as usual (`await Person.Create(...).save()`)
```

In analytical mode Memgraph keeps no versions of what is written, so writers never conflict and a
write is several times as fast (2.8 times for a load of 100,000 entities and 30,000 factoids, and
many writers at once no longer slow it down). The price is that nothing is a transaction: a write
that fails part way is not rolled back, another connection sees writes before they are done, and
Memgraph writes nothing to disk. Memgraph also refuses the mode while unique constraints exist.
So `bulk_ingest`:

1. refuses unless the database is **empty** (it may hold the record of migrations and users);
2. takes the migration lock, so `migrate` and the API (anything but this process) cannot write;
3. drops the unique constraints, keeping their definitions on the lock;
4. switches to `IN_MEMORY_ANALYTICAL`;
5. lets the body write;
6. whatever happened in the body: switches back to `IN_MEMORY_TRANSACTIONAL`, makes the constraints
   again (which fails if the load wrote a duplicate id or URL), makes the text index again, and
   releases the lock.

If the constraints cannot be made (duplicates), the lock is **kept** and `PanglossBulkLoadError` says
which: fix the data, then `recover()` (`pangloss memgraph bulk-recover`) finishes the job. It is also
what to run after a load that was killed: the lock holds what is needed to put everything back.

See `docs/large-data.md`.
"""

import json
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import neo4j
from pangloss_models.exceptions import PanglossBulkLoadError

from pangloss_memgraph.databases.memgraph.database import Database
from pangloss_memgraph.databases.memgraph.migration_backend import (
    LOCK_ID,
    _session,
    lock,
    rebuild_text_indexes,
    unlock,
)

logger = logging.getLogger("pangloss.memgraph.bulk")

TRANSACTIONAL = "IN_MEMORY_TRANSACTIONAL"
ANALYTICAL = "IN_MEMORY_ANALYTICAL"

# What an empty database may hold: the record of migrations, and the users (and their tokens), without
# whom nothing can be written
ALLOWED_LABELS = [
    "PGMigration",
    "PGMigrationLock",
    "PGUser",
    "PGAccessToken",
    "PGRevokedSession",
]


async def prepared(database: Database) -> None:
    if not hasattr(database, "driver"):
        await database._initialise_driver()


async def statements(database: Database, statement: str) -> list[dict[str, Any]]:
    """A statement run on its own (not in a transaction: Memgraph does not allow the ones here in
    one)"""
    async with _session(database) as session:
        result = await session.run(statement)  # ty: ignore[invalid-argument-type]
        return await result.data()


async def storage_mode(database: Database | None = None) -> str:
    """The mode Memgraph is in now. (`SHOW STORAGE INFO` alone says only the mode it *started* in)"""
    database = database or Database.default
    await prepared(database)
    for row in await statements(database, "SHOW STORAGE INFO ON CURRENT DATABASE"):
        if row["storage info"] == "storage_mode":
            return str(row["value"])
    raise PanglossBulkLoadError("Cannot tell which storage mode Memgraph is in")


async def set_storage_mode(database: Database, mode: str) -> None:
    try:
        await statements(database, f"STORAGE MODE {mode}")
    except neo4j.exceptions.Neo4jError as error:
        raise PanglossBulkLoadError(
            f"Memgraph would not switch to {mode}: {error.message}"
        ) from error
    now = await storage_mode(database)
    if now != mode:
        raise PanglossBulkLoadError(
            f"Memgraph is in {now}, not {mode}, after the switch"
        )
    logger.info("Memgraph storage mode: %s", mode)


async def something_in(database: Database) -> str | None:
    """The labels of one node that an empty database would not have, if there is one"""
    async with _session(database) as session:
        result = await session.run(
            "MATCH (n) WHERE none(l IN labels(n) WHERE l IN $allowed) "
            "RETURN labels(n) AS labels LIMIT 1",
            allowed=ALLOWED_LABELS,
        )
        row = await result.single()
    return ":".join(row["labels"]) if row else None


def constraint_text(row: dict[str, Any]) -> str:
    properties = ", ".join(f"n.{name}" for name in row["properties"])
    return f"(n:{row['label']}) ASSERT {properties} IS UNIQUE"


def constraint_name(row: dict[str, Any]) -> str:
    return f":{row['label']}({', '.join(row['properties'])})"


async def constraints_now(database: Database) -> list[dict[str, Any]]:
    return await statements(database, "SHOW CONSTRAINT INFO")


async def held(database: Database) -> list[dict[str, Any]] | None:
    """The constraints a bulk load took away (kept on the lock), or None if there is no such lock"""
    async with _session(database) as session:
        result = await session.run(
            "MATCH (l:PGMigrationLock {id: $id}) RETURN l.bulk_constraints AS constraints",
            id=LOCK_ID,
        )
        row = await result.single()
    if row is None or row["constraints"] is None:
        return None
    return json.loads(row["constraints"])


async def restore(database: Database | None = None) -> None:
    """Put the database back after a bulk load: transactional mode, the constraints, the text index,
    and the lock released. Safe to run again. Raises `PanglossBulkLoadError`, with the lock kept, if a
    constraint cannot be made (the data has a duplicate)."""
    database = database or Database.default
    await prepared(database)
    taken = await held(database)
    if taken is None:
        raise PanglossBulkLoadError(
            "There is no bulk load to recover: the database has no lock that one made"
        )
    if await storage_mode(database) != TRANSACTIONAL:
        await set_storage_mode(database, TRANSACTIONAL)

    have = {constraint_name(row) for row in await constraints_now(database)}
    failed: list[str] = []
    for row in taken:
        if constraint_name(row) in have:
            continue
        try:
            await statements(database, f"CREATE CONSTRAINT ON {constraint_text(row)}")
            logger.info("Constraint made again: %s", constraint_name(row))
        except neo4j.exceptions.Neo4jError as error:
            failed.append(f"{constraint_name(row)}: {error.message}")
    if failed:
        logger.error(
            "Bulk load: %s constraint(s) could not be made again: %s",
            len(failed),
            "; ".join(failed),
        )
        raise PanglossBulkLoadError(
            "The data loaded has duplicates, so the unique constraints could not be made again:\n  "
            + "\n  ".join(failed)
            + "\nThe database is read-only (the migration lock is kept) until that is put right: "
            "remove the duplicates, then run `pangloss memgraph bulk-recover`."
        )
    await rebuild_text_indexes(database)
    await unlock(database)
    logger.info("Bulk load finished: the database is back to normal")


@asynccontextmanager
async def bulk_ingest(
    who: str | None = None, database: Database | None = None
) -> AsyncGenerator[None]:
    """Write to an empty database in Memgraph's analytical mode (see the module). Raises
    `PanglossBulkLoadError` if the database is not empty, or not in the usual mode, and
    `PanglossMigrationError` if a migration (or a bulk load) holds the lock."""
    database = database or Database.default
    await prepared(database)

    mode = await storage_mode(database)
    if mode != TRANSACTIONAL:
        raise PanglossBulkLoadError(
            f"Memgraph is in {mode}: a bulk load that did not finish? `pangloss memgraph bulk-recover` "
            "puts it back"
        )
    found = await something_in(database)
    if found:
        raise PanglossBulkLoadError(
            f"A bulk load is only for an empty database, and this has data (a :{found} node, at least). "
            "Nothing was changed"
        )
    constraints = await constraints_now(database)
    unsupported = [row for row in constraints if row["constraint type"] != "unique"]
    if unsupported:
        raise PanglossBulkLoadError(
            "Cannot bulk load with constraints other than unique ones: "
            + ", ".join(
                f":{row['label']} ({row['constraint type']})" for row in unsupported
            )
        )

    await lock(who=f"bulk load{f' by {who}' if who else ''}", database=database)
    saved = False
    try:
        # (kept on the lock before anything is dropped, so that a load that is killed can be put back)
        async with _session(database) as session:
            result = await session.run(
                "MATCH (l:PGMigrationLock {id: $id}) SET l.bulk_constraints = $constraints",
                id=LOCK_ID,
                constraints=json.dumps(constraints),
            )
            await result.consume()
        saved = True
        for row in constraints:
            await statements(database, f"DROP CONSTRAINT ON {constraint_text(row)}")
        await set_storage_mode(database, ANALYTICAL)
    except BaseException:
        if saved:
            await restore(database)
        else:
            await unlock(database)
        raise

    logger.info(
        "Bulk load started: %s constraints dropped, analytical mode", len(constraints)
    )
    database.bulk_loading = True
    try:
        yield
    except BaseException:
        logger.error(
            "The bulk load stopped part way: nothing is rolled back, and the database holds "
            "what was written before"
        )
        raise
    finally:
        database.bulk_loading = False
        await restore(database)
