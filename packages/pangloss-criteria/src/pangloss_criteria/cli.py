"""`pangloss criteria <command>`: the worker, and what is waiting for it.

pangloss criteria status              what is pending and claimed, and for how long
pangloss criteria worker              the worker, on its own (with `CRITERIA_WORKER_IN_SERVER = False`)
"""

import asyncio
import time
from collections.abc import Awaitable, Callable

import typer

cli = typer.Typer(
    name="criteria",
    help="Matches criteria: descriptions, their candidates, and the worker",
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


@cli.command()
def status(ctx: typer.Context) -> None:
    """What is pending for the worker, how much of it is claimed, and how long the oldest has waited"""
    from pangloss_criteria.worker import pending_status

    found = run_connected(ctx, pending_status)
    behind = (
        f" (the oldest for {max(0, round(time.time() - found['oldest']))} s)"
        if found.get("oldest")
        else ""
    )
    typer.echo(
        f"pending: {found['pending']} heads ({found['claimed']} claimed){behind}"
    )


@cli.command("worker")
def run_worker(
    ctx: typer.Context,
    batch: int = typer.Option(200, "--batch", help="Heads claimed at once"),
) -> None:
    """Run the worker until stopped (Ctrl-C). Only one works at a time: a second waits for the first's lease"""
    from pangloss_criteria.worker import worker

    worker.settings.batch = batch

    async def run() -> None:
        try:
            await worker.run()
        except asyncio.CancelledError:
            pass

    try:
        run_connected(ctx, run)
    except KeyboardInterrupt:
        typer.echo("stopped")
