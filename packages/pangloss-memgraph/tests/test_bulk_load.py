"""`bulk_ingest`: writing to an empty database in Memgraph's analytical storage mode.

It drops the unique constraints and changes the mode of the whole Memgraph, so these tests have a
Memgraph of their own (port 7691, started if it is not there), not the one the other tests share."""

import json

import neo4j
import pytest
import pytest_asyncio
from pangloss_memgraph.databases.memgraph import migration_backend as backend
from pangloss_memgraph.databases.memgraph.bulk import (
    ANALYTICAL,
    TRANSACTIONAL,
    bulk_ingest,
    constraint_name,
    constraints_now,
    restore,
    statements,
    storage_mode,
)
from pangloss_memgraph.databases.memgraph.database import Database
from pangloss_memgraph.databases.memgraph.initialise_database import (
    initialise_database,
)
from pangloss_models.exceptions import (
    PanglossBulkLoadError,
    PanglossMigrationError,
    PanglossReadOnlyError,
)

from .helpers import BULK_URI

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture(loop_scope="session")
async def database(bulk_memgraph):
    """A database of its own, in the usual mode, with nothing but a user and what Pangloss makes"""
    shared = Database.default
    database = object.__new__(Database)
    database.settings = shared.settings.model_copy(
        update={
            "DATABASE": shared.settings.DATABASE.model_copy(update={"DB_URL": BULK_URI})
        }
    )
    await database._initialise_driver()
    if await storage_mode(database) != TRANSACTIONAL:
        await statements(database, f"STORAGE MODE {TRANSACTIONAL}")
    await statements(database, "MATCH (n) DETACH DELETE n")
    await backend.ensure_ready(database)
    await initialise_database(database)
    await statements(database, "CREATE (:PGUser {username: 'bulk-test'})")
    try:
        yield database
    finally:
        database.bulk_loading = False
        if await storage_mode(database) != TRANSACTIONAL:
            await statements(database, f"STORAGE MODE {TRANSACTIONAL}")
        await statements(database, "MATCH (n) DETACH DELETE n")
        await database.close()


async def names(database: Database) -> set[str]:
    return {constraint_name(row) for row in await constraints_now(database)}


async def locks(database: Database) -> int:
    rows = await statements(
        database, "MATCH (l:PGMigrationLock) RETURN count(l) AS locks"
    )
    return rows[0]["locks"]


async def count(database: Database, label: str) -> int:
    rows = await statements(database, f"MATCH (n:{label}) RETURN count(n) AS c")
    return rows[0]["c"]


async def test_the_body_runs_in_analytical_mode_without_constraints_and_all_is_put_back(
    database,
):
    before = await names(database)
    assert (
        len(before) >= 10
    )  # (Pangloss's: ids, urls, users, tokens, the migration record)

    async with bulk_ingest(who="ann", database=database):
        assert await storage_mode(database) == ANALYTICAL
        assert await names(database) == set()
        assert await locks(database) == 1
        for i in range(50):
            await statements(
                database,
                f"CREATE (:PGIndexableNode {{id: 'n{i}', label: 'a bulk {i}'}})",
            )

    assert await storage_mode(database) == TRANSACTIONAL
    assert await names(database) == before
    assert await locks(database) == 0
    assert await count(database, "PGIndexableNode") == 50  # (what was written stays)
    # the constraints work again
    with pytest.raises(neo4j.exceptions.Neo4jError):
        await statements(database, "CREATE (:PGIndexableNode {id: 'n1'})")


async def test_the_text_index_finds_what_the_load_wrote(database):
    async with bulk_ingest(database=database):
        await statements(
            database,
            "CREATE (:PGIndexableNode {id: 'x1', label: 'Charlemagne crowned'}), "
            "(:PGIndexableNode {id: 'x2', label: 'Leo III'})",
        )

    rows = await statements(
        database,
        'CALL text_search.regex_search("label_text", "Charlemagne") YIELD node '
        "RETURN node.id AS id",
    )
    assert [row["id"] for row in rows] == ["x1"]


