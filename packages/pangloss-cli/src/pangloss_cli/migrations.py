"""`pangloss makemigrations`, `migrate` and `showmigrations`: see `docs/migrations.md`.

The models are compared with the migrations of the installed apps (`<app>/migrations/`),
and what changed is written as new migrations, after asking what cannot be known from the models
(is this a rename? what value do the nodes that exist get?). `migrate` applies the migrations that
the database has not had, and records them.
"""

import copy
import importlib
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import typer
from pangloss_models.exceptions import (
    PanglossImportError,
    PanglossInitialisationError,
    PanglossMigrationError,
    PanglossMigrationIrreversible,
)
from pangloss_models.migrations import PossibleRename, build_snapshot, data_view
from pangloss_models.migrations import changes as c
from pangloss_models.migrations.affected import affected_models
from pangloss_models.migrations.check import CONCURRENCY as CHECK_CONCURRENCY
from pangloss_models.migrations.check import check_data
from pangloss_models.migrations.files import (
    EMPTY_SNAPSHOT,
    Migration,
    MigrationGraph,
    discover,
    graph_of,
    migrations_directory,
    next_name,
    squash,
    write,
)
from pangloss_models.migrations.history import (
    pending,
    problems,
    resolve_target,
    states_around,
    to_unapply,
)
from pangloss_models.migrations.planner import app_of_change, plan, with_what_they_need
from pangloss_models.migrations.questions import (
    collect_questions,
    parse_value,
    with_answer,
)
from pangloss_models.migrations.reverse import reverse_changes
from pangloss_models.migrations.startup import migration_backend_of, structure_of

from pangloss_cli.project import Project, fail
from pangloss_cli.users import run_with_database

SAFETY_MARKS = {
    "safe": "",
    "additive": "",
    "transforming": "",
    "lossy": "  [LOSES DATA]",
    "manual": "  [NEEDS CODE]",
}


def optional_migration_backend(project: Project) -> ModuleType | None:
    return migration_backend_of(project.require_settings().DATABASE_MODULE)


def load_models(project: Project) -> dict:
    """Import and initialise the models of the project, and describe them"""
    from pangloss_models import initialise

    project.require_settings()
    try:
        project.import_models()
        initialise()
    except (PanglossInitialisationError, PanglossImportError) as error:
        fail(f"Cannot initialise the models: {error}")
    return build_snapshot(structure_of(optional_migration_backend(project)))


def installed_apps(project: Project) -> list[str]:
    return list(project.require_settings().INSTALLED_APPS)


def load_graph(apps: list[str], applied: dict | None = None) -> MigrationGraph:
    try:
        return graph_of(apps, applied)
    except PanglossMigrationError as error:
        fail(str(error))
        raise


def migration_backend(project: Project) -> ModuleType:
    settings = project.require_settings()
    try:
        return importlib.import_module(f"{settings.DATABASE_MODULE}.migration_backend")
    except ModuleNotFoundError:
        fail(f"The database '{settings.DATABASE_MODULE}' does not support migrations")
        raise


def describe(migration: Migration) -> list[str]:
    return [
        f"    - {change.describe()}{SAFETY_MARKS[change.safety]}"
        for change in migration.changes
    ]


# ---------------------------------------------------------------------------
# makemigrations
# ---------------------------------------------------------------------------


def ask_renames(
    result_questions: list[PossibleRename],
) -> tuple[list[PossibleRename], list[PossibleRename]]:
    confirmed, declined = [], []
    for question in result_questions:
        (
            confirmed if typer.confirm(question.question(), default=False) else declined
        ).append(question)
    return confirmed, declined


