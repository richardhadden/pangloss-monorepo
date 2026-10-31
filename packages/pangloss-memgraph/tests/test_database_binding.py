"""The models use the database that is in use when they are called (not when the backend was imported):
`install(database)` for the process, `using(database)` for a while"""

import subprocess
import sys

import pytest
from pangloss_models import initialise
from pangloss_models.model_bases.entity import Entity
from pangloss_users import current_request_username
from pangloss_memgraph.databases.memgraph.database import Database, current, using
from pangloss_memgraph.databases.memgraph.initialise_database import initialise_database

from .helpers import BULK_URI


def test_the_functions_of_the_models_are_imported_without_a_database():
    imported = subprocess.run(
        [
            sys.executable,
            "-c",
            "import pangloss_memgraph.databases.memgraph.exposed_functions",
        ],
        capture_output=True,
        text=True,
    )
    assert imported.returncode == 0, imported.stderr


@pytest.mark.asyncio(loop_scope="session")
async def test_another_database_is_used_within_using(clear_database, bulk_memgraph):
    class Person(Entity):
        pass

    initialise()
    main = current()
    other = Database(
        settings=main.settings.model_copy(
            update={
                "DATABASE": main.settings.DATABASE.model_copy(
                    update={"DB_URL": BULK_URI}
                )
            }
        )
    )

    async def run(statement: str, **params) -> None:
        driver = await other.ensure_driver()
        async with driver.session(
            database=other.settings.DATABASE.DATABASE_NAME
        ) as session:
            await (await session.run(statement, **params)).consume()

    try:
        await run("MATCH (n) DETACH DELETE n")
        await run("MERGE (:PGUser {username: $u})", u=current_request_username.get())
        with using(other):
            assert current() is other
            await initialise_database(other)
            await Person.Create(label="In the other").save()
            assert [p.label for p in (await Person.list()).results] == ["In the other"]

        assert current() is main
        await Person.Create(label="In the main one").save()
        assert [p.label for p in (await Person.list()).results] == ["In the main one"]
    finally:
        await run("MATCH (n) DETACH DELETE n")
        await other.close()
