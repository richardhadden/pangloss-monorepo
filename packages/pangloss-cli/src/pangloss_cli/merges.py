"""`pangloss merge`, `pangloss unmerge` and `pangloss merges`: merging two entities that are one, and undoing a merge,
from the command line (implementation_docs/entity-identity.md). For a clean-up from a list of pairs, and for the merges
that are too large to be made through the API by anyone but an admin."""

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any
from uuid import UUID

import typer

from pangloss_cli.project import fail

cli = typer.Typer(name="merges", no_args_is_help=True)


def run_connected[T](
    ctx: typer.Context, function: Callable[[], Awaitable[T]], user: str | None = None
) -> T:
    """Import and initialise the models, then run a coroutine function with the database connected, as the user"""
    from pangloss_models import initialise
    from pangloss_models.exceptions import MODEL_ERRORS
    from pangloss_users import current_request_username

    project = ctx.obj
    backend = project.require_database()
    try:
        project.import_models()
        initialise()
    except MODEL_ERRORS as error:
        fail(f"Cannot initialise the models: {error}")

    async def main() -> T:
        await backend.connect()
        try:
            if user is not None:
                current_request_username.set(user)
            return await function()
        finally:
            await settle()
            await backend.disconnect()

    return asyncio.run(main())


async def settle() -> None:
    """Wait for what a merge left running in this loop (its later look for stray references), if the storage has it"""
    from pangloss_core import storage_of

    waiting = getattr(storage_of().operations, "settle_second_passes", None)
    if waiting is not None:
        await waiting()


def entity_model(name: str) -> Any:
    from pangloss_models import Entity, ModelRegistry

    model = ModelRegistry.all_models().get(name)
    if not (isinstance(model, type) and issubclass(model, Entity)):
        fail(f"There is no entity class '{name}'")
    return model


