"""The `pangloss` command.

Core commands are here; an installed app (`INSTALLED_APPS`) that has a `cli.py` with a
Typer object named `cli` adds its commands as `pangloss <name> <command>`, where
`<name>` is the name of that Typer object (or the app's, without a `pangloss_`
prefix). For example `pangloss_memgraph` adds `pangloss memgraph info`.
"""

from collections.abc import Mapping, Sequence
from pathlib import Path

import typer

from pangloss_cli.migrations import (
    backups,
    check_data_command,
    cleanmigrations,
    makemigrations,
    migrate,
    restore,
    showmigrations,
    squashmigrations,
)
from pangloss_cli.project import (
    NO_SETTINGS_MESSAGE,
    Project,
    app_command_group,
    fail,
    group_name,
    load_project,
)
from pangloss_cli.scaffold import (
    ScaffoldError,
    add_to_installed_apps,
    plan_app,
    plan_project,
    settings_file,
)
from pangloss_cli.server import serve
from pangloss_cli.users import run_with_database, users_cli


def setup_database(ctx: typer.Context) -> None:
    """Make what the database needs: indexes, constraints and so on (safe to repeat)"""
    project: Project = ctx.obj
    backend = project.require_database()

    from pangloss_models import initialise
    from pangloss_models.exceptions import PanglossInitialisationError

    try:
        project.import_models()
        initialise()
    except PanglossInitialisationError as error:
        fail(f"Cannot initialise the models: {error}")

    from pangloss_models.meta_kit.migrations.files import graph_of

    if graph_of(list(project.require_settings().INSTALLED_APPS)).migrations:
        typer.secho(
            "This project has migrations: `pangloss migrate` makes and changes the database "
            "(this makes the enums of the models as they are now, which can get ahead of the "
            "migrations). Use it for a project without migrations.",
            fg="yellow",
            err=True,
        )

    async def run() -> list[str]:
        return await backend.setup_database()

    for line in run_with_database(project, run):
        typer.echo(line)
    typer.secho("Database is set up", fg="green")


def make_stubs(
    ctx: typer.Context,
    force: bool = typer.Option(
        False,
        "--force",
        help="Write over a .pyi file that was not made by this command",
    ),
) -> None:
    """Write type stubs (.pyi) for the modules that declare models, so that an editor
    can complete `Person.Create(...)`, `Person.HeadView` and the like

    The models of the installed apps (and the modules they import models from, if they
    are in the project) are initialised, and a stub is written beside each module that
    declares models. Run it again when the models change."""
    project: Project = ctx.obj
    settings = project.require_settings()
    assert project.location is not None

    from pangloss_models import initialise
    from pangloss_models.exceptions import (
        PanglossImportError,
        PanglossInitialisationError,
    )
    from pangloss_models.typestubs import write_stubs

    try:
        project.import_models()
        initialise()
    except (PanglossInitialisationError, PanglossImportError) as error:
        fail(f"Cannot initialise the models: {error}")

    root = project.location.root
    written, skipped = write_stubs(root, force=force)
    for path in written:
        typer.echo(f"  wrote {path.relative_to(root)}")
    for path in skipped:
        typer.secho(
            f"  skipped {path.relative_to(root)}: it was not made by this command "
            "(use --force to write over it)",
            fg="yellow",
        )
    if not written and not skipped:
        typer.echo(
            f"No models found in {', '.join(settings.INSTALLED_APPS) or 'the project'}"
        )
    else:
        typer.secho(f"Wrote {len(written)} stub file(s)", fg="green")


def new_project(
    name: str = typer.Argument(..., help="The name of the project (a Python name)"),
) -> None:
    """Make a new project in the current directory: its settings, and pyproject.toml"""
    directory = Path.cwd()
    try:
        plan = plan_project(name, directory)
    except ScaffoldError as error:
        fail(str(error))
        return
    plan.apply()

    typer.secho(f"Created project '{name}'", fg="green")
    for path in plan.create:
        typer.echo(f"  created {path.relative_to(directory)}")
    for path in plan.append:
        typer.echo(f"  added to {path.relative_to(directory)}")
    typer.echo(
        f"\nNext: check the database settings in {name}/settings.py, add the Pangloss "
        "packages to the dependencies in pyproject.toml, and make an app with\n"
        "  pangloss new-app <name>"
    )


