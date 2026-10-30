"""What the packages that write their own queries (typology, calendar) take from this backend: see `pangloss_core.backend`"""

import neo4j

from pangloss_neo4j.databases.neo4j.database import (
    Database,
    Transaction,
    timeout_from_setting,
)
from pangloss_neo4j.databases.neo4j.visibility import unpublished_visible

__all__ = [
    "Database",
    "Transaction",
    "ensure_lock",
    "lock",
    "timeout_from_setting",
    "unpublished_visible",
    "user_exists",
]


async def ensure_lock(key: str) -> None:
    """Make the lock node of the key, in a transaction of its own, before the transaction that locks it is opened. (A
    transaction that makes the node cannot be retried over it: if two make it at once the second is refused at its commit,
    which the driver does not try again; and a transaction does not see a node made after it began.) Harmless if it is there"""

    @Database.default.write_transaction
    async def make(tx: Transaction) -> None:
        await (await tx.run("MERGE (:PGLock {key: $key})", key=key)).consume()

    try:
        await make()
    except neo4j.exceptions.ClientError as error:
        if "unique constraint" not in str(error).lower():
            raise
        # (another made it at the same moment, which is all that was wanted)


async def lock(tx: Transaction, key: str) -> None:
    """Make this transaction conflict with every other that locks the same `key`, until it ends: the other waits, and then
    sees what the first did. Without it, two changes that are each right alone can together be wrong (two moves in a
    hierarchy that make a loop): what two transactions add does not conflict. The lock is a node of its own (`:PGLock {key}`,
    unique); `ensure_lock(key)` makes it, before the transaction is opened."""
    taken = await (
        await tx.run(
            "MATCH (l:PGLock {key: $key}) SET l.writes = coalesce(l.writes, 0) + 1 RETURN count(l) AS taken",
            key=key,
        )
    ).single()
    if not taken or not taken["taken"]:
        raise RuntimeError(f"There is no lock {key!r}: ensure_lock({key!r}) makes it")


async def user_exists(username: str) -> bool:
    database = Database.default
    async with database.driver.session(
        database=database.settings.DATABASE.DATABASE_NAME
    ) as session:
        result = await session.run(
            "MATCH (u:PGUser {username: $username}) RETURN u LIMIT 1",
            username=username,
        )
        return await result.single() is not None
