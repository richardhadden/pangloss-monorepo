"""The `pangloss` command.

Core commands are here; an installed app (`INSTALLED_APPS`) that has a `cli.py` with a
Typer object named `cli` adds its commands as `pangloss <name> <command>`, where
`<name>` is the name of that Typer object (or the app's, without a `pangloss_`
prefix). For example `pangloss_memgraph` adds `pangloss memgraph info`.
"""

from collections.abc import Mapping, Sequence
from pathlib import Path

import typer

from pangloss_cli.project import (
    Project,
    app_command_group,
    fail,
    group_name,
    load_project,
)
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

    async def run() -> list[str]:
        return await backend.setup_database()

    for line in run_with_database(project, run):
        typer.echo(line)
    typer.secho("Database is set up", fg="green")


def add_app_commands(app: typer.Typer, project: Project) -> None:
    if project.settings is None:
        return

    taken = {
        command.name or command.callback.__name__.replace("_", "-")
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
    app.add_typer(users_cli, name="users")
    add_app_commands(app, project)
    return app


def main() -> None:
    build_app()()


if __name__ == "__main__":
    main()