def read_pairs(path: Path) -> list[tuple[UUID, UUID]]:
    """The pairs of a file: a line each, the id of the entity that stays and then the id of the one it absorbs, with
    a space, a tab or a comma between. Blank lines and lines that start with `#` are left out"""
    pairs = []
    for number, line in enumerate(path.read_text().splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.replace(",", " ").split()
        try:
            survivor, absorbed = (UUID(part) for part in parts)
        except ValueError:
            fail(
                f"{path}, line {number}: expected two ids (the survivor, the absorbed)"
            )
        pairs.append((survivor, absorbed))
    return pairs


def describe_preview(preview: Any) -> list[str]:
    if not preview.possible:
        return ["cannot be merged: " + "; ".join(preview.refused)]
    lines = [
        f"would write {preview.heads} documents and entities"
        + (f" (over the limit of {preview.limit}: --large)" if preview.large else "")
    ]
    if preview.collapsed:
        lines.append(
            f"{len(preview.collapsed)} name both in one relation, and would name the survivor once"
        )
    if preview.both:
        lines.append(f"{len(preview.both)} name both in different relations")
    if preview.kept:
        lines.append(f"{preview.kept} references stay on the absorbed entity")
    return lines


def describe_result(result: Any) -> list[str]:
    merge = result.merge
    lines = [
        f"merge {merge.id}: {merge.moved} references moved in {merge.heads} documents and entities"
        + (f", {merge.dropped} dropped as duplicates" if merge.dropped else "")
    ]
    for head in result.collapsed:
        lines.append(
            f"  names the survivor once where it named both: {head.type} {head.id} {head.label or ''}".rstrip()
        )
    for head in result.both:
        lines.append(
            f"  names the survivor in two relations: {head.type} {head.id} {head.label or ''}".rstrip()
        )
    if result.kept:
        lines.append(f"  {result.kept} references stay on the absorbed entity")
    return lines


@cli.command("merge")
def merge_command(
    ctx: typer.Context,
    type: str = typer.Argument(..., help="The class of the entities: Person"),
    survivor: UUID | None = typer.Argument(None, help="The entity that stays"),
    absorbed: UUID | None = typer.Argument(None, help="The entity merged into it"),
    user: str = typer.Option(..., "--user", help="The user the merge is made by"),
    pairs: Path | None = typer.Option(
        None,
        "--pairs",
        exists=True,
        dir_okay=False,
        help="A file of pairs instead: a line each, the survivor's id and then the absorbed entity's",
    ),
    as_class: str | None = typer.Option(
        None,
        "--as",
        help="The class the survivor takes, when the two differ (the narrower, if not given)",
    ),
    large: bool = typer.Option(
        False,
        "--large",
        help="Make a merge that writes more documents than MERGE_LIMIT, in batches (and go on with one that stopped)",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Say what each merge would do, and write nothing"
    ),
) -> None:
    """Merge one entity into another: what refers to the second refers to the first

    The survivor has its own fields, the absorbed entity's where it has none, and both of every list. The absorbed
    entity is kept, marked as merged: `pangloss unmerge` brings it back. With --pairs, the pairs are merged one after
    the other, and the first that cannot be merged stops the rest (those before it stay merged)."""
    from pangloss_models import PanglossWriteError

    if pairs is not None and (survivor is not None or absorbed is not None):
        fail("Give either two ids or --pairs, not both")
    if pairs is None and (survivor is None or absorbed is None):
        fail("Give the ids of the survivor and of the absorbed entity, or --pairs")
    todo = read_pairs(pairs) if pairs is not None else [(survivor, absorbed)]
    failed = False

    async def run() -> None:
        nonlocal failed
        model = entity_model(type)
        chosen = entity_model(as_class) if as_class else None
        for into, absorb in todo:
            typer.echo(f"{absorb} into {into}:")
            try:
                if dry_run:
                    preview = await model.merge_preview(
                        absorb=absorb, into=into, as_class=chosen
                    )
                    lines = describe_preview(preview)
                    failed = failed or not preview.possible
                else:
                    result = await model.merge(
                        absorb=absorb, into=into, as_class=chosen, allow_large=large
                    )
                    lines = describe_result(result)
            except PanglossWriteError as error:
                typer.secho(f"  not merged: {error}", fg="red", err=True)
                failed = True
                return
            for line in lines:
                typer.echo(f"  {line}")

    run_connected(ctx, run, user)
    if failed:
        raise typer.Exit(1)
    if not dry_run:
        typer.secho(f"Merged {len(todo)}", fg="green")


@cli.command("unmerge")
def unmerge_command(
    ctx: typer.Context,
    merge_id: UUID = typer.Argument(
        ..., help="The id of the merge (`pangloss merges`)"
    ),
    user: str = typer.Option(..., "--user", help="The user the merge is undone by"),
    confirm_migrated: bool = typer.Option(
        False,
        "--confirm-migrated",
        help="Undo it though the database has been migrated since (look at --dry-run first)",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Say what would be undone, and write nothing"
    ),
) -> None:
    """Undo a merge: what it moved goes back to the entity it absorbed, which is itself again

    What cannot be put back (the document was changed or removed since) is listed, and so is what was written to the
    survivor since the merge, which stays on it."""
    from pangloss_models import Entity, PanglossWriteError

    async def run() -> Any:
        return await Entity.unmerge(
            merge_id,
            # (a dry run shows what would go back whatever has been migrated)
            confirm_migrated=confirm_migrated or dry_run,
            dry_run=dry_run,
        )

    try:
        result = run_connected(ctx, run, user)
    except PanglossWriteError as error:
        typer.secho(f"Not undone: {error}", fg="red", err=True)
        raise typer.Exit(1) from error
    would = "would go" if dry_run else "went"
    typer.echo(
        f"{result.restored} references {would} back, in {result.heads} documents and entities"
    )
    for move in result.unmatched:
        typer.echo(
            f"  not put back ({move['reason']}): {move['source_type']} {move['source']}, {move['field']}"
        )
    if result.made_since:
        typer.echo(
            f"{len(result.made_since)} were written to the survivor since the merge, and stay on it:"
        )
        for head in result.made_since:
            typer.echo(f"  {head.type} {head.id} {head.label or ''}".rstrip())
    if result.fields_restored:
        typer.echo("The survivor's fields are as they were before the merge")
    elif result.draft is not None:
        typer.echo(
            f"The survivor's fields were left as they are ({result.draft_reason}): what they were before the "
            "merge is on the merge's record, to reconcile by hand"
        )
    if not dry_run:
        typer.secho(f"Merge {merge_id} is undone", fg="green")


@cli.command("merges")
def merges_command(
    ctx: typer.Context,
    state: list[str] = typer.Option(
        [],
        "--state",
        help="Only those in this state (proposed, rejected, stale, running, done, undone): more than once for more",
    ),
    limit: int = typer.Option(
        50, "--limit", help="At most this many, the latest first"
    ),
) -> None:
    """List the merges of entities that are recorded, the latest first"""
    from pangloss_core import storage_of

    async def run() -> tuple[list[Any], int]:
        operation = getattr(storage_of().operations, "list_merges", None)
        if operation is None:
            fail("The storage of this project cannot merge entities")
        return await operation(states=state or None, limit=limit)

    merges, total = run_connected(ctx, run)
    for merge in merges:
        who = merge.by or merge.proposed_by or "?"
        when = merge.when or merge.proposed_when
        date = f"{when:%Y-%m-%d %H:%M}" if when else "?"
        typer.echo(
            f"{merge.id}  {merge.state:<8}  {date}  {who}  "
            f"{merge.absorbed_type} {merge.absorbed_label or merge.absorbed} "
            f"-> {merge.survivor_type} {merge.survivor_label or merge.survivor}"
            + (
                f"  (undo proposed by {merge.undo_proposed_by})"
                if merge.undo_proposed_by
                else ""
            )
        )
    typer.echo(f"{total} in all" if merges else "No merges")
