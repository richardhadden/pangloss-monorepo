"""`pangloss typology <command>`: load a vocabulary from a file, write one out, and look at one (added to the `pangloss`
command for an installed app with a `cli.py`)."""

import asyncio
import json
from collections.abc import Awaitable, Callable
from pathlib import Path

import typer

cli = typer.Typer(
    name="typology",
    help="The vocabularies of types",
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


def typology_named(ctx: typer.Context, name: str):
    from pangloss_typology.typology import Typology

    ctx.obj.import_models()  # (a typology exists once the models that declare it are imported)
    found = Typology.registry.get(name)
    if found is None:
        known = ", ".join(sorted(Typology.registry)) or "(none)"
        typer.secho(f"No typology {name}. Known: {known}", fg="red", err=True)
        raise typer.Exit(2)
    return found


def read_entries(path: Path) -> list:
    text = path.read_text()
    try:  # (the interface's reader takes comments out of a .jsonc file)
        from pangloss_interface.i18n.jsonc import strip_comments

        text = strip_comments(text)
    except ImportError:
        pass
    data = json.loads(text)
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        raise typer.BadParameter("The file must hold a list of types")
    return data


@cli.command()
def load(
    ctx: typer.Context,
    name: str = typer.Argument(
        help="The typology, by the name of its entity: RoleType"
    ),
    file: Path = typer.Argument(
        exists=True, dir_okay=False, help="A nested JSON(C) file"
    ),
    user: str = typer.Option(
        ..., "--user", help="The user the types are made as (they must exist)"
    ),
) -> None:
    """Make the types of a file, nested as the hierarchy is: `[{"label": "Official", "label_de": "Beamter", "children": [...]}]`.
    One that is already there (the same label under the same supertype) is left alone, so the file can be loaded again"""
    from pangloss_typology import service

    typology = typology_named(ctx, name)
    entries = read_entries(file)

    async def work():
        from pangloss_memgraph.cli import user_exists
        from pangloss_users import current_request_username

        if not await user_exists(user):
            raise service.Refused(
                f"There is no user called {user!r}: `pangloss users create` makes one"
            )
        current_request_username.set(user)
        return await service.load(typology, entries)

    try:
        report = run_connected(ctx, work)
    except service.Refused as error:
        typer.secho(str(error), fg="red", err=True)
        raise typer.Exit(1) from error
    typer.echo(f"{report.created} made, {report.existing} already there")


@cli.command()
def dump(
    ctx: typer.Context,
    name: str = typer.Argument(
        help="The typology, by the name of its entity: RoleType"
    ),
    file: Path | None = typer.Option(
        None, "--to", help="Write to this file (default: show it)"
    ),
) -> None:
    """Write the vocabulary in the form `load` reads"""
    from pangloss_typology import service

    typology = typology_named(ctx, name)
    text = json.dumps(
        run_connected(ctx, lambda: service.dump(typology)), indent=2, ensure_ascii=False
    )
    if file is None:
        typer.echo(text)
    else:
        file.write_text(text + "\n")
        typer.echo(f"Written to {file}")


@cli.command()
def tree(
    ctx: typer.Context,
    name: str = typer.Argument(
        help="The typology, by the name of its entity: RoleType"
    ),
) -> None:
    """Show the hierarchy"""
    from pangloss_typology import service

    typology = typology_named(ctx, name)

    def show(nodes: list, depth: int = 0) -> None:
        for node in nodes:
            typer.echo(f"{'  ' * depth}{node['label']}")
            show(node["children"], depth + 1)

    show(run_connected(ctx, lambda: service.tree_of(typology)))
