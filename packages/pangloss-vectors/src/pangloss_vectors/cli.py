"""`pangloss vectors <command>`: the vectors of similarity.

pangloss vectors rebuild [--part NAME]   every vector of a part (or of every part) made again, and the profiles
pangloss vectors status                  what is in use, and whether a rebuild is due (and why)
pangloss vectors weights                 the profiles and their weights; the parts, with dimension and signature
pangloss vectors worker [--batch N]      the worker, on its own (with `VECTORS_WORKER_IN_SERVER = False`)
"""

import asyncio
from collections.abc import Awaitable, Callable

import typer

cli = typer.Typer(
    name="vectors",
    help="Similarity: the vectors of documents and entities, their rebuild and status",
    no_args_is_help=True,
)


def initialised(ctx: typer.Context) -> None:
    """Import and initialise the models (the parts' dimensions and signatures are known after it)"""
    from pangloss_models import initialise

    ctx.obj.import_models()
    initialise()


def run_connected[T](ctx: typer.Context, function: Callable[[], Awaitable[T]]) -> T:
    """Import and initialise the models, then run a coroutine function with the database connected"""
    backend = ctx.obj.require_database()
    initialised(ctx)

    async def main() -> T:
        await backend.connect()
        try:
            return await function()
        finally:
            await backend.disconnect()

    return asyncio.run(main())


def weights_text(weights) -> str:
    from pangloss_vectors.status import weights_text as text

    return text(weights)


@cli.command()
def rebuild(
    ctx: typer.Context,
    part_name: str | None = typer.Option(
        None,
        "--part",
        help="Only this part (and the profiles that weigh it); every part if not given",
    ),
) -> None:
    """Make every vector of a part (or of every part) again, in a new generation, combine the profiles that weigh
    it, switch to them and drop the old ones. Searches meanwhile read the vectors in use. Also combines again a
    profile whose weights changed. Refused while another rebuild runs on the database"""
    from pangloss_models.exceptions import PanglossInitialisationError

    from pangloss_vectors.rebuild import VectorsRebuildBusy
    from pangloss_vectors.rebuild import rebuild as rebuilding

    try:
        done = run_connected(ctx, lambda: rebuilding(part_name))
    except PanglossInitialisationError as error:
        # (a part of that name is not registered)
        typer.secho(str(error), fg="red", err=True)
        raise typer.Exit(2) from None
    except VectorsRebuildBusy as error:
        typer.secho(str(error), fg="red", err=True)
        raise typer.Exit(1) from None
    for made in done.parts:
        typer.echo(
            f"part {made.part}: generation {made.generation}, {made.count} vectors in {made.seconds:.2f} s"
            f" ({made.dropped} of older generations dropped)"
        )
    for made in done.profiles:
        typer.echo(
            f"profile {made.profile}: generation {made.generation}, {made.count} vectors in {made.seconds:.2f} s"
            f", {made.why} ({made.dropped} of older generations dropped)"
        )
    for what, why in done.skipped.items():
        typer.secho(f"{what}: skipped, {why}", fg="yellow")
    typer.echo(f"done in {done.seconds:.2f} s")


@cli.command()
def status(ctx: typer.Context) -> None:
    """For each part and profile: the generation in use, when it was built, how many vectors, and whether a rebuild
    is due, and why. (`pangloss check` cannot say so: it does not read the database)"""
    from pangloss_vectors.status import status as reading

    found = run_connected(ctx, reading)

    def built(generation, built_at, count) -> str:
        if generation is None:
            return "never built"
        when = built_at.strftime("%Y-%m-%d %H:%M:%S UTC") if built_at else "?"
        return f"generation {generation}, built {when}, {count} vectors"

    for p in found.parts:
        typer.echo(
            f"part {p.part}: {built(p.generation, p.built_at, p.count)}"
            + (f", {p.stale} stale" if p.generation is not None else "")
            + f" (dimension {p.dimension}, signature {p.signature})"
        )
        if p.unavailable:
            typer.secho(f"  cannot be built here: {p.unavailable}", fg="yellow")
        for reason in p.reasons:
            typer.secho(f"  rebuild due: {reason}", fg="yellow")
    for p in found.profiles:
        typer.echo(
            f"profile {p.profile} ({weights_text(p.weights)}): {built(p.generation, p.built_at, p.count)}"
            f" (dimension {p.dimension})"
        )
        for reason in p.reasons:
            typer.secho(f"  rebuild due: {reason}", fg="yellow")
    if found.rebuilding is not None:
        since = found.rebuilding.since.strftime("%Y-%m-%d %H:%M:%S UTC")
        typer.echo(f"rebuilding now: {found.rebuilding.by}, since {since}")
    if found.rebuild_due:
        typer.secho(
            "A rebuild is due: pangloss vectors rebuild", fg="yellow", bold=True
        )


@cli.command()
def weights(ctx: typer.Context) -> None:
    """The profiles and the weight of each part in them; the parts, with the dimension and signature of their
    vectors today. Reads no database"""
    from pangloss_vectors import store
    from pangloss_vectors.parts import parts, profiles

    initialised(ctx)
    for name, given in profiles().items():
        typer.echo(f"profile {name}: {weights_text(given)}")
    for name, made in parts().items():
        typer.echo(
            f"part {name}: dimension {made.dimension()}, signature {store.part_signature(made)}, "
            f"{'refreshed after a write' if made.local else 'rebuilt only'}"
            + (f", needs {', '.join(sorted(made.requires))}" if made.requires else "")
        )


@cli.command("worker")
def run_worker(
    ctx: typer.Context,
    batch: int = typer.Option(200, "--batch", help="Heads claimed at once"),
) -> None:
    """Run the worker that keeps the vectors current after writes, until stopped (Ctrl-C). Only one works at a time:
    a second waits for the first's lease. It does nothing while a rebuild runs"""
    from pangloss_vectors.worker import worker

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
