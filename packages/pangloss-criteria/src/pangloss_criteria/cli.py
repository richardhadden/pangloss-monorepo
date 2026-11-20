"""`pangloss criteria <command>`: the worker, and what is waiting for it.

pangloss criteria status              what is pending and claimed, and how many descriptions there are of each kind
pangloss criteria explain ID          what a description is, which writes it is evaluated for, and how
pangloss criteria rebuild [--type T]  every description evaluated again in full (after a bulk load)
pangloss criteria check               the descriptions whose criteria no longer hold (exits with 1 if any)
pangloss criteria worker              the worker, on its own (with `CRITERIA_WORKER_IN_SERVER = False`)
"""

import asyncio
import dataclasses
import json
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
    """What is pending for the worker, how much of it is claimed, and how long the oldest has waited; how many
    descriptions there are, how many are far, have no anchor (evaluated root first), are too broad (more candidates
    than are linked) or are broken"""
    from pangloss_criteria.maintenance import description_status
    from pangloss_criteria.worker import pending_status

    async def read() -> tuple[dict, dict]:
        return await pending_status(), await description_status()

    found, kinds = run_connected(ctx, read)
    behind = (
        f" (the oldest for {max(0, round(time.time() - found['oldest']))} s)"
        if found.get("oldest")
        else ""
    )
    typer.echo(
        f"pending: {found['pending']} heads ({found['claimed']} claimed){behind}"
    )
    typer.echo(f"descriptions: {kinds['descriptions']}")
    typer.echo(
        f"  far: {kinds['far']} (evaluated in full after every write of a class they depend on)"
    )
    typer.echo(
        f"  no anchor, evaluated root first: {kinds['no_anchor']} (of them far: {kinds['far_no_anchor']})"
    )
    typer.echo(
        f"  too broad: {kinds['too_broad']} (more candidates than are linked; the count is exact after `rebuild`)"
    )
    typer.echo(f"  broken: {kinds['broken']}")
    if kinds["shared_places"]:
        typer.echo(
            f"  places with the criteria of another place of the same one: {kinds['shared_places']}"
        )
    if kinds["no_holder"]:
        typer.secho(
            f"  places of a mark no place of their document holds criteria for: {kinds['no_holder']}"
            " (`pangloss criteria check`)",
            fg="yellow",
        )
    if kinds["not_fitting"] > kinds["broken"]:
        typer.secho(
            f"  criteria that do not fit the models now: {kinds['not_fitting']} (`pangloss criteria check`)",
            fg="yellow",
        )


@cli.command()
def explain(
    ctx: typer.Context,
    id: str = typer.Argument(..., help="The id of the description"),
) -> None:
    """What a description is: local or far, its anchors, complete or not; which writes it is evaluated for, and
    how; how a full evaluation is made; and the query of its test"""
    from pangloss_criteria.maintenance import explain as explained

    told = run_connected(ctx, lambda: explained(id))
    if told is None:
        typer.secho(f"No description {id}", fg="red", err=True)
        raise typer.Exit(2)
    typer.secho(f"{told.id}  (in {told.head})", bold=True)
    if told.same_one is not None:
        typer.echo(
            f"  the same one as the other places of its document with the mark {told.same_one}"
            + (
                f": evaluated by the criteria of {told.evaluated_by}"
                if told.evaluated_by
                else ""
            )
        )
    typer.echo(f"  criteria: {told.criteria}")
    typer.echo(
        f"  candidates: {told.linked} linked, {told.count} in all ({told.count_everyone} seen by everyone)"
    )
    if told.broken:
        typer.secho(f"  broken: {told.broken}", fg="yellow")
    if told.error:
        typer.secho(f"  does not fit the models: {told.error}", fg="red")
        return
    typer.echo(
        f"  {told.reach}, {'complete' if told.complete else 'not complete'}"
        + (
            ""
            if told.stored["reach"] is not None
            else " (worked out now: saved before it was stored)"
        )
    )
    if not told.anchors:
        typer.echo("  anchors: none")
    for anchor in told.anchors:
        merged = "".join(
            f" ({id} merged into {survivor})"
            for id, survivor in anchor["merged"].items()
        )
        typer.echo(
            f"  anchor: {' or '.join(anchor['ids'])}, {anchor['hops']} hops{merged}"
        )
    typer.echo("  evaluated after:")
    for line in told.chosen_for:
        typer.echo(f"    - {line}")
    typer.echo(f"  in full: {told.in_full}")
    typer.echo("  the query of its test (as a logged-in reader):")
    typer.echo("    " + told.query.strip().replace("\n", "\n    "))
    typer.echo(f"    parameters: {json.dumps(told.params)}")


@cli.command()
def rebuild(
    ctx: typer.Context,
    type_name: str | None = typer.Option(
        None,
        "--type",
        help="Only the descriptions whose criteria are of this class, or one below it",
    ),
) -> None:
    """Every description evaluated again in full, and written where the result is another. After a bulk load (which
    leaves nothing pending), a migration that touches a class the criteria name, or a change of
    `CRITERIA_MAX_CANDIDATES`. Refused while another worker works on the database"""
    from pangloss_criteria.maintenance import CriteriaWorkerBusy
    from pangloss_criteria.maintenance import rebuild as rebuilding

    try:
        done = run_connected(ctx, lambda: rebuilding(type_name))
    except CriteriaWorkerBusy as error:
        typer.secho(str(error), fg="red", err=True)
        raise typer.Exit(1) from None
    typer.echo(json.dumps(dataclasses.asdict(done)))


@cli.command()
def check(ctx: typer.Context) -> None:
    """The descriptions whose criteria no longer fit the models, or that name an entity that is deleted or not there
    (ids of merged entities are resolved, and said). Exits with 1 if there are any"""
    from pangloss_criteria.maintenance import check as checking

    problems, merged = run_connected(ctx, checking)
    for note in merged:
        typer.echo(f"{note.description} (in {note.head}): {note.problem}")
    for problem in problems:
        typer.secho(
            f"{problem.description} (in {problem.head}): {problem.problem}", fg="red"
        )
    if problems:
        raise typer.Exit(1)
    typer.echo("every description's criteria fit the models")


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