async def test_a_database_with_data_is_refused_and_not_touched(database):
    await statements(database, "CREATE (:PGIndexableNode {id: 'there'})")
    before = await names(database)

    with pytest.raises(PanglossBulkLoadError, match="only for an empty database"):
        async with bulk_ingest(database=database):
            pytest.fail("the body must not run")

    assert await storage_mode(database) == TRANSACTIONAL
    assert await names(database) == before
    assert await locks(database) == 0


async def test_users_and_the_record_of_migrations_do_not_count_as_data(database):
    await statements(
        database,
        "CREATE (:PGMigration {app: 'a', name: '0001'}), (:PGAccessToken {token_hash: 'h'})",
    )

    async with bulk_ingest(database=database):
        assert await storage_mode(database) == ANALYTICAL


async def test_a_migration_lock_that_is_held_refuses_it(database):
    await backend.lock("a migrate", database=database)
    before = await names(database)

    with pytest.raises(PanglossMigrationError, match="Another migrate"):
        async with bulk_ingest(database=database):
            pytest.fail("the body must not run")

    assert await storage_mode(database) == TRANSACTIONAL
    assert await names(database) == before
    assert await locks(database) == 1  # (the other's: it is not ours to remove)


async def test_a_failure_in_the_body_puts_everything_back_and_is_raised(database):
    before = await names(database)

    with pytest.raises(RuntimeError, match="the load failed"):
        async with bulk_ingest(database=database):
            await statements(database, "CREATE (:PGIndexableNode {id: 'half'})")
            raise RuntimeError("the load failed")

    assert await storage_mode(database) == TRANSACTIONAL
    assert await names(database) == before
    assert await locks(database) == 0
    assert await count(database, "PGIndexableNode") == 1  # (nothing is rolled back)


async def test_duplicates_are_found_when_the_constraints_come_back(database):
    before = await names(database)

    with pytest.raises(PanglossBulkLoadError, match="duplicates") as caught:
        async with bulk_ingest(database=database):
            await statements(
                database,
                "CREATE (:PGUrl {url: 'https://x/1'}), (:PGUrl {url: 'https://x/1'}), "
                "(:PGUrl {url: 'https://x/2'})",
            )

    # it says which, and the database is back to the usual mode, read-only until that is put right
    assert ":PGUrl(url)" in str(caught.value)
    assert "bulk-recover" in str(caught.value)
    assert await storage_mode(database) == TRANSACTIONAL
    assert await names(database) == before - {":PGUrl(url)"}
    assert await locks(database) == 1
    with pytest.raises(PanglossReadOnlyError):

        @database.write_transaction
        async def write(tx):
            await tx.run("CREATE (:Anything)")

        await write()

    # remove the duplicate; recover finishes it
    await statements(
        database,
        "MATCH (u:PGUrl {url: 'https://x/1'}) WITH u LIMIT 1 DETACH DELETE u",
    )
    await restore(database)

    assert await names(database) == before
    assert await locks(database) == 0
    assert await count(database, "PGUrl") == 2


async def test_recover_after_a_load_that_was_killed(database):
    before = await names(database)
    loading = bulk_ingest(who="killed", database=database)
    await loading.__aenter__()
    # (the process dies here: nothing runs the end of the block)
    database.bulk_loading = False
    assert await storage_mode(database) == ANALYTICAL
    assert await names(database) == set()

    with pytest.raises(PanglossBulkLoadError, match="bulk-recover"):
        async with bulk_ingest(database=database):
            pytest.fail("a second load must not start over the first")

    await restore(database)

    assert await storage_mode(database) == TRANSACTIONAL
    assert await names(database) == before
    assert await locks(database) == 0

    with pytest.raises(PanglossBulkLoadError, match="no bulk load to recover"):
        await restore(database)


async def test_what_the_lock_keeps_is_what_was_dropped(database):
    before = {
        json.dumps(sorted(row["properties"])) for row in await constraints_now(database)
    }

    async with bulk_ingest(database=database):
        rows = await statements(
            database,
            "MATCH (l:PGMigrationLock) RETURN l.bulk_constraints AS c, l.acquired_by AS who",
        )
        kept = json.loads(rows[0]["c"])
        assert {json.dumps(sorted(row["properties"])) for row in kept} == before
        assert "bulk load" in rows[0]["who"]


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