def new_app(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="The name of the app (a Python name)"),
) -> None:
    """Make a new app (for your models) in the project, and add it to INSTALLED_APPS"""
    project: Project = ctx.obj
    if project.location is None:
        fail(project.settings_error or NO_SETTINGS_MESSAGE)
        return
    root = project.location.root

    try:
        plan = plan_app(name, root)
    except ScaffoldError as error:
        fail(str(error))
        return

    # (the settings are edited only if that can be done reliably)
    settings_path = settings_file(project.location.module, root)
    edited: str | None = None
    if settings_path is not None:
        edited = add_to_installed_apps(settings_path.read_text(), name)

    plan.apply()
    typer.secho(f"Created app '{name}'", fg="green")
    for path in plan.create:
        typer.echo(f"  created {path.relative_to(root)}")

    if settings_path is not None and edited is not None:
        settings_path.write_text(edited)
        typer.echo(
            f'  added "{name}" to INSTALLED_APPS in {settings_path.relative_to(root)}'
        )
    else:
        typer.secho(
            f'\nAdd "{name}" to INSTALLED_APPS in your settings yourself (it could not '
            "be done automatically).",
            fg="yellow",
        )
    typer.echo(f"\nNow declare your models in {name}/models.py")


def run(
    ctx: typer.Context,
    host: str = typer.Option("127.0.0.1", "--host", help="The address to listen on"),
    port: int = typer.Option(8000, "--port", help="The port to listen on"),
) -> None:
    """Start the API server"""
    serve(ctx.obj, host, port, reload=False)


def dev(
    ctx: typer.Context,
    host: str = typer.Option("127.0.0.1", "--host", help="The address to listen on"),
    port: int = typer.Option(8000, "--port", help="The port to listen on"),
) -> None:
    """Start the API server, restarting it when the code or settings change"""
    serve(ctx.obj, host, port, reload=True)


def add_app_commands(app: typer.Typer, project: Project) -> None:
    if project.settings is None:
        return

    taken = {
        command.name or getattr(command.callback, "__name__", "").replace("_", "-")
        for command in app.registered_commands
        if command.callback
    } | {group.name for group in app.registered_groups}

    for installed_app in project.settings.INSTALLED_APPS:
        try:
            group = app_command_group(installed_app)
            if group is None:
                continue
            name = group_name(installed_app, group)
            if name in taken:
                raise ValueError(f"'{name}' is already a command")
        except Exception as error:
            project.app_errors.append((installed_app, str(error)))
            typer.secho(
                f"Warning: no commands from '{installed_app}': {error}",
                fg="yellow",
                err=True,
            )
            continue
        taken.add(name)
        app.add_typer(group, name=name)


def build_app(
    argv: Sequence[str] | None = None,
    environment: Mapping[str, str] | None = None,
    directory: Path | None = None,
) -> typer.Typer:
    project = load_project(argv, environment, directory)

    app = typer.Typer(
        name="pangloss",
        help="Pangloss",
        add_completion=False,
        no_args_is_help=True,
    )

    @app.callback()
    def callback(
        ctx: typer.Context,
        settings: str | None = typer.Option(
            None,
            "--settings",
            metavar="MODULE",
            help="The settings module of the project. Otherwise "
            "PANGLOSS_SETTINGS, or the 'settings' of 'tool.pangloss' in pyproject.toml",
        ),
    ) -> None:
        ctx.obj = project

    app.command("setup-database")(setup_database)
    app.command("make-stubs")(make_stubs)
    app.command("makemigrations")(makemigrations)
    app.command("migrate")(migrate)
    app.command("showmigrations")(showmigrations)
    app.command("squashmigrations")(squashmigrations)
    app.command("cleanmigrations")(cleanmigrations)
    app.command("backups")(backups)
    app.command("restore")(restore)
    app.command("check-data")(check_data_command)
    app.command("new-project")(new_project)
    app.command("new-app")(new_app)
    app.command("run")(run)
    app.command("dev")(dev)
    app.add_typer(users_cli, name="users")
    add_app_commands(app, project)
    return app


def main() -> None:
    build_app()()


if __name__ == "__main__":
    main()
