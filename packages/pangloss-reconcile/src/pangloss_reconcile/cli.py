"""`pangloss reconcile <command>`: reconciliation's own records.

pangloss reconcile sweep   the records of what was offered that can make no example now, removed
pangloss reconcile learn   the decisions kept fitted, compared and written as a fit, put in use past a check
                           (`--dry-run`: nothing written; `--use ID`: an earlier fit in use; `--use none`: none)
"""

import typer

cli = typer.Typer(
    name="reconcile",
    help="Reconciliation: what was offered for stand-ins, and the decisions kept of it",
    no_args_is_help=True,
)


@cli.callback()
def reconcile() -> None:
    """Reconciliation: what was offered for stand-ins, and the decisions kept of it"""
    # (a group: `pangloss reconcile sweep`, `pangloss reconcile learn`)


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