def ask_answers(
    changes: list[c.Change],
    state: dict,
    noinput: bool,
    wanted: Callable[[c.Change], bool] | None = None,
) -> list[c.Change]:
    """Ask for what the changes need, and put it in them (only for those that `wanted` says yes to)"""
    needed = [
        (index, question)
        for index, question in collect_questions(changes, state)
        if wanted is None or wanted(changes[index])
    ]
    changes = list(changes)
    unanswerable: list[str] = []
    refused: list[str] = []
    for index, question in needed:
        change = changes[index]
        if question.descriptor is None:
            unanswerable.append(f"{change.describe()}: {question.prompt}")
            continue
        if noinput:
            if not question.optional:
                refused.append(f"{change.describe()}: {question.prompt}")
            continue
        while True:
            text = typer.prompt(question.prompt, default="", show_default=False)
            if not text.strip():
                if question.optional:
                    break
                typer.secho("An answer is needed.", fg="red", err=True)
                continue
            try:
                value = parse_value(text, question.descriptor, state["enums"])
            except PanglossMigrationError as error:
                typer.secho(str(error), fg="red", err=True)
                continue
            changes[index] = with_answer(change, question.field, value)
            break
    if refused:
        fail(
            "These need an answer (so no migration is written without asking):\n  "
            + "\n  ".join(refused)
        )
    if unanswerable:
        typer.secho(
            "These need an answer that is written in the migration:",
            fg="yellow",
            err=True,
        )
        for line in unanswerable:
            typer.secho(f"  {line}", fg="yellow", err=True)
    return changes


def make_empty(
    project: Project, app: str | None, name: str | None, dry_run: bool
) -> None:
    """A migration with no changes, to write by hand"""
    apps = installed_apps(project)
    if app is None:
        fail(
            "`--empty` needs the app the migration is for: `pangloss makemigrations --empty <app>`"
        )
    if app not in apps:
        fail(f"{app} is not one of the INSTALLED_APPS")
    graph = load_graph(apps)
    leaf = graph.leaf(app)
    if leaf is None:
        fail(f"{app} has no migrations yet: run `pangloss makemigrations` first")
    migration = Migration(
        app=app,
        name=next_name(
            (m for m in graph.migrations.values() if m.app == app), name or "empty"
        ),
        changes=(),
        schema_hash=leaf.schema_hash,
    )
    typer.secho(f"{migration}", bold=True)
    if dry_run:
        typer.echo("(nothing was written)")
        return
    path = write(migration, migrations_directory(app))
    typer.secho(f"Wrote {path}", fg="green")


