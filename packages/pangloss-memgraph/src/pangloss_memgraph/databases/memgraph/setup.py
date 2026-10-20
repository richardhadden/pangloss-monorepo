"""What the `pangloss` command line needs of a database backend.

A backend package (`DATABASE_MODULE`) supplies a `setup` module with these functions:

- `create_database(settings)`: make the default database object, if there is not one.
  Not async, and it does not connect: `exposed_functions` needs it to exist when it is imported.
- `async connect()` / `async disconnect()`: open and close the connection. The
  command line does this inside the event loop that runs a command.
- `async setup_database()`: make what the backend needs in the database (for Memgraph,
  indexes, constraints, the text index and enums), as far as it is not there already,
  and return a description of what was done, as a list of lines to show.
"""

from pangloss_core.settings import BaseSettings

from pangloss_memgraph.databases.memgraph.database import Database
from pangloss_memgraph.databases.memgraph.initialise_database import (
    initialise_database,
)


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


async def disconnect() -> None:
    database = Database.default
    if hasattr(database, "driver") and not database.driver._closed:
        await database.driver.close()


async def setup_database() -> list[str]:
    setup = await initialise_database()
    return [
        *[f"created: {description}" for description in setup.created],
        *[f"already present: {description}" for description in setup.already_present],
    ]
