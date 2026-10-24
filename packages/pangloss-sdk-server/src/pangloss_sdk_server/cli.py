"""`pangloss sdk <command>`: build and look at the project's SDK (added to the `pangloss`
command for an installed app with a `cli.py`)."""

import typer

from pangloss_sdk_server import config, publish
from pangloss_sdk_server.builder import SdkBuildError, build_package

cli = typer.Typer(
    name="sdk", help="Build the SDK of this project", no_args_is_help=True
)


def load(ctx: typer.Context):
    """The project, with its models imported and initialised"""
    project = ctx.obj
    settings = project.require_settings()
    assert project.location is not None

    from pangloss_models import initialise
    from pangloss_models.exceptions import (
        PanglossImportError,
        PanglossInitialisationError,
    )

    try:
        project.import_models()
        initialise()
    except (PanglossInitialisationError, PanglossImportError) as error:
        typer.secho(f"Cannot initialise the models: {error}", fg="red", err=True)
        raise typer.Exit(1)
    return settings, project.location.root


def fail(error: SdkBuildError) -> None:
    typer.secho(f"Cannot build the SDK: {error}", fg="red", err=True)
    for problem in error.problems:
        typer.secho(f"  {problem}", fg="red", err=True)
    raise typer.Exit(1)


@cli.command()
def build(
    ctx: typer.Context,
    force: bool = typer.Option(
        False, "--force", help="Build again even if nothing changed"
    ),
) -> None:
    """Build the SDK: the models of the apps, with stubs, as a package. It is checked on
    a clean client before it replaces the last build."""
    settings, root = load(ctx)
    try:
        built = publish.build(root, settings, force=force)
    except SdkBuildError as error:
        fail(error)
    manifest = built.manifest
    state = "built" if built.changed else "unchanged"
    typer.secho(
        f"{manifest['distribution']} {manifest['version']} {state} "
        f"(fingerprint {manifest['fingerprint'][:12]})",
        fg="green",
    )
    typer.echo(f"  apps: {', '.join(manifest['apps'])}")
    typer.echo(f"  modules: {len(manifest['modules'])}")
    typer.echo(f"  in {built.directory}")
    for note in built.notes:
        typer.secho(f"  note: {note}", fg="yellow")


@cli.command()
def status(ctx: typer.Context) -> None:
    """What is built, and whether the models have changed since"""
    settings, root = load(ctx)
    output = config.output_directory(root, settings)
    state = publish.read_state(output)
    if not state:
        typer.echo("The SDK has not been built (pangloss sdk build)")
        raise typer.Exit(1)
    try:
        package = publish.current_package(root, settings, output)
    except SdkBuildError as error:
        fail(error)
    typer.echo(
        f"Built {state['built_at']}: version 0.{state['number']}, "
        f"fingerprint {state['fingerprint'][:12]}"
    )
    if state["schema_position"]:
        typer.echo(f"  schema position: {state['schema_position']}")
    if publish.needs_build(package, output):
        typer.secho("  The models have changed since: pangloss sdk build", fg="yellow")
        raise typer.Exit(2)
    typer.secho("  Up to date with the models", fg="green")


@cli.command()
def show(
    ctx: typer.Context,
    diff: bool = typer.Option(False, "--diff", help="The change since the last build"),
) -> None:
    """The files of the SDK as the models are now; with --diff, what differs from the last build"""
    settings, root = load(ctx)
    output = config.output_directory(root, settings)
    try:
        package = build_package(
            root, settings, publish.read_state(output).get("number", 0) + 1
        )
    except SdkBuildError as error:
        fail(error)
    if diff:
        lines = publish.diff_against_built(package, output)
        typer.echo("\n".join(lines) if lines else "No change since the last build")
        return
    for path, content in sorted(package.files.items()):
        typer.echo(f"{len(content):>8}  {path}")
