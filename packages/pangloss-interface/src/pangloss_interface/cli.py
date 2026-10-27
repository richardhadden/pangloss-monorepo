"""`pangloss interface <command>`: the commands that wrap the JavaScript tools.

(`pangloss-cli` adds this to the `pangloss` command for an installed app that has a
`cli.py` with a Typer object named `cli`, and gives each command the loaded project as
`ctx.obj`.)

The interface is built in the project's working directory, `.pangloss/interface`: each
command that needs it copies the JavaScript of the package there, and writes the
definitions of the project's models as a TypeScript module that the interface imports.
"""

import json
from pathlib import Path
from typing import Any

import typer

from pangloss_interface.paths import APP_PATH, JS_ROOT
from pangloss_interface.runtime import (
    InterfaceRuntimeError,
    Runtime,
    find_runtime,
    run,
)
from pangloss_interface.translations_cli import translations, write_translations
from pangloss_interface.typescript import models_module
from pangloss_interface.workspace import (
    TRANSLATIONS_PATH,
    linked_translations_path,
    export_project_models,
    is_source_checkout,
    prepare,
    prepare_linked,
    working_directory,
)

cli = typer.Typer(name="interface", help="The web interface", no_args_is_help=True)
cli.add_typer(translations)

RuntimeOption = typer.Option(
    None,
    "--runtime",
    help="'node' (the default) or 'bun'. Otherwise PANGLOSS_INTERFACE_RUNTIME",
)
ApiUrlOption = typer.Option(
    "http://127.0.0.1:8000", "--api-url", help="Where the Pangloss API is"
)

NO_PROJECT = (
    "No project found. Run this where there is a pyproject.toml with "
    "[tool.pangloss], or give --settings"
)


def fail(message: str, code: int = 1):
    typer.secho(message, fg="red", err=True)
    raise typer.Exit(code)


def runtime_or_exit(requested: str | None) -> Runtime:
    try:
        return find_runtime(requested)
    except InterfaceRuntimeError as error:
        fail(str(error))
        raise  # (for the checker: fail does not return)


def run_or_exit(
    command: list[str], cwd: Path, environment: dict[str, str] | None = None
):
    code = run(command, cwd, environment)
    if code != 0:
        raise typer.Exit(code)


def project_of(ctx: typer.Context) -> Any:
    """The project loaded by `pangloss-cli` (with its settings), or exit"""
    project = ctx.obj
    if project is None or getattr(project, "location", None) is None:
        fail(getattr(project, "settings_error", None) or NO_PROJECT)
    project.require_settings()
    return project


def export_or_exit(project: Any) -> dict[str, Any]:
    from pangloss_models.exceptions import (
        PanglossImportError,
        PanglossInitialisationError,
    )

    try:
        return export_project_models(project)
    except (PanglossInitialisationError, PanglossImportError) as error:
        fail(f"Cannot initialise the models: {error}")
        raise


def prepare_workspace(ctx: typer.Context) -> Path:
    """Copy the interface into the project, with its models; returns the directory"""
    project = project_of(ctx)
    exported = export_or_exit(project)
    prepared = prepare(project.location.root, exported)
    for name in prepared.written:
        typer.echo(
            f"  wrote {(prepared.directory / name).relative_to(project.location.root)}"
        )
    for name in prepared.removed:
        typer.echo(f"  removed {name}")
    write_translations(project, exported, prepared.directory / TRANSLATIONS_PATH)
    return prepared.directory


def installed(directory: Path) -> bool:
    return (directory / "node_modules").is_dir()


def ensure_installed(runtime: Runtime, directory: Path) -> None:
    if not installed(directory):
        typer.echo("Installing the packages of the interface")
        run_or_exit(runtime.install(), directory)


def built_server(directory: Path) -> Path:
    return directory / "interface-app" / "dist" / "server" / "node.js"


@cli.command()
def info(ctx: typer.Context, runtime: str | None = RuntimeOption) -> None:
    """Show where the interface is built, and what will run it"""
    project = project_of(ctx)
    directory = working_directory(project.location.root)
    typer.echo(f"Directory:  {directory}")
    typer.echo(
        f"Prepared:   {'yes' if directory.is_dir() else 'no (pangloss interface build)'}"
    )
    typer.echo(f"Installed:  {'yes' if installed(directory) else 'no'}")
    typer.echo(f"Built:      {'yes' if built_server(directory).is_file() else 'no'}")
    found = runtime_or_exit(runtime)
    typer.echo(f"Runtime:    {found.name} ({found.executable})")


