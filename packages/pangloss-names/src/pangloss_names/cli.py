"""`pangloss names <command>`: the name part of similarity.

pangloss names search TEXT [--type NAME ...] [--profile NAME] [-k 10]   the items nearest a name
"""

import typer

cli = typer.Typer(
    name="names",
    help="Similarity by name: the items nearest a name",
    no_args_is_help=True,
)


@cli.callback()
def names() -> None:
    """Similarity by name: the items nearest a name"""
    # (a group of one command is still a group, `pangloss names search`, and not the command itself)


@cli.command()
def search(
    ctx: typer.Context,
    text: str = typer.Argument(..., help="The name to search by"),
    types: list[str] | None = typer.Option(
        None,
        "--type",
        help="Only items of this class of documents or entities (or of a class below it); may be given more than "
        "once",
    ),
    profile: str | None = typer.Option(
        None,
        "--profile",
        help="The profile to search by (it must weigh the name part); the first that does if not given",
    ),
    k: int = typer.Option(10, "-k", min=1, help="How many items"),
) -> None:
    """The items nearest a name, by a profile that weighs the name part: a line for each, nearest first, with its
    score, class, label and id. Unpublished documents are shown (the command line is the project's owner)"""
    from pangloss_vectors.cli import run_connected
    from pangloss_vectors.store import RebuildDue
    from pangloss_vectors.views import reference_views

    from pangloss_names.by_name import search as searching

    async def found():
        nearest = await searching(
            text, types=types or None, profile=profile, k=k, see_unpublished=True
        )
        views = (
            await reference_views([hit.id for hit in nearest.hits], True)
            if nearest.status == "ok"
            else {}
        )
        return nearest, views

    try:
        nearest, views = run_connected(ctx, found)
    except RebuildDue as error:
        typer.secho(str(error), fg="red", err=True)
        raise typer.Exit(1) from None
    except ValueError as error:
        # (no profile weighs the name part, a class that is not one, a text with no name in it)
        typer.secho(str(error), fg="red", err=True)
        raise typer.Exit(2) from None
    if nearest.status == "pending":
        typer.secho(
            "The profile has not been built: run `pangloss vectors rebuild`",
            fg="yellow",
            err=True,
        )
        raise typer.Exit(1)
    if nearest.status == "rebuild_due":
        typer.secho(
            "The profile's vectors in use are not of the dimension its parts make today: run "
            "`pangloss vectors rebuild`",
            fg="yellow",
            err=True,
        )
        raise typer.Exit(1)
    if not nearest.hits:
        typer.echo("nothing found")
    for hit in nearest.hits:
        label = (views.get(hit.id) or {}).get("label", "")
        typer.echo(f"{hit.score:.4f}  {hit.type}  {label}  {hit.id}")
