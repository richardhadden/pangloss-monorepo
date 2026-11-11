"""`pangloss review <command>`: look at what is to be checked, and check it (added to the `pangloss` command for
an installed app with a `cli.py`)."""

import asyncio
from collections.abc import Awaitable, Callable
from uuid import UUID

import typer

from pangloss_review import service
from pangloss_review.exceptions import PanglossReviewError
from pangloss_review.status import ReviewStatus

cli = typer.Typer(
    name="review",
    help="Check documents before they are published",
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

    try:
        return asyncio.run(main())
    except PanglossReviewError as error:
        typer.secho(str(error), fg="red", err=True)
        raise typer.Exit(1) from error


def status_named(name: str) -> ReviewStatus:
    """The status of that name (`checked`, the earlier name of `published`, is still taken)"""
    try:
        return ReviewStatus(name)
    except ValueError:
        allowed = ", ".join(status.value for status in ReviewStatus)
        raise typer.BadParameter(f"{name!r} is not one of {allowed}") from None


@cli.command()
def queue(
    ctx: typer.Context,
    status: list[str] = typer.Option(
        [], "--status", "-s", help="unchecked (the default), errors_found or published"
    ),
    type: str | None = typer.Option(None, "--type", "-t", help="Only this class"),
    page: int = typer.Option(1, "--page"),
) -> None:
    """The documents to check, the oldest change first"""
    statuses = [status_named(name) for name in status]
    found = run_connected(ctx, lambda: service.queue(statuses or None, type, page))
    for item in found.results:
        typer.echo(
            f"{item.id}  {item.status:<12} {item.type:<20} {item.label or ''}"
            f"  ({item.open_comments} open comments)"
        )
    typer.echo(
        f"{found.count} in all"
        + (" (more on the next page)" if found.next_page else "")
    )


@cli.command()
def show(ctx: typer.Context, id: UUID) -> None:
    """The state of a document, and its open comments"""
    detail = run_connected(ctx, lambda: service.get_detail(id))
    typer.echo(
        f"{detail.type} {detail.label or ''}: {detail.status} (published: {detail.published})"
    )
    for c in detail.comments:
        about = f" [{c.target_label}]" if c.target_label else ""
        typer.echo(f"  {c.at:%Y-%m-%d} {c.username}{about}: {c.text}")


@cli.command("set")
def set_status(
    ctx: typer.Context,
    id: UUID,
    status: str = typer.Argument(..., help="unchecked, errors_found or published"),
    user: str = typer.Option(..., "--user", "-u", help="Who is checking it"),
    comment: str | None = typer.Option(None, "--comment", "-c"),
) -> None:
    """Set the status of a document: `published` publishes it"""
    wanted = status_named(status)
    state = run_connected(ctx, lambda: service.set_status(id, wanted, user, comment))
    typer.echo(
        f"{state.type} {state.label or ''}: {state.status} (published: {state.published})"
    )


@cli.command("index-uris")
def index_uris(ctx: typer.Context):
    """Make again the index of the URIs that parts of documents name (unreconciled mentions, identifications a
    toolchain suggested): after a bulk load, or for a project's own classes of suggestion in data from before the
    index. It is otherwise kept by the writes."""
    from pangloss_review import uris

    made = run_connected(ctx, uris.rebuild)
    typer.echo(f"{made} URIs of parts of documents are indexed")