@cli.command("export-models")
def export_models(
    ctx: typer.Context,
    format: str = typer.Option(
        "ts", "--format", help="'ts' (the module the interface imports) or 'json'"
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="A file to write (otherwise it is printed)"
    ),
) -> None:
    """Export the definitions of the project's models, as the interface reads them"""
    if format not in ("ts", "json"):
        fail("--format is 'ts' or 'json'")
    exported = export_or_exit(project_of(ctx))
    text = (
        models_module(exported)
        if format == "ts"
        else json.dumps(exported, indent=2) + "\n"
    )
    if output is None:
        typer.echo(text, nl=False)
    else:
        output.write_text(text)
        typer.echo(f"Wrote {output}")


@cli.command()
def install(ctx: typer.Context, runtime: str | None = RuntimeOption) -> None:
    """Prepare the interface in the project, and install its packages"""
    found = runtime_or_exit(runtime)
    directory = prepare_workspace(ctx)
    run_or_exit(found.install(), directory)


@cli.command()
def dev(
    ctx: typer.Context,
    runtime: str | None = RuntimeOption,
    api_url: str = ApiUrlOption,
    port: int = typer.Option(3000, "--port", help="The port to listen on"),
    link: bool = typer.Option(
        False,
        "--link",
        help="Run from the source of the package itself, not a copy in the project, so "
        "that changes to interface-core and interface-app show at once. For working on "
        "the interface (needs a checkout of the source)",
    ),
) -> None:
    """Start the interface's development server (it passes /api on to the API)

    The models are exported when it starts: restart it after changing them."""
    found = runtime_or_exit(runtime)
    if link:
        if not is_source_checkout():
            fail("--link needs the source of pangloss-interface (an editable install)")
        project = project_of(ctx)
        exported = export_or_exit(project)
        models = prepare_linked(project.location.root, exported)
        write_translations(
            project, exported, linked_translations_path(project.location.root)
        )
        typer.echo(f"Running from {JS_ROOT}\nModels: {models}")
        ensure_installed(found, JS_ROOT)
        directory, environment = APP_PATH, {"PANGLOSS_MODELS_MODULE": str(models)}
    else:
        directory = prepare_workspace(ctx)
        ensure_installed(found, directory)
        directory, environment = directory / "interface-app", {}
    run_or_exit(
        found.script("dev", "--port", str(port)),
        directory,
        {"PANGLOSS_API_URL": api_url, **environment},
    )


@cli.command()
def build(ctx: typer.Context, runtime: str | None = RuntimeOption) -> None:
    """Build the interface for production, in .pangloss/interface

    The definitions of the project's models are exported first."""
    found = runtime_or_exit(runtime)
    directory = prepare_workspace(ctx)
    ensure_installed(found, directory)
    run_or_exit(found.script("build"), directory / "interface-app")
    typer.secho(f"Built in {directory / 'interface-app' / 'dist'}", fg="green")


@cli.command()
def serve(
    ctx: typer.Context,
    runtime: str | None = RuntimeOption,
    host: str = typer.Option("127.0.0.1", "--host", help="The address to listen on"),
    port: int = typer.Option(3000, "--port", help="The port to listen on"),
) -> None:
    """Run the built interface (server-side rendered)"""
    directory = working_directory(project_of(ctx).location.root)
    entry = built_server(directory)
    if not entry.is_file():
        fail("The interface is not built: run 'pangloss interface build'")
    found = runtime_or_exit(runtime)
    run_or_exit(
        found.run_file(entry),
        directory / "interface-app",
        {"HOST": host, "PORT": str(port)},
    )


@cli.command()
def check(ctx: typer.Context, runtime: str | None = RuntimeOption) -> None:
    """Type-check the interface with the project's models, and check the layers"""
    found = runtime_or_exit(runtime)
    directory = prepare_workspace(ctx)
    ensure_installed(found, directory)
    run_or_exit(found.script("typecheck"), directory)
    run_or_exit(found.script("check:layers"), directory)
