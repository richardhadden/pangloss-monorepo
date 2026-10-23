"""`pangloss history <command>`: look at the history of a head node (added to the `pangloss`
command for an installed app with a `cli.py`)."""

import json
from uuid import UUID

import typer

from pangloss_history import config
from pangloss_history.diff import diff
from pangloss_history.store import SqliteStore

cli = typer.Typer(name="history", help="Look at the history of documents and entities", no_args_is_help=True)


def open_store(ctx: typer.Context) -> SqliteStore:
    settings = getattr(ctx.obj, "settings", None)
    path = config.db_path(settings)
    if not path.exists():
        typer.secho(f"There is no history yet ({path} does not exist)", fg="red", err=True)
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
        typer.echo(f"v{r.version}  {r.op:<8} {r.at:%Y-%m-%d %H:%M:%S}  {r.who}{restored}")


@cli.command()
def show(ctx: typer.Context, id: UUID, version: int) -> None:
    """A version, as it was written"""
    record = fetch(open_store(ctx), id, version)
    typer.echo(json.dumps(record.data(), indent=2))


@cli.command("diff")
def show_difference(
    ctx: typer.Context, id: UUID, version: int, to: int | None = typer.Option(None, "--to")
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
