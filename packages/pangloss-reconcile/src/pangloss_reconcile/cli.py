"""`pangloss reconcile <command>`: reconciliation's own records.

pangloss reconcile sweep   the records of what was offered that can make no example now, removed
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
    # (a group of one command is still a group, `pangloss reconcile sweep`, and not the command itself)


@cli.command()
def sweep(ctx: typer.Context) -> None:
    """Remove the records of what the stored route offered that can make no example now: those older than
    RECONCILE_SHOWN_FOR minutes, and those whose stand-in is no longer in a document. Says how many went"""
    from pangloss_vectors.cli import run_connected

    from pangloss_reconcile.decisions import sweep as sweeping

    gone = run_connected(ctx, sweeping)
    typer.echo(f"{gone} record{'' if gone == 1 else 's'} of what was offered removed")
