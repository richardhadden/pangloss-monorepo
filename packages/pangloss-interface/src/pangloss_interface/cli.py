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

from pangloss_interface.modules import (
    MODULE_DIRECTORY,
    InterfaceModule,
    ManifestError,
    app_directory,
    discover,
    problems,
    read_manifests,
)
from pangloss_interface.paths import APP_PATH, JS_ROOT
from pangloss_interface.runtime import (
    InterfaceRuntimeError,
    Runtime,
    find_runtime,
    run,
)
from pangloss_interface.scaffold import module_files
from pangloss_interface.translations_cli import translations, write_translations
from pangloss_interface.typescript import models_module
from pangloss_interface.workspace import (
    TRANSLATIONS_PATH,
    export_project_models,
    is_source_checkout,
    linked_translations_path,
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


def modules_of(project: Any) -> list[InterfaceModule]:
    """The interface modules of the project's installed apps"""
    return discover(project.require_settings().INSTALLED_APPS)


def prepare_workspace(ctx: typer.Context) -> Path:
    """Copy the interface into the project, with its models and the interface modules of its
    installed apps; returns the directory"""
    project = project_of(ctx)
    exported = export_or_exit(project)
    prepared = prepare(project.location.root, exported, modules_of(project))
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


def module_problems(ctx: typer.Context, runtime: Runtime, directory: Path) -> list[str]:
    """What the models and the modules' manifests say that does not fit (the working directory is prepared)"""
    project = project_of(ctx)
    modules = modules_of(project)
    exported = export_or_exit(project)
    try:
        manifests = read_manifests(runtime, directory, modules)
    except ManifestError as error:
        return [f"The manifests of the interface modules could not be read: {error}"]
    return problems(modules, manifests, exported)


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
        linked = prepare_linked(project.location.root, exported, modules_of(project))
        models = linked.models
        write_translations(
            project, exported, linked_translations_path(project.location.root)
        )
        typer.echo(f"Running from {JS_ROOT}\nModels: {models}")
        for root in linked.module_roots:
            typer.echo(f"Module (in place): {root}")
        ensure_installed(found, JS_ROOT)
        directory, environment = (
            APP_PATH,
            {
                "PANGLOSS_MODELS_MODULE": str(models),
                "PANGLOSS_MODULES_MODULE": str(linked.modules),
                "PANGLOSS_SOURCES_CSS": str(linked.sources),
                "PANGLOSS_MODULE_ROOTS": ":".join(str(r) for r in linked.module_roots),
            },
        )
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
    wrong = module_problems(ctx, found, directory)
    for message in wrong:
        typer.secho(message, fg="red", err=True)
    if wrong:
        raise typer.Exit(1)
    typer.secho("The interface modules are consistent with the models", fg="green")


@cli.command("new-module")
def new_module(
    ctx: typer.Context,
    app: str = typer.Argument(..., help="An installed app (in INSTALLED_APPS)"),
    force: bool = typer.Option(
        False, "--force", help="Write the files that are missing, if the module exists"
    ),
    example: bool = typer.Option(
        True, "--example/--no-example", help="Include a card as an example"
    ),
) -> None:
    """Make the interface module of an app: a Solid library for the pages and cards of its models"""
    project = project_of(ctx)
    if app not in project.require_settings().INSTALLED_APPS:
        fail(f"{app} is not one of the INSTALLED_APPS")
    directory = app_directory(app)
    if directory is None:
        fail(f"Cannot find the package of {app}")
        raise typer.Exit(1)
    root = directory / MODULE_DIRECTORY
    if root.exists() and not force:
        fail(f"{root} exists: use --force to write the files that are missing")
    for name, text in module_files(app, example).items():
        path = root / name
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        typer.echo(f"  wrote {path}")
    typer.echo(
        "\nNext:\n"
        f'  1. name a component in a model: InterfaceMeta(view_card="{app}:ExampleCard")\n'
        "  2. pangloss interface check\n"
        "  3. pangloss interface dev\n"
        "A wheel of the app has to include the folder: see the interface modules guide."
    )


@cli.command("modules")
def list_modules(ctx: typer.Context, runtime: str | None = RuntimeOption) -> None:
    """List the interface modules of the installed apps, what each provides, and the problems"""
    project = project_of(ctx)
    modules = modules_of(project)
    if not modules:
        typer.echo("No installed app has an interface module (pangloss interface new-module APP)")
        return
    found = runtime_or_exit(runtime)
    directory = prepare_workspace(ctx)
    ensure_installed(found, directory)
    try:
        manifests = read_manifests(found, directory, modules)
    except ManifestError as error:
        fail(f"The manifests could not be read: {error}")
        raise
    for module in modules:
        manifest = manifests[module.app]
        typer.echo(f"{module.app}  ({module.root})")
        typer.echo(f"    components: {', '.join(manifest.components) or '-'}")
        typer.echo(f"    routes:     {', '.join(r['path'] for r in manifest.routes) or '-'}")
        if manifest.requires:
            typer.echo(f"    requires:   {', '.join(manifest.requires)}")
    wrong = problems(modules, manifests, export_or_exit(project))
    for message in wrong:
        typer.secho(f"problem: {message}", fg="red", err=True)
    if wrong:
        raise typer.Exit(1)
