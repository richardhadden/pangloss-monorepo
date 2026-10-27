"""Commands for Memgraph, added to the `pangloss` command line as `pangloss memgraph
<command>` when `pangloss_memgraph` is in `INSTALLED_APPS`.

(Setting up the database is the core command `pangloss setup-database`, which calls
`databases.memgraph.setup.setup_database`.)
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import typer
from pangloss_models.bulk_upload import read_records, upload, validate
from pangloss_models.exceptions import (
    PanglossBulkLoadError,
    PanglossBulkRecordError,
    PanglossMigrationError,
)
from pangloss_users import current_request_username

from pangloss_memgraph.databases.memgraph.bulk import bulk_ingest, restore
from pangloss_memgraph.databases.memgraph.database import Database
from pangloss_memgraph.databases.memgraph.initialise_database import run_statement
from pangloss_memgraph.databases.memgraph.setup import connect, disconnect

cli = typer.Typer(
    name="memgraph", help="Memgraph database commands", no_args_is_help=True
)


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
        typer.echo(
            f"  {row['index type']}: :{row['label']}({', '.join(row['property'])})"
        )
    typer.secho("Unique constraints", bold=True)
    for row in found["constraints"]:
        typer.echo(
            f"  {row['constraint type']}: :{row['label']}({', '.join(row['properties'])})"
        )


def fail(message: str) -> typer.Exit:
    typer.secho(message, fg="red", err=True)
    return typer.Exit(1)


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


@cli.command("bulk-load")
def bulk_load(
    ctx: typer.Context,
    file: Path = typer.Argument(
        ..., exists=True, dir_okay=False, help="A JSON Lines file: a record a line"
    ),
    user: str = typer.Option(
        ..., "--user", help="The user the records are written as (they must exist)"
    ),
    concurrency: int = typer.Option(
        4,
        "--concurrency",
        min=1,
        help="How many are written at once, among records of one type (1 for a type whose records refer to each other)",
    ),
    validate_only: bool = typer.Option(
        False, "--validate-only", help="Check the file and write nothing"
    ),
) -> None:
    """Load a file of records into an EMPTY database, several times faster than writing them as usual

    Each line is a JSON object: its "type" (the model) and the fields of that model's `Create`.
    What a record refers to must be earlier in the file, so entities need ids of their own
    (`create_with_id`). The database is put into Memgraph's analytical storage mode for the
    load, with the unique constraints dropped, and put back after, which fails (and keeps the
    database read-only) if the file had a duplicate id or URL. See docs/large-data.md.
    """
    from pangloss_models import initialise

    project = ctx.obj
    project.import_models()
    initialise()

    # (every record is checked before the database is touched)
    try:
        counts = validate(read_records(file))
    except PanglossBulkRecordError as error:
        raise fail(f"{file}, {error}") from error
    total = sum(counts.values())
    typer.echo(
        f"{total} records: " + ", ".join(f"{n} {name}" for name, n in counts.items())
    )
    if validate_only:
        typer.secho("All are valid; nothing was written", fg="green")
        return

    started = time.monotonic()

    def progress(done: int) -> None:
        if done % 5000 == 0:
            typer.echo(f"  {done} of {total} ...", err=True)

    async def load() -> dict[str, int]:
        if not await user_exists(user):
            raise PanglossBulkLoadError(
                f"There is no user called {user!r}: `pangloss users create` makes one"
            )
        current_request_username.set(user)
        async with bulk_ingest(who=user):
            return await upload(
                read_records(file), concurrency=concurrency, progress=progress
            )

    try:
        written = run_connected(load)
    except PanglossBulkRecordError as error:
        raise fail(
            f"{file}, {error}\nThe records before it were written, and the database is back to "
            "normal, with what was written so far (nothing is rolled back)."
        ) from error
    except (PanglossBulkLoadError, PanglossMigrationError) as error:
        raise fail(str(error)) from error

    seconds = max(time.monotonic() - started, 0.001)
    typer.secho(
        f"Wrote {sum(written.values())} records in {seconds:.0f} s "
        f"({sum(written.values()) / seconds:.0f} a second)",
        fg="green",
    )


@cli.command("bulk-recover")
def bulk_recover() -> None:
    """Put the database back after a bulk load that stopped, or left duplicates

    Switches Memgraph back to its usual mode, makes the unique constraints again and the text
    index, and removes the lock. If the data has a duplicate, says which constraint it is, and
    leaves the lock: remove the duplicate, and run this again.
    """
    try:
        run_connected(restore)
    except (PanglossBulkLoadError, PanglossMigrationError) as error:
        raise fail(str(error)) from error
    typer.secho("The database is back to normal", fg="green")
