"""Commands for Memgraph, added to the `pangloss` command line as `pangloss memgraph
<command>` when `pangloss_memgraph` is in `INSTALLED_APPS`.

(Setting up the database is the core command `pangloss setup-database`, which calls
`databases.memgraph.setup.setup_database`.)
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import typer

from pangloss_memgraph.databases.memgraph.database import Database
from pangloss_memgraph.databases.memgraph.initialise_database import run_statement
from pangloss_memgraph.databases.memgraph.setup import connect, disconnect

cli = typer.Typer(name="memgraph", help="Memgraph database commands", no_args_is_help=True)


def run_connected[T](function: Callable[[], Awaitable[T]]) -> T:
    """Run a coroutine function with the database connected"""

    async def main() -> T:
        await connect()
        try:
            return await function()
        finally:
            await disconnect()

    return asyncio.run(main())


async def show(statement: str) -> list[dict[str, Any]]:
    database = Database.default
    return await run_statement(
        database.driver, database.settings.DATABASE.DATABASE_NAME, statement
    )


@cli.command()
def info() -> None:
    """Show the indexes and constraints in the database"""

    async def collect():
        return {
            "indexes": await show("SHOW INDEX INFO"),
            "constraints": await show("SHOW CONSTRAINT INFO"),
        }

    try:
        found = run_connected(collect)
    except Exception as error:
        typer.secho(f"Cannot read the database: {error}", fg="red", err=True)
        raise typer.Exit(1) from error

    typer.secho("Indexes", bold=True)
    for row in found["indexes"]:
        typer.echo(f"  {row['index type']}: :{row['label']}({', '.join(row['property'])})")
    typer.secho("Unique constraints", bold=True)
    for row in found["constraints"]:
        typer.echo(
            f"  {row['constraint type']}: :{row['label']}({', '.join(row['properties'])})"
        )
