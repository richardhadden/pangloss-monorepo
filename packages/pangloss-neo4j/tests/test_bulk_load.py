"""`bulk_ingest`: writing to an empty database, with the migration lock held and the constraints in place.

(Memgraph's switches to its analytical storage mode and drops the constraints; Neo4j has no such mode, so there is much less
to put back. These tests have a Neo4j of their own (port 7694, started if it is not there): the load needs an empty database.)
"""

import asyncio

import pytest
import pytest_asyncio
from pangloss_models.exceptions import (
    PanglossBulkLoadError,
    PanglossMigrationError,
    PanglossReadOnlyError,
)
from pangloss_neo4j.databases.neo4j import migration_backend as backend
from pangloss_neo4j.databases.neo4j.bulk import bulk_ingest, held, restore
from pangloss_neo4j.databases.neo4j.database import Database
from pangloss_neo4j.databases.neo4j.initialise_database import (
    UNIQUE_CONSTRAINTS,
    initialise_database,
)
from pangloss_neo4j.databases.neo4j.schema import list_constraints, run_statement

from .conftest import NEO4J_DATABASE
from .helpers import BULK_URI

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def statements(database: Database, statement: str):
    return await run_statement(database.driver, NEO4J_DATABASE, statement)


@pytest_asyncio.fixture(loop_scope="session")
async def database(bulk_neo4j):
    """A database of its own with nothing but a user and what Pangloss makes"""
    shared = Database.default
    database = object.__new__(Database)
    database.settings = shared.settings.model_copy(
        update={
            "DATABASE": shared.settings.DATABASE.model_copy(update={"DB_URL": BULK_URI})
        }
    )
    await database._initialise_driver()
    await statements(database, "MATCH (n) DETACH DELETE n")
    await backend.ensure_ready(database)
    await initialise_database(database)
    await statements(database, "CREATE (:PGUser {username: 'bulk-test'})")
    try:
        yield database
    finally:
        database.bulk_loading = False
        await statements(database, "MATCH (n) DETACH DELETE n")
        await database.close()


async def constraints(database: Database) -> set[tuple[str, tuple[str, ...]]]:
    return {
        (c.label, c.properties)
        for c in await list_constraints(database.driver, NEO4J_DATABASE)
    }


async def locks(database: Database) -> int:
    rows = await statements(
        database, "MATCH (l:PGMigrationLock) RETURN count(l) AS locks"
    )
    return rows[0]["locks"]


async def count(database: Database, label: str) -> int:
    rows = await statements(database, f"MATCH (n:{label}) RETURN count(n) AS c")
    return rows[0]["c"]


async def test_the_body_runs_with_the_lock_and_the_constraints_and_the_lock_is_released(
    database,
):
    before = await constraints(database)
    assert {(label, (prop,)) for label, prop in UNIQUE_CONSTRAINTS} <= before

    async with bulk_ingest(who="ann", database=database):
        assert await locks(database) == 1
        assert await held(database) == "bulk load by ann"
        assert await constraints(database) == before  # (not dropped, as Memgraph's are)
        for i in range(50):
            await statements(
                database,
                f"CREATE (:PGIndexableNode {{id: 'n{i}', label: 'a bulk {i}'}})",
            )

    assert await locks(database) == 0
    assert await constraints(database) == before
    assert await count(database, "PGIndexableNode") == 50  # (what was written stays)


async def test_a_duplicate_fails_the_write_that_has_it_and_the_load_goes_on(database):
    """(Memgraph finds duplicates only when the constraints come back, and then keeps the database read-only until they
    are put right. Here a duplicate is refused as it is written.)"""
    import neo4j

    async with bulk_ingest(database=database):
        await statements(database, "CREATE (:PGUrl {url: 'https://x/1'})")
        with pytest.raises(neo4j.exceptions.ConstraintError):
            await statements(database, "CREATE (:PGUrl {url: 'https://x/1'})")
        await statements(database, "CREATE (:PGUrl {url: 'https://x/2'})")

    assert await count(database, "PGUrl") == 2
    assert await locks(database) == 0


