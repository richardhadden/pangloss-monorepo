"""`backend.lock(tx, key)`: transactions that lock the same key run one after the other, and each sees what the one before did
(what the typology hierarchy relies on: two checks that are each right alone must not both pass)"""

import asyncio

import pytest
from pangloss_neo4j.databases.neo4j.backend import Transaction, ensure_lock, lock
from pangloss_neo4j.databases.neo4j.database import Database

pytestmark = pytest.mark.asyncio(loop_scope="session")

WRITERS = 6


async def add_one(database: Database, key: str, name: str) -> None:
    await ensure_lock(key)

    @database.write_transaction
    async def write(tx: Transaction) -> None:
        await lock(tx, key)
        seen = await (
            await tx.run("MATCH (c:Counter {name: $name}) RETURN c.n AS n", name=name)
        ).single()
        await asyncio.sleep(
            0.05
        )  # (long enough for the others to read the same number, if nothing stopped them)
        await tx.run(
            "MATCH (c:Counter {name: $name}) SET c.n = $n", name=name, n=seen["n"] + 1
        )

    await write()


async def test_transactions_that_lock_one_key_do_not_lose_each_others_changes(
    db_driver, clear_database
):
    database = Database.default
    db_driver.execute_query(
        "CREATE (:Counter {name: 'a', n: 0})",
        database=database.settings.DATABASE.DATABASE_NAME,
    )
    await asyncio.gather(*[add_one(database, "counter", "a") for _ in range(WRITERS)])

    rows, _, _ = db_driver.execute_query(
        "MATCH (c:Counter {name: 'a'}) RETURN c.n AS n",
        database=database.settings.DATABASE.DATABASE_NAME,
    )
    assert rows[0]["n"] == WRITERS


async def test_one_lock_node_is_made_for_a_key_however_many_ask_at_once(
    db_driver, clear_database
):
    database = Database.default
    await asyncio.gather(*[add_one_lock(database, "once") for _ in range(WRITERS)])

    rows, _, _ = db_driver.execute_query(
        "MATCH (l:PGLock {key: 'once'}) RETURN count(l) AS locks, l.writes AS writes",
        database=database.settings.DATABASE.DATABASE_NAME,
    )
    assert rows[0]["locks"] == 1
    assert rows[0]["writes"] == WRITERS


async def add_one_lock(database: Database, key: str) -> None:
    await ensure_lock(key)

    @database.write_transaction
    async def write(tx: Transaction) -> None:
        await lock(tx, key)

    await write()
