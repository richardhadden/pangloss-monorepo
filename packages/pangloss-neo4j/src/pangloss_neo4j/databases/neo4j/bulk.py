"""Loading a lot of data into an empty database.

```python
async with bulk_ingest():
    ...  # write with the models, as usual (`await Person.Create(...).save()`)
```

Memgraph's `bulk_ingest` switches the database to its *analytical storage mode* (no transactions, no versions, several times
as fast) and drops the unique constraints for the load. **Neo4j has no such mode**, so here the load is made in ordinary
transactions, by as many writers at once as the caller likes, with the constraints in place: ids and URLs are checked as they
are written, and a duplicate fails the write that made it (the load does not end with a database that has to be put right).
It is slower than Memgraph's analytical load; how much is measured in `docs/neo4j-implementation.md`. (Neo4j's own fast way,
`neo4j-admin database import`, is offline and has its own file format: not used.)

What `bulk_ingest` keeps from Memgraph's:

1. it refuses unless the database is **empty** (it may hold the record of migrations and the users);
2. it takes the migration lock, so `migrate` and the API (anything but this process) cannot write, and its own writes are
   let through;
3. whatever happened in the body, it releases the lock.

A load that was killed leaves the lock: `restore()` (`pangloss neo4j bulk-recover`) releases it. Nothing else has to be put
back, as nothing was taken away. See `docs/large-data.md`.
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from pangloss_models.exceptions import PanglossBulkLoadError

from pangloss_neo4j.databases.neo4j.database import Database, slow_query_ms
from pangloss_neo4j.databases.neo4j.migration_backend import (
    LOCK_ID,
    _session,
    lock,
    unlock,
)

logger = logging.getLogger("pangloss.neo4j.bulk")

# A write is "slow" (a warning) over this during a load, if `SLOW_QUERY_MS` is less: with several
# writers at once most take longer than the usual 500 ms, and a warning for each says nothing
QUIET_DURING_LOAD_MS = 10_000

# What an empty database may hold: the record of migrations, and the users (and their tokens), without
# whom nothing can be written
ALLOWED_LABELS = [
    "PGMigration",
    "PGMigrationLock",
    "PGUser",
    "PGAccessToken",
    "PGRevokedSession",
]

BULK_LOCK_PREFIX = "bulk load"


async def prepared(database: Database) -> None:
    if not hasattr(database, "driver"):
        await database._initialise_driver()


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


async def held(database: Database) -> str | None:
    """Who a bulk load that holds the lock is by (the lock's `acquired_by`), or None if no bulk load does"""
    async with _session(database) as session:
        result = await session.run(
            "MATCH (l:PGMigrationLock {id: $id}) RETURN l.acquired_by AS who",
            id=LOCK_ID,
        )
        row = await result.single()
    if row is None or not str(row["who"] or "").startswith(BULK_LOCK_PREFIX):
        return None
    return str(row["who"])


async def restore(database: Database | None = None) -> None:
    """Finish a bulk load that did not end: release its lock. Safe to run again. Raises `PanglossBulkLoadError` if the lock
    is not a bulk load's (a migration's lock is `pangloss migrate --unlock`)"""
    database = database or Database.default
    await prepared(database)
    if await held(database) is None:
        raise PanglossBulkLoadError(
            "There is no bulk load to recover: the database has no lock that one made"
        )
    await unlock(database)
    logger.info("Bulk load finished: the lock is released")


@asynccontextmanager
async def bulk_ingest(
    who: str | None = None, database: Database | None = None
) -> AsyncGenerator[None]:
    """Write to an empty database (see the module). Raises `PanglossBulkLoadError` if the database is not empty, and
    `PanglossMigrationError` if a migration (or a bulk load) holds the lock."""
    database = database or Database.default
    await prepared(database)

    found = await something_in(database)
    if found:
        raise PanglossBulkLoadError(
            f"A bulk load is only for an empty database, and this has data (a :{found} node, at least). "
            "Nothing was changed"
        )

    await lock(
        who=f"{BULK_LOCK_PREFIX}{f' by {who}' if who else ''}", database=database
    )
    logger.info("Bulk load started")
    database.bulk_loading = True
    database.slow_query_threshold = max(
        slow_query_ms(database.settings), QUIET_DURING_LOAD_MS
    )
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
        database.slow_query_threshold = None
        await unlock(database)
        logger.info("Bulk load finished")
