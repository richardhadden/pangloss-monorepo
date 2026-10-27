"""`pangloss zotero <command>`: sync a library once, watch it, and look at how it stands (added to the
`pangloss` command for an installed app with a `cli.py`)."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import typer

from pangloss_zotero import config

cli = typer.Typer(
    name="zotero",
    help="Keep a Zotero library in the database",
    no_args_is_help=True,
)


def run_connected[T](ctx: typer.Context, function: Callable[[], Awaitable[T]]) -> T:
    """Import and initialise the models, then run a coroutine function with the database connected"""
    from pangloss_models import initialise

    project = ctx.obj
    backend = project.require_database()
    project.import_models()
    initialise()

    async def main() -> T:
        await backend.connect()
        try:
            return await function()
        finally:
            await backend.disconnect()

    return asyncio.run(main())


def settings_of(ctx: typer.Context) -> Any:
    return ctx.obj.require_settings()


@cli.command()
def sync(
    ctx: typer.Context,
    library: list[str] = typer.Option(
        [],
        "--library",
        "-l",
        help="A library to sync, such as groups/2556736 (default: all in the settings)",
    ),
    full: bool = typer.Option(
        False, "--full", help="Read every item, not only what changed"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Say what would be done; write nothing"
    ),
) -> None:
    """Bring the libraries up to date, once"""
    from pangloss_zotero.client import ZoteroError
    from pangloss_zotero.watch import sync_libraries

    settings = settings_of(ctx)
    try:
        reports = run_connected(
            ctx,
            lambda: sync_libraries(
                settings, library or None, full=full, dry_run=dry_run
            ),
        )
    except ZoteroError as error:
        typer.secho(str(error), fg="red", err=True)
        raise typer.Exit(1) from error
    failed = False
    for report in reports:
        typer.echo(("(dry run) " if dry_run else "") + report.summary())
        for error in report.errors[:10]:
            failed = True
            typer.secho(f"  {error}", fg="red", err=True)
    if failed:
        raise typer.Exit(1)


@cli.command()
def watch(ctx: typer.Context) -> None:
    """Sync, then listen to Zotero and sync whenever a library changes (until stopped)

    The server does this itself, as a background task, unless ZOTERO_WATCH is False: run this instead
    when the server has several workers, and only one should listen."""
    from pangloss_zotero.watch import watch as run_watch

    settings = settings_of(ctx)
    typer.echo(
        "Watching " + ", ".join(config.libraries(settings)) + " (Ctrl-C to stop)"
    )
    try:
        run_connected(ctx, lambda: run_watch(settings))
    except KeyboardInterrupt:
        typer.echo("Stopped")


@cli.command()
def status(
    ctx: typer.Context,
    remote: bool = typer.Option(
        False, "--remote", help="Ask Zotero for its version too"
    ),
) -> None:
    """For each library: how far it has been synced, and when, and the last error"""
    from pangloss_zotero.client import ZoteroClient, ZoteroError
    from pangloss_zotero.mapping import build_table
    from pangloss_zotero.store import ModelStore

    settings = settings_of(ctx)

    async def collect() -> list[tuple[str, Any, int | None]]:
        store = ModelStore()
        rows = []
        async with ZoteroClient(
            config.api_key(settings), config.api_url(settings)
        ) as client:
            for library in config.libraries(settings):
                state = await store.library_state(library)
                latest = None
                if remote:
                    try:
                        latest = await client.library_version(library)
                    except ZoteroError as error:
                        typer.secho(f"{library}: {error}", fg="red", err=True)
                rows.append((library, state, latest))
        return rows

    for library, state, latest in run_connected(ctx, collect):
        line = f"{library}: version {state.synced_version}"
        if latest is not None:
            line += f" of {latest}" + (
                " (behind)" if latest > state.synced_version else " (up to date)"
            )
        line += (
            f", synced {state.last_sync:%Y-%m-%d %H:%M:%S}"
            if state.last_sync
            else ", never synced"
        )
        typer.echo(line)
        if state.last_error:
            typer.secho(f"  last error: {state.last_error}", fg="red")
    table = build_table()
    typer.echo(
        "Item types: "
        + (
            ", ".join(f"{t} -> {c}" for t, c in table.describe().items())
            or "(none claimed)"
        )
    )
    typer.echo(f"Anything else is written as {table.fallback.__name__}")


@cli.command()
def check(ctx: typer.Context) -> None:
    """Look for what is wrong with how Zotero is set up (settings, class declarations, fields the sync cannot give)"""
    from pangloss_models import initialise

    from pangloss_zotero.checks import problems

    project = ctx.obj
    settings = project.require_settings()
    project.import_models()
    initialise()
    found = problems(settings)
    for problem in found:
        typer.secho(problem, fg="red", err=True)
    if found:
        raise typer.Exit(1)
    typer.secho("Nothing is wrong", fg="green")
