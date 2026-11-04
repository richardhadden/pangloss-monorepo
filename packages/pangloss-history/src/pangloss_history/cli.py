"""`pangloss history <command>`: look at the history of a head node (added to the `pangloss`
command for an installed app with a `cli.py`)."""

import asyncio
import json
from uuid import UUID

import typer

from pangloss_history import config
from pangloss_history.diff import diff
from pangloss_history.restore import restore
from pangloss_history.store import SqliteStore

cli = typer.Typer(
    name="history",
    help="Look at the history of documents and entities",
    no_args_is_help=True,
)


def open_store(ctx: typer.Context) -> SqliteStore:
    settings = getattr(ctx.obj, "settings", None)
    path = config.db_path(settings)
    if not path.exists():
        typer.secho(
            f"There is no history yet ({path} does not exist)", fg="red", err=True
        )
        raise typer.Exit(1)
    return SqliteStore(path)


def fetch(store: SqliteStore, id: UUID, version: int):
    record = store.get(id, version)
    if record is None:
        typer.secho(f"Version {version} of {id} was not recorded", fg="red", err=True)
        raise typer.Exit(1)
    return record


@cli.command("list")
def list_versions(ctx: typer.Context, id: UUID) -> None:
    """The versions that are recorded of a head node"""
    records = open_store(ctx).versions(id)
    if not records:
        typer.secho(f"There is no history of {id}", fg="red", err=True)
        raise typer.Exit(1)
    for r in records:
        restored = f" (from version {r.restored_from})" if r.restored_from else ""
        typer.echo(
            f"v{r.version}  {r.op:<8} {r.at:%Y-%m-%d %H:%M:%S}  {r.who}{restored}"
        )


@cli.command()
def show(ctx: typer.Context, id: UUID, version: int) -> None:
    """A version, as it was written"""
    record = fetch(open_store(ctx), id, version)
    typer.echo(json.dumps(record.data(), indent=2))


@cli.command("diff")
def show_difference(
    ctx: typer.Context,
    id: UUID,
    version: int,
    to: int | None = typer.Option(None, "--to"),
) -> None:
    """What changed from one version to another (to the latest, if --to is not given)"""
    store = open_store(ctx)
    if to is None:
        to = store.latest_version(id)
    if to is None:
        typer.secho(f"There is no history of {id}", fg="red", err=True)
        raise typer.Exit(1)
    changes = diff(fetch(store, id, version).data(), fetch(store, id, to).data())
    if not changes:
        typer.echo("No differences")
    for c in changes:
        if c.kind == "changed":
            typer.echo(f"~ {c.path}: {json.dumps(c.old)} -> {json.dumps(c.new)}")
        elif c.kind == "added":
            typer.echo(f"+ {c.path}: {json.dumps(c.new)}")
        else:
            typer.echo(f"- {c.path}: {json.dumps(c.old)}")


@cli.command("restore")
def restore_version(
    ctx: typer.Context,
    model: str,
    id: UUID,
    version: int,
    user: str = typer.Option(..., "--user", help="The user the new version is made by"),
    expected: int | None = typer.Option(
        None, "--expected-version", help="Only if the head node is at this version now"
    ),
) -> None:
    """Write an earlier version again, as a new version"""
    from pangloss_models import initialise
    from pangloss_models.exceptions import PanglossWriteError
    from pangloss_models.model_registry import ModelRegistry
    from pangloss_users import current_request_username

    project = ctx.obj
    store = open_store(ctx)
    backend = project.require_database()
    project.import_models()
    initialise()
    found = ModelRegistry.all_models().get(model)
    if found is None:
        typer.secho(f"There is no model '{model}'", fg="red", err=True)
        raise typer.Exit(1)

    async def main() -> int:
        await backend.connect()
        try:
            current_request_username.set(user)
            return await restore(store, found, id, version, expected)
        finally:
            await backend.disconnect()

    try:
        new_version = asyncio.run(main())
    except PanglossWriteError as error:
        typer.secho(f"Not restored: {error}", fg="red", err=True)
        raise typer.Exit(1) from error
    typer.echo(f"Version {version} is now version {new_version}")


@cli.command("baseline")
def record_baseline(
    ctx: typer.Context,
    model: list[str] = typer.Option(
        [],
        "--model",
        help="Only these models (as many as are given); all with history if none",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Count what would be recorded, and record nothing"
    ),
) -> None:
    """Record what each document and entity is now, if history has no record of its version (as for data written
    before pangloss_history was installed). Safe to run again: what has a record is left alone."""
    from pangloss_models import initialise
    from pangloss_models.model_registry import ModelRegistry

    from pangloss_history.baseline import make_baseline, models_with_history
    from pangloss_history.draft import installed_apps
    from pangloss_history.schema_position import schema_position

    project = ctx.obj
    settings = getattr(project, "settings", None)
    path = config.db_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    store = SqliteStore(path)
    backend = project.require_database()
    project.import_models()
    initialise()
    chosen = models_with_history()
    if model:
        unknown = [name for name in model if name not in ModelRegistry.all_models()]
        if unknown:
            typer.secho(f"There is no model {', '.join(unknown)}", fg="red", err=True)
            raise typer.Exit(1)
        chosen = [m for m in chosen if m.__name__ in model]

    async def main():
        await backend.connect()
        try:
            return await make_baseline(
                store, schema_position(installed_apps()), chosen, dry_run=dry_run
            )
        finally:
            await backend.disconnect()

    result = asyncio.run(main())
    for name, id, why in result.failed:
        typer.secho(f"{name} {id}: not recorded ({why})", fg="yellow", err=True)
    verb = "would be recorded" if dry_run else "recorded"
    typer.echo(
        f"{result.looked_at} looked at: {result.recorded} {verb}, "
        f"{result.up_to_date} had a record of their version already"
        + (
            f", {len(result.failed)} could not be read as their model"
            if result.failed
            else ""
        )
    )