async def test_the_text_index_finds_what_the_load_wrote(database):
    async with bulk_ingest(database=database):
        await statements(
            database,
            "CREATE (:PGIndexableNode {id: 'x1', label: 'Charlemagne crowned'}), "
            "(:PGIndexableNode {id: 'x2', label: 'Leo III'})",
        )

    rows = await statements(
        database,
        "CALL db.index.fulltext.queryNodes('label_text', '*charlemagne*') YIELD node "
        "RETURN node.id AS id",
    )
    assert [row["id"] for row in rows] == ["x1"]


async def test_a_database_with_data_is_refused_and_not_touched(database):
    await statements(database, "CREATE (:PGIndexableNode {id: 'there'})")
    before = await constraints(database)

    with pytest.raises(PanglossBulkLoadError, match="only for an empty database"):
        async with bulk_ingest(database=database):
            pytest.fail("the body must not run")

    assert await constraints(database) == before
    assert await locks(database) == 0


async def test_users_and_the_record_of_migrations_do_not_count_as_data(database):
    await statements(
        database,
        "CREATE (:PGMigration {app: 'a', name: '0001'}), (:PGAccessToken {token_hash: 'h'})",
    )

    async with bulk_ingest(database=database):
        assert await locks(database) == 1


async def test_a_migration_lock_that_is_held_refuses_it(database):
    await backend.lock("a migrate", database=database)

    with pytest.raises(PanglossMigrationError, match="Another migrate"):
        async with bulk_ingest(database=database):
            pytest.fail("the body must not run")

    assert await locks(database) == 1  # (the other's: it is not ours to remove)
    assert await held(database) is None  # (and it is not a bulk load's)


async def test_a_failure_in_the_body_releases_the_lock_and_is_raised(database):
    with pytest.raises(RuntimeError, match="the load failed"):
        async with bulk_ingest(database=database):
            await statements(database, "CREATE (:PGIndexableNode {id: 'half'})")
            raise RuntimeError("the load failed")

    assert await locks(database) == 0
    assert await count(database, "PGIndexableNode") == 1  # (nothing is rolled back)


async def test_recover_after_a_load_that_was_killed(database):
    loading = bulk_ingest(who="killed", database=database)
    await loading.__aenter__()
    # (the process dies here: nothing runs the end of the block)
    database.bulk_loading = False
    assert await locks(database) == 1

    with pytest.raises(PanglossMigrationError, match="Another migrate"):
        async with bulk_ingest(database=database):
            pytest.fail("a second load must not start over the first")

    await restore(database)
    assert await locks(database) == 0

    with pytest.raises(PanglossBulkLoadError, match="no bulk load to recover"):
        await restore(database)


async def test_recover_does_not_remove_the_lock_of_a_migration(database):
    await backend.lock("a migrate", database=database)
    with pytest.raises(PanglossBulkLoadError, match="no bulk load to recover"):
        await restore(database)
    assert await locks(database) == 1
    await backend.unlock(database)


async def test_its_own_writes_are_let_through_the_lock_and_only_its_own(database):
    @database.write_transaction
    async def write(tx):
        await tx.run("CREATE (:PGIndexableNode {id: 'mine'})")

    with pytest.raises(PanglossReadOnlyError):
        await backend.lock("someone", database=database)
        try:
            await write()
        finally:
            await backend.unlock(database)

    async with bulk_ingest(database=database):
        await write()  # (the lock is held: this is the load's)
    assert await count(database, "PGIndexableNode") == 1

    # after, another's lock refuses it again
    await backend.lock("someone", database=database)
    try:
        with pytest.raises(PanglossReadOnlyError):
            await write()
    finally:
        await backend.unlock(database)


async def test_writes_are_not_called_slow_during_a_load_unless_they_are_very_slow(
    database, caplog
):
    import logging

    from pangloss_neo4j.databases.neo4j.database import timed

    async def takes(milliseconds: int) -> None:
        async def run() -> None:
            await asyncio.sleep(milliseconds / 1000)

        await timed(database, "write", takes, run)

    caplog.set_level(logging.DEBUG, logger="pangloss.neo4j.transactions")
    await takes(700)  # (over the usual 500 ms)
    assert any("(slow)" in record.message for record in caplog.records)

    caplog.clear()
    async with bulk_ingest(database=database):
        await takes(700)
        assert not any("(slow)" in record.message for record in caplog.records)
    assert database.slow_query_threshold is None

    caplog.clear()
    await takes(700)  # (and as usual again after)
    assert any("(slow)" in record.message for record in caplog.records)
