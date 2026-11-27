"""`pangloss compare <command>`: what comparison learns from people's judgements.

pangloss compare learn    every judgement fitted, compared and written as a fit, put in use past a check
                          (`--dry-run`: nothing written; `--use ID`: an earlier fit in use; `--use none`: none)
pangloss compare status   the fit in use, how many judgements there are, and how many more a fit needs
"""

import asyncio
from collections.abc import Awaitable, Callable

import typer

cli = typer.Typer(
    name="compare",
    help="Comparison of statements: what is learnt from people's judgements",
    no_args_is_help=True,
)


@cli.callback()
def compare() -> None:
    """Comparison of statements: what is learnt from people's judgements"""
    # (a group: `pangloss compare learn`, `status`)


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
def learn(
    ctx: typer.Context,
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Do all of it but write nothing"
    ),
    use: str | None = typer.Option(
        None,
        "--use",
        help="Fit nothing: put the earlier fit of this id in use, through the same check; `none`: no fit in use",
    ),
) -> None:
    """Learn from people's judgements: read every judgement, make examples of "one event or two" and of "does this
    answer that" of the newest of each pair, fit both, compare each with the hand-set score on judgements held out,
    and write the fit, in use for each model that is of COMPARE_LEARN_FROM judgements or more and no worse than the
    hand-set score. Says what it did, line by line"""
    from pangloss_compare import fits

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
            used = [
                fits.TITLES[m].lower()
                for m in fits.MODELS
                if found[f"{fits.NAMES[m]}_used"]
            ]
            return f"The fit {found['id']} is in use, for {' and '.join(used)}"

        said = run_connected(ctx, using)
        typer.echo(said)
        if said.startswith("Refused: "):
            raise typer.Exit(1)
        return

    async def learnt() -> list[str]:
        return (await fits.learn(dry_run=dry_run)).lines()

    for line in run_connected(ctx, learnt):
        typer.echo(line)


@cli.command()
def status(ctx: typer.Context) -> None:
    """The fit in use, how many judgements there are, and how many more are needed for a fit to be used"""
    from pangloss_compare import fits

    for line in fits.status_lines(run_connected(ctx, fits.status)):
        typer.echo(line)