def makemigrations(
    ctx: typer.Context,
    app: str | None = typer.Argument(
        None,
        help="Only this app's migrations (and the other apps' they need); with --empty, the app it is for",
    ),
    empty: bool = typer.Option(
        False,
        "--empty",
        help="Write a migration with no changes, to put RunCypher / RunPython in",
    ),
    name: str | None = typer.Option(
        None, "--name", "-n", help="A name for the migration"
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be written"),
    check: bool = typer.Option(
        False,
        "--check",
        help="Write nothing; exit with an error if the models have changed",
    ),
    noinput: bool = typer.Option(
        False, "--noinput", help="Never ask: fail if something has to be asked"
    ),
) -> None:
    """Write the migrations for what has changed in the models since the last"""
    project: Project = ctx.obj
    if empty:
        make_empty(project, app, name, dry_run)
        return
    snapshot = load_models(project)
    apps = installed_apps(project)
    if app is not None and app not in apps:
        fail(f"{app} is not one of the INSTALLED_APPS")
    graph = load_graph(apps)

    confirmed: list[PossibleRename] = []
    declined: list[PossibleRename] = []
    try:
        while True:
            result = plan(graph, snapshot, apps, confirmed, declined)
            if result.is_final:
                break
            if noinput or check:
                questions = "\n".join(f"  {q.question()}" for q in result.questions)
                fail(
                    f"These need an answer (so a migration cannot be written without asking):\n{questions}"
                )
            new_confirmed, new_declined = ask_renames(result.questions)
            confirmed += new_confirmed
            declined += new_declined

        if result.is_empty:
            typer.echo("No changes")
            return
        if app is not None and not with_what_they_need(result.migrations, app):
            typer.echo(f"No changes for {app}")
            return
        if check:
            shown = (
                [
                    ch
                    for m in with_what_they_need(result.migrations, app)
                    for ch in m.changes
                ]
                if app is not None
                else result.changes
            )
            typer.echo(f"{len(shown)} changes since the last migration:")
            for change in shown:
                typer.echo(f"  - {change.describe()}")
            raise typer.Exit(1)

        owners = graph.owners()
        mine: Callable[[c.Change], bool] | None = None
        if app is not None:
            # (only what the app's migrations, and those they need, will hold is asked about)
            held = {m.app for m in with_what_they_need(result.migrations, app)}
            mine = lambda change: app_of_change(change, snapshot, owners, apps) in held
        answered = ask_answers(result.changes, result.old, noinput, mine)
        result = plan(
            graph,
            snapshot,
            apps,
            confirmed,
            declined,
            answer=lambda changes, old: answered,
            name=name,
        )
    except PanglossMigrationError as error:
        fail(str(error))
        raise

    if app is not None:
        kept = with_what_they_need(result.migrations, app)
        left = [m for m in result.migrations if m not in kept]
        result.migrations = kept
        if left:
            typer.secho(
                f"Not written (not {app}'s, nor needed by it): {', '.join(str(m) for m in left)}. "
                "`pangloss makemigrations` writes them.",
                fg="yellow",
            )

    for migration in result.migrations:
        typer.secho(f"{migration}", bold=True)
        for line in describe(migration):
            typer.echo(line)
    if dry_run:
        typer.echo("(nothing was written)")
        return
    for migration in result.migrations:
        path = write(migration, migrations_directory(migration.app))
        typer.secho(f"Wrote {path}", fg="green")


def squashmigrations(
    ctx: typer.Context,
    app: str = typer.Argument(..., help="The app"),
    first: str = typer.Argument(
        ..., help="The first migration of the run (name or number)"
    ),
    last: str = typer.Argument(
        ..., help="The last migration of the run (name or number)"
    ),
    name: str | None = typer.Option(
        None, "--name", "-n", help="A name for the squashed migration"
    ),
    no_optimize: bool = typer.Option(
        False,
        "--no-optimize",
        help="Keep all the changes, one after another, as they were",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be written"),
) -> None:
    """Replace a run of migrations of an app by one that does the same.

    A database that has had all of them, or none, uses the squashed one; one that is part way
    through goes on with the originals. Delete the originals once every database has had them all."""
    project: Project = ctx.obj
    apps = installed_apps(project)
    if app not in apps:
        fail(f"{app} is not one of the INSTALLED_APPS")
    graph = load_graph(apps)
    try:
        squashed = squash(graph, app, first, last, name=name, optimize=not no_optimize)
    except PanglossMigrationError as error:
        fail(str(error))
        raise
    in_graph = [
        graph.migrations[key] for key in squashed.replaces if key in graph.migrations
    ]
    before = sum(len(m.changes) for m in in_graph)
    typer.secho(f"{squashed}", bold=True)
    typer.echo(f"  replaces {', '.join(n for _, n in squashed.replaces)}")
    typer.echo(
        f"  {before} changes in {len(in_graph)} migrations -> {len(squashed.changes)} changes"
    )
    for line in describe(squashed):
        typer.echo(line)
    if dry_run:
        typer.echo("(nothing was written)")
        return
    path = write(squashed, migrations_directory(app))
    typer.secho(f"Wrote {path}", fg="green")
    typer.echo(
        "The migrations it replaces are kept, for databases that are part way through them. "
        "Delete them (the files) when every database has applied them all."
    )


def backups(ctx: typer.Context) -> None:
    """List the snapshots the server has (what `migrate --backup` takes), newest first"""
    project: Project = ctx.obj
    backend = migration_backend(project)
    if not hasattr(backend, "backups"):
        fail("This database does not list backups")
    for row in run_with_database(project, backend.backups):
        typer.echo(f"{row['creation_time']}  {row['size']:>10}  {row['path']}")


def restore(
    ctx: typer.Context,
    path: str = typer.Argument(..., help="A snapshot, as `pangloss backups` shows it"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Do not ask first"),
) -> None:
    """Put the database back to a snapshot. EVERYTHING in it now is replaced by what the snapshot
    has: data written since is lost, and so is the record of migrations since (so run `pangloss
    migrate` after, with the code that goes with it)."""
    project: Project = ctx.obj
    backend = migration_backend(project)
    if not hasattr(backend, "restore"):
        fail("This database cannot restore a backup")
    if not yes:
        typer.confirm(f"Replace everything in the database with {path}?", abort=True)
    try:
        run_with_database(project, lambda: backend.restore(path))
    except PanglossMigrationError as error:
        fail(str(error))
    typer.secho(
        "Restored. Run `pangloss showmigrations` to see where the database is.",
        fg="green",
    )


def history_warnings(project: Project, squashed: list[Migration]) -> list[str]:
    """What deleting would do to the versions kept by `pangloss-history` (nothing, if it is not
    installed)"""
    settings = project.require_settings()
    if "pangloss_history" not in settings.INSTALLED_APPS:
        return []
    from pangloss_history.cleanup import warnings_for

    return warnings_for(settings, squashed)


def cleanmigrations(
    ctx: typer.Context,
    app: str | None = typer.Argument(None, help="Only this app's"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Do not ask before deleting"),
) -> None:
    """Delete the files of the migrations that a squashed migration replaces.

    Only this database is looked at: it must have had all of them or none (not be part way through).
    Another database (a colleague's, staging, production) that is part way through them cannot go
    on without them, so delete them only when every database has applied them all."""
    project: Project = ctx.obj
    apps = installed_apps(project)
    if app is not None and app not in apps:
        fail(f"{app} is not one of the INSTALLED_APPS")
    backend = migration_backend(project)

    async def read():
        await backend.ensure_ready()
        return await backend.applied()

    applied = run_with_database(project, read)
    try:
        everything = [m for name in apps for m in discover(name)]
        graph = MigrationGraph.of(everything, applied)
    except PanglossMigrationError as error:
        fail(str(error))
        raise

    files: list[tuple[Migration, Path]] = []
    part_way: list[Migration] = []
    seen: set[Path] = set()
    # (what the squashed migrations that are used replace, among them squashed migrations that were
    # squashed again)
    covered = {key for originals in graph.stands_for.values() for key in originals}
    for squashed in (
        m for m in everything if m.replaces and (app is None or m.app == app)
    ):
        if squashed.key not in graph.migrations:
            if squashed.key not in covered:
                part_way.append(
                    squashed
                )  # (not used: the database is part way through what it replaces)
            continue
        for original in squashed.replaces:
            path = migrations_directory(original[0]) / f"{original[1]}.py"
            if path.exists() and path not in seen:
                seen.add(path)
                files.append((squashed, path))
    for squashed in part_way:
        typer.secho(
            f"{squashed}: this database is part way through what it replaces, so they are kept",
            fg="yellow",
        )
    if not files:
        typer.echo("Nothing to delete")
        return
    typer.echo("These are replaced by a squashed migration:")
    for squashed, path in files:
        typer.echo(f"  {path.name}  (by {squashed.name})")
    typer.secho(
        "No other database is looked at. One that is part way through them cannot go on without them.",
        fg="yellow",
    )
    for warning in history_warnings(
        project, list({id(s): s for s, _ in files}.values())
    ):
        typer.secho(f"History: {warning}", fg="yellow")
    if not yes:
        typer.confirm("Delete them?", abort=True)
    for _, path in files:
        path.unlink()
    typer.secho(f"Deleted {len(files)} files", fg="green")


# ---------------------------------------------------------------------------
# migrate, showmigrations
# ---------------------------------------------------------------------------


def report_dry_run(reports: list) -> None:
    """Say what a dry run found, and fail if some change would"""
    failed = False
    typer.echo("\nTried, and rolled back:")
    for report in reports:
        typer.secho(f"  {report.app}.{report.name}", bold=True)
        for change_report in report.changes:
            typer.echo(f"    - {change_report.change.describe()}")
            typer.secho(
                f"        {change_report.summary()}",
                fg="red" if change_report.status == "error" else None,
            )
        failed = failed or report.failed
    if failed:
        fail("Some changes would fail: nothing was changed")
    typer.echo("Nothing was changed")


def go_backwards(
    project: Project,
    backend: ModuleType,
    graph: MigrationGraph,
    applied: dict,
    app: str,
    wanted: Migration | None,
    snapshot: dict,
    *,
    plan_only: bool,
    dry_run: bool,
    fake: bool,
    yes: bool,
    backup: bool | None,
    no_check: bool,
    check: bool,
    batch_size: int | None = None,
) -> None:
    """Undo the migrations of `app` after `wanted` (and what follows them): their changes are
    undone by the changes that `reverse_changes` makes, the last applied first"""
    chosen = to_unapply(graph, applied, app, wanted)
    if not chosen:
        typer.echo("Nothing to undo")
        return
    if check:
        typer.echo(f"{len(chosen)} migrations to undo")
        raise typer.Exit(1)

    # (one that failed or was left running is undone as if it was applied: the changes can be made over
    # what was done)
    keys = {
        key
        for key, record in applied.items()
        if record.get("status") in ("applied", "failed", "running")
    }
    before, after, now = states_around(graph, keys)
    undoing: list[Migration] = []
    lossy = False
    to_be_asked: list[str] = []
    for migration in chosen:
        try:
            reversal = reverse_changes(migration.changes, before[migration.key])
        except PanglossMigrationIrreversible as error:
            fail(f"{migration} cannot be undone: {error}")
            raise
        if plan_only:
            # (a plan says what will be asked, and does not ask)
            changes = list(reversal.changes)
            to_be_asked += [
                f"{migration}: {question.prompt}"
                for _, question in collect_questions(changes, after[migration.key])
                if not question.optional
            ]
        else:
            changes = ask_answers(reversal.changes, after[migration.key], noinput=False)
            for _, question in collect_questions(changes, after[migration.key]):
                if not question.optional:
                    fail(f"{migration} cannot be undone without: {question.prompt}")
        lossy = lossy or reversal.lossy
        undoing.append(
            Migration(
                app=migration.app,
                name=migration.name,
                changes=tuple(changes),
                replaces=migration.replaces,  # (their records go too)
                atomic=migration.atomic,
                batch_size=migration.batch_size,
            )
        )

    typer.echo("To undo:")
    for migration in undoing:
        typer.secho(f"  {migration}", bold=True)
        for line in describe(migration):
            typer.echo(line)
    if lossy:
        typer.secho(
            "  [LOSES DATA: what the migrations wrote or changed is not brought back]",
            fg="yellow",
        )
    if plan_only:
        if to_be_asked:
            typer.echo("Going back will ask for:")
            for line in to_be_asked:
                typer.echo(f"  - {line}")
        return
    if dry_run:
        report_dry_run(
            run_with_database(project, lambda: backend.dry_run(undoing, now))
        )
        return

    if lossy and not fake and backup is None:
        fail(
            "Some of this loses data: give --backup (take a snapshot first) or --no-backup (you "
            "have your own)"
        )
    if lossy and not fake and not yes:
        typer.confirm("Some of this loses data. Go on?", abort=True)

    def progress(migration: Migration, what: str) -> None:
        typer.echo(f"  {migration}: {what}")

    taken: list[str] = []

    async def run_all():
        await backend.lock()
        try:
            if backup and not fake:
                if not hasattr(backend, "backup"):
                    raise PanglossMigrationError("This database cannot take a backup")
                taken_backup = await backend.backup()
                taken.append(taken_backup)
                typer.echo(f"Backup: {taken_backup}")
                notice = (
                    await backend.backup_notice()
                    if hasattr(backend, "backup_notice")
                    else None
                )
                if notice:
                    typer.secho(notice, fg="yellow")
            return await backend.unapply(
                undoing, now, fake=fake, progress=progress, batch_size=batch_size
            )
        finally:
            await backend.unlock()

    try:
        run_with_database(project, run_all)
    except PanglossMigrationError as error:
        fail(str(error))
    typer.secho("Done", fg="green")
    if not fake and not no_check:
        remaining = before[chosen[-1].key]
        changes = [change for migration in undoing for change in migration.changes]
        affected = sorted(affected_models(changes, remaining))
        if affected:
            typer.echo(
                f"Models the undoing could have made unreadable: {', '.join(affected)}"
            )
            report_data_check(project, types=affected)
        else:
            typer.echo("Nothing that exists is affected: no data to read")
    warn_if_backup_gone(project, backend, taken)


def migrate(
    ctx: typer.Context,
    app: str | None = typer.Argument(
        None,
        help="Only this app's migrations (and what they need), or go back to <target>",
    ),
    target: str | None = typer.Argument(
        None,
        help="Go to this migration of the app (its name or number): forwards if it is not applied, "
        "backwards if it is (`zero`: undo them all). Backwards undoes what follows it, in every app",
    ),
    plan_only: bool = typer.Option(
        False, "--plan", help="Show what would be applied, and apply nothing"
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Try the changes in a transaction that is rolled back, and say what each would do to "
        "the data (and which would fail). Nothing is changed",
    ),
    no_check: bool = typer.Option(
        False, "--no-check", help="Do not read the data with the models after applying"
    ),
    batch_size: int | None = typer.Option(
        None,
        "--batch-size",
        min=1,
        help="Make the migrations in batches of this many nodes, each its own transaction, with how "
        "far it has got kept: one that stops (or fails) goes on from there the next time. Without "
        "it a migration is one transaction, unless it says `atomic = False`",
    ),
    check_all: bool = typer.Option(
        False,
        "--check-all",
        help="Read all the data after applying, not only the models the migrations could have "
        "made unreadable",
    ),
    fake: bool = typer.Option(
        False,
        "--fake",
        help="Record the migrations as applied without running them (for a database that already is as they say)",
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Do not ask before changes that lose data"
    ),
    backup: bool | None = typer.Option(
        None,
        "--backup/--no-backup",
        help="Take a snapshot of the database before applying (after the lock). Migrations with "
        "changes that lose data need one of the two",
    ),
    unlock: bool = typer.Option(
        False, "--unlock", help="Remove the lock of a migrate that was stopped"
    ),
    check: bool = typer.Option(
        False,
        "--check",
        help="Apply nothing; exit with an error if migrations are to be applied",
    ),
) -> None:
    """Apply the migrations that the database has not had"""
    project: Project = ctx.obj
    snapshot = load_models(project)
    apps = installed_apps(project)
    backend = migration_backend(project)

    if unlock:
        run_with_database(project, backend.unlock)
        typer.secho("Unlocked", fg="green")
        return

    async def state_of_database():
        await backend.ensure_ready()
        return await backend.applied()

    applied = run_with_database(project, state_of_database)
    graph = load_graph(apps, applied)
    applied = graph.reconcile(
        applied
    )  # (a squashed migration whose originals were applied is)

    found = problems(graph, applied)
    if found:
        for line in found:
            typer.secho(line, fg="red", err=True)
        fail("The migrations and the record of them in the database do not agree")

    wanted: Migration | None = None
    if app is not None:
        if app not in apps:
            fail(f"{app} is not one of the INSTALLED_APPS")
        try:
            wanted = resolve_target(graph, app, target) if target else graph.leaf(app)
        except PanglossMigrationError as error:
            fail(str(error))
        is_applied = (
            wanted is not None
            and applied.get(wanted.key, {}).get("status") == "applied"
        )
        if target is not None and (wanted is None or is_applied):
            go_backwards(
                project,
                backend,
                graph,
                applied,
                app,
                wanted,
                snapshot,
                plan_only=plan_only,
                dry_run=dry_run,
                fake=fake,
                yes=yes,
                backup=backup,
                no_check=no_check,
                check=check,
                batch_size=batch_size,
            )
            return
    elif target is not None:
        fail("A target needs the app it is for: `pangloss migrate <app> <target>`")

    todo = pending(graph, applied)
    if wanted is not None:
        needed = graph.closure([wanted.key])
        todo = [m for m in todo if m.key in needed]
    if not todo:
        typer.echo("Nothing to apply")
        warn_if_models_have_changed(graph, snapshot)
        return
    if check:
        typer.echo(f"{len(todo)} migrations to apply")
        raise typer.Exit(1)

    if not applied and not fake and hasattr(backend, "has_data"):
        if run_with_database(project, backend.has_data):
            typer.secho(
                "The database has data, and no record of any migration. If it was made before these "
                "migrations (by `pangloss setup-database`, say), run `pangloss migrate --fake` to "
                "record them without running them. Otherwise go on.",
                fg="yellow",
                err=True,
            )

    typer.echo("To apply:")
    for migration in todo:
        typer.secho(f"  {migration}", bold=True)
        for line in describe(migration):
            typer.echo(line)
    if plan_only:
        return

    applied_keys = [
        key for key, record in applied.items() if record.get("status") == "applied"
    ]
    state = graph.state(applied_keys) if applied_keys else copy.deepcopy(EMPTY_SNAPSHOT)

    if dry_run:
        report_dry_run(run_with_database(project, lambda: backend.dry_run(todo, state)))
        return

    lossy = [m for m in todo for ch in m.changes if ch.safety == "lossy"]
    if lossy and not fake and backup is None:
        fail(
            "Some of these lose data: give --backup (take a snapshot first) or --no-backup (you "
            "have your own)"
        )
    if lossy and not fake and not yes:
        typer.confirm("Some of these lose data. Go on?", abort=True)

    def progress(migration: Migration, what: str) -> None:
        typer.echo(f"  {migration}: {what}")

    taken: list[str] = []

    async def run_all():
        await backend.lock()
        try:
            if backup and not fake:
                if not hasattr(backend, "backup"):
                    raise PanglossMigrationError("This database cannot take a backup")
                taken_backup = await backend.backup()
                taken.append(taken_backup)
                typer.echo(f"Backup: {taken_backup}")
                notice = (
                    await backend.backup_notice()
                    if hasattr(backend, "backup_notice")
                    else None
                )
                if notice:
                    typer.secho(notice, fg="yellow")
            return await backend.apply(
                todo, state, fake=fake, progress=progress, batch_size=batch_size
            )
        finally:
            await backend.unlock()

    try:
        run_with_database(project, run_all)
    except PanglossMigrationError as error:
        fail(str(error))
    typer.secho("Done", fg="green")
    warn_if_models_have_changed(graph, snapshot)
    if not fake and not no_check:
        if check_all:
            report_data_check(project)
        else:
            # (adding a model, or an optional field, changes nothing that exists)
            changes = [change for migration in todo for change in migration.changes]
            affected = sorted(affected_models(changes, graph.state()))
            if affected:
                typer.echo(
                    f"Models the migrations could have made unreadable: {', '.join(affected)}"
                )
                report_data_check(project, types=affected)
            else:
                typer.echo(
                    "Nothing that exists is affected by these migrations: no data to read"
                )
    warn_if_backup_gone(project, backend, taken)


def warn_if_backup_gone(
    project: Project, backend: ModuleType, taken: list[str]
) -> None:
    """Say so if the database has already removed the backup this `migrate` took: it keeps only the
    newest few, and reading the data back after a large migration can take longer than they last"""
    if not taken or not hasattr(backend, "backups"):
        return
    try:
        kept = {row["path"] for row in run_with_database(project, backend.backups)}
    except PanglossMigrationError, OSError:
        return
    for path in taken:
        if path not in kept:
            typer.secho(
                f"The backup {path} is no longer there: the database keeps only the newest few "
                "snapshots, and has made others since. Take another (`pangloss migrate --backup` "
                "does, before it changes anything) if you still need one.",
                fg="yellow",
            )


def warn_if_models_have_changed(graph: MigrationGraph, snapshot: dict) -> None:
    """The migrations come to the models, or `makemigrations` has something to write"""
    if graph.state() != data_view(snapshot):
        typer.secho(
            "The models have changed since the migrations: run `pangloss makemigrations`",
            fg="yellow",
        )


def showmigrations(ctx: typer.Context) -> None:
    """List the migrations, and which the database has had"""
    project: Project = ctx.obj
    apps = installed_apps(project)
    backend = migration_backend(project)

    async def read():
        await backend.ensure_ready()
        return await backend.applied()

    applied = run_with_database(project, read)
    try:
        graph = graph_of(apps, applied)
    except PanglossMigrationError as error:
        # (the migrations do not make a graph with this database, but what is on disk and what
        # the database has had can still be listed, to see what is wrong)
        show_without_graph(apps, applied)
        fail(str(error))
        raise
    applied = graph.reconcile(applied)
    for app in apps:
        own = [m for m in graph.order() if m.app == app]
        if not own:
            continue
        typer.secho(app, bold=True)
        for migration in own:
            record = applied.get(migration.key, {})
            status = record.get("status")
            mark = {"applied": "[X]", "failed": "[!]", "running": "[~]"}.get(
                status, "[ ]"
            )
            note = " (faked)" if record.get("fake") else ""
            typer.echo(f" {mark} {migration.name}{note}")
    for line in problems(graph, applied):
        typer.secho(line, fg="red", err=True)


def show_without_graph(apps: list[str], applied: dict) -> None:
    """The migrations on disk and the records of the database, side by side, by name"""
    for app in apps:
        names = {m.name for m in discover(app)}
        recorded = {name: record for (a, name), record in applied.items() if a == app}
        if not names and not recorded:
            continue
        typer.secho(app, bold=True)
        for name in sorted(names | recorded.keys()):
            status = recorded.get(name, {}).get("status")
            mark = {"applied": "[X]", "failed": "[!]", "running": "[~]"}.get(
                status, "[ ]"
            )
            note = "" if name in names else " (no file)"
            typer.echo(f" {mark} {name}{note}")


def report_data_check(
    project: Project,
    types: list[str] | None = None,
    limit: int | None = None,
    parallel: int = CHECK_CONCURRENCY,
) -> None:
    """Read the data with the models, and say what cannot be read (exit 1 if anything)"""
    typer.echo("Reading the data with the models ...")
    check = run_with_database(
        project, lambda: check_data(types=types, limit=limit, concurrency=parallel)
    )
    if check.ok:
        typer.secho(f"All {check.checked} can be read", fg="green")
        return
    typer.secho(
        f"{len(check.problems)} of {check.checked} cannot be read:", fg="red", err=True
    )
    for problem in check.problems[:20]:
        typer.secho(f"  {problem}", fg="red", err=True)
    if len(check.problems) > 20:
        typer.secho(f"  ... and {len(check.problems) - 20} more", fg="red", err=True)
    raise typer.Exit(1)


def check_data_command(
    ctx: typer.Context,
    type: list[str] = typer.Option(
        [], "--type", "-t", help="Only this model (more than once for more)"
    ),
    limit: int | None = typer.Option(
        None, "--limit", help="At most this many of each model"
    ),
    parallel: int = typer.Option(
        CHECK_CONCURRENCY,
        "--parallel",
        min=1,
        help="How many to read at once (16 was about four times faster than one on a large database)",
    ),
) -> None:
    """Read all the data with the models as they are, and report what cannot be read

    Run after a migration (`migrate` does), or to find what the models and the data no longer
    agree about."""
    project: Project = ctx.obj
    load_models(project)
    report_data_check(project, types=type or None, limit=limit, parallel=parallel)
