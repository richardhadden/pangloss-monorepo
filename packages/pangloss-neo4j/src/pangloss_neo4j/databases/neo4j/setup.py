"""What the `pangloss` command line needs of a database backend.

A backend package (`DATABASE_MODULE`) supplies a `setup` module with these functions:

- `create_database(settings)`: make the default database object, if there is not one.
  Not async, and it does not connect: `exposed_functions` needs it to exist when it is imported.
- `async connect()` / `async disconnect()`: open and close the connection. The
  command line does this inside the event loop that runs a command.
- `async setup_database()`: make what the backend needs in the database (for Neo4j,
  indexes, constraints and the text index), as far as it is not there already,
  and return a description of what was done, as a list of lines to show.
"""

import logging
from urllib.parse import urlparse

from pangloss_core.settings import BaseSettings

from pangloss_neo4j.databases.neo4j.database import Database
from pangloss_neo4j.databases.neo4j.initialise_database import (
    initialise_database,
)

logger = logging.getLogger("pangloss.neo4j.setup")


def create_database(settings: BaseSettings) -> None:
    """Make the default database object, if there is not one already (there is one
    default per process, and it holds the connection)"""
    if "default" not in Database.__dict__:
        Database(settings=settings)


async def connect() -> None:
    database = Database.default
    if not hasattr(database, "driver") or database.driver._closed:
        await database._initialise_driver()
    await database.driver.verify_connectivity()
    # (the address and the database name: not the credentials)
    address = urlparse(database.settings.DATABASE.DB_URL)
    logger.info(
        "Connected to Neo4j at %s:%s (database %r)",
        address.hostname,
        address.port,
        database.settings.DATABASE.DATABASE_NAME,
    )


async def disconnect() -> None:
    database = Database.default
    if hasattr(database, "driver") and not database.driver._closed:
        await database.driver.close()
        logger.info("Disconnected from Neo4j")


async def setup_database() -> list[str]:
    setup = await initialise_database()
    logger.info(
        "Database setup: %s made, %s already there",
        len(setup.created),
        len(setup.already_present),
    )
    return [
        *[f"created: {description}" for description in setup.created],
        *[f"already present: {description}" for description in setup.already_present],
    ]
