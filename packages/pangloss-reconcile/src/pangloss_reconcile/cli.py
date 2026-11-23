"""`pangloss reconcile <command>`: reconciliation's own records.

pangloss reconcile sweep   the records of what was offered that can make no example now, removed
pangloss reconcile learn   the decisions kept fitted, compared and written as a fit, put in use past a check
                           (`--dry-run`: nothing written; `--use ID`: an earlier fit in use; `--use none`: none)
pangloss reconcile worker [--batch N] [--once]
                           the worker that suggests, on its own (with `RECONCILE_WORKER_IN_SERVER = False`);
                           `--once`: what can be done now, and stop
"""

import asyncio

import typer

cli = typer.Typer(
    name="reconcile",
    help="Reconciliation: what was offered for stand-ins, and the decisions kept of it",
    no_args_is_help=True,
)


@cli.callback()
def reconcile() -> None:
    """Reconciliation: what was offered for stand-ins, and the decisions kept of it"""
    # (a group: `pangloss reconcile sweep`, `pangloss reconcile learn`, `pangloss reconcile worker`)


@cli.command()
def sweep(ctx: typer.Context) -> None:
    """Remove the records of what the stored route offered that can make no example now: those older than
    RECONCILE_SHOWN_FOR minutes, and those whose stand-in is no longer in a document. Says how many went"""
    from pangloss_vectors.cli import run_connected

    from pangloss_reconcile.decisions import sweep as sweeping

    gone = run_connected(ctx, sweeping)
    typer.echo(f"{gone} record{'' if gone == 1 else 's'} of what was offered removed")


@cli.command()
def learn(
    ctx: typer.Context,
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Do all of it but write nothing (the records that would be swept are counted, not removed)",
    ),
    use: str | None = typer.Option(
        None,
        "--use",
        help="Fit nothing: put the earlier fit of this id in use, through the same check; `none`: no fit in use",
    ),
) -> None:
    """Learn from the decisions kept: sweep, read the examples of today's vectors and weights, fit the ranking and
    the "none of these" models, compare each with what it would replace, and write the fit, put in use only when it
    is of RECONCILE_LEARN_FROM decisions or more and its "none of these" model is no worse than always answering the
    commoner. Says what it did, line by line"""
    from pangloss_vectors.cli import run_connected

    from pangloss_reconcile import fits

    if use is not None:
        if dry_run:
            raise typer.BadParameter("--use and --dry-run are not given together")

        async def using() -> str:
            if use.lower() == "none":
                await fits.use(None)
                return fits.NO_FIT
            try:
                found = await fits.use(use)
            except fits.Refused as error:
                return f"Refused: {error}"
            assert found is not None
            return (
                f"The fit {found['id']} is in use (of {found['decisions']:,} decisions)"
            )

        said = run_connected(ctx, using)
        typer.echo(said)
        if said.startswith("Refused: "):
            raise typer.Exit(1)
        return

    async def learning() -> list[str]:
        return (await fits.learn(dry_run=dry_run)).lines()

    for line in run_connected(ctx, learning):
        typer.echo(line)


@cli.command("worker")
def run_worker(
    ctx: typer.Context,
    batch: int = typer.Option(5, "--batch", min=1, help="Heads claimed at once"),
    once: bool = typer.Option(
        False, "--once", help="Do what can be done now, say how many, and stop"
    ),
) -> None:
    """Run the worker that suggests who the stand-ins of the documents left for it are, until stopped (Ctrl-C). Only
    one works at a time: a second waits for the first's lease. It waits while the vectors are rebuilt, and for the
    vectors of the writes that left its work. It writes as RECONCILE_TOOLCHAIN (made if absent), and stops if that is
    a person or disabled"""
    from pangloss_vectors.cli import run_connected

    from pangloss_reconcile import suggesting
    from pangloss_reconcile.suggesting import ToolchainRefused, worker

    worker.settings.batch = batch
    if once:
        try:
            done = run_connected(ctx, suggesting.drain)
        except ToolchainRefused as error:
            typer.echo(f"Refused: {error}", err=True)
            raise typer.Exit(1) from None
        typer.echo(f"{done} document{'' if done == 1 else 's'} done")
        return

    async def run() -> None:
        try:
            await worker.run()
        except asyncio.CancelledError:
            pass

    try:
        run_connected(ctx, run)
    except KeyboardInterrupt:
        typer.echo("stopped")
