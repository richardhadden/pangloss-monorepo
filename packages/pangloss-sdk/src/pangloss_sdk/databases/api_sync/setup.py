"""What the `pangloss` command line needs of a database backend (see
`pangloss_memgraph.databases.memgraph.setup`). There is nothing to set up for a
remote Pangloss instance: this is a stub."""

from pangloss_core.settings import BaseSettings


def create_database(settings: BaseSettings) -> None:
    pass


async def connect() -> None:
    pass


async def disconnect() -> None:
    pass


async def setup_database() -> list[str]:
    return ["nothing to set up: the database is a remote Pangloss instance"]
