"""What the `pangloss` command line needs of a database backend.

A backend (its `Storage`, named by `STORAGE`) has a `setup` module with these functions:

- `create_database(settings)`: make the process's database object, if there is not one.
  Not async, and it does not connect.
- `async connect()` / `async disconnect()`: open and close the connection. The
  command line does this inside the event loop that runs a command.
- `async setup_database()`: make what the backend needs in the database (for Memgraph,
  indexes, constraints and the text index), as far as it is not there already,
  and return a description of what was done, as a list of lines to show.
"""

import logging
from urllib.parse import urlparse

from pangloss_core.settings import BaseSettings

from pangloss_memgraph.databases.memgraph.database import (
    Database,
    current,
    install,
    installed,
)
from pangloss_memgraph.databases.memgraph.initialise_database import (
    initialise_database,
)


logger = logging.getLogger("pangloss.memgraph.setup")


def create_database(settings: BaseSettings) -> Database:
    """Make the process's database (`database.install`) from the settings, if it has none
    already. It does not connect: `connect` does"""
    return installed() or install(Database(settings=settings))


async def connect() -> None:
    database = current()
    driver = await database.ensure_driver()
    await driver.verify_connectivity()
    # (the address and the database name: not the credentials)
    address = urlparse(database.settings.DATABASE.DB_URL)
    logger.info(
        "Connected to Memgraph at %s:%s (database %r)",
        address.hostname,
        address.port,
        database.settings.DATABASE.DATABASE_NAME,
    )


async def disconnect() -> None:
    database = current()
    if database.driver is not None:
        await database.close()
        logger.info("Disconnected from Memgraph")


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
