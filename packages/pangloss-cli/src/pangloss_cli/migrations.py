"""`pangloss makemigrations`, `migrate` and `showmigrations`: see `docs/migrations.md`.

The models are compared with the migrations of the installed apps (`<app>/migrations/`),
and what changed is written as new migrations, after asking what cannot be known from the models
(is this a rename? what value do the nodes that exist get?). `migrate` applies the migrations that
the database has not had, and records them.
"""

import importlib
from types import ModuleType

import typer
from pangloss_models.exceptions import (
    PanglossImportError,
    PanglossInitialisationError,
    PanglossMigrationError,
)
from pangloss_models.migrations import PossibleRename, build_snapshot, data_view
from pangloss_models.migrations import changes as c
from pangloss_models.migrations.affected import affected_models
from pangloss_models.migrations.check import check_data
from pangloss_models.migrations.files import (
    Migration,
    MigrationGraph,
    graph_of,
    migrations_directory,
    write,
)
from pangloss_models.migrations.history import pending, problems
from pangloss_models.migrations.planner import plan
from pangloss_models.migrations.questions import (
    collect_questions,
    parse_value,
    with_answer,
)

from pangloss_cli.project import Project, fail
from pangloss_cli.users import run_with_database

SAFETY_MARKS = {
    "safe": "",
    "additive": "",
    "transforming": "",
    "lossy": "  [LOSES DATA]",
    "manual": "  [NEEDS CODE]",
}


def load_models(project: Project) -> dict:
    """Import and initialise the models of the project, and describe them"""
    from pangloss_models import initialise

    project.require_settings()
    try:
        project.import_models()
        initialise()
    except (PanglossInitialisationError, PanglossImportError) as error:
        fail(f"Cannot initialise the models: {error}")
    return build_snapshot()


def installed_apps(project: Project) -> list[str]:
    return list(project.require_settings().INSTALLED_APPS)


def load_graph(apps: list[str]) -> MigrationGraph:
    try:
        return graph_of(apps)
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
    return [f"    - {change.describe()}{SAFETY_MARKS[change.safety]}" for change in migration.changes]


# ---------------------------------------------------------------------------
# makemigrations
# ---------------------------------------------------------------------------


def ask_renames(result_questions: list[PossibleRename]) -> tuple[list[PossibleRename], list[PossibleRename]]:
    confirmed, declined = [], []
    for question in result_questions:
        (confirmed if typer.confirm(question.question(), default=False) else declined).append(question)
    return confirmed, declined


def ask_answers(changes: list[c.Change], state: dict, noinput: bool) -> list[c.Change]:
    """Ask for what the changes need, and put it in them"""
    needed = collect_questions(changes, state)
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
        fail("These need an answer (so no migration is written without asking):\n  " + "\n  ".join(refused))
    if unanswerable:
        typer.secho("These need an answer that is written in the migration:", fg="yellow", err=True)
        for line in unanswerable:
            typer.secho(f"  {line}", fg="yellow", err=True)
    return changes


def makemigrations(
    ctx: typer.Context,
    name: str | None = typer.Option(None, "--name", "-n", help="A name for the migration"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be written"),
    check: bool = typer.Option(
        False, "--check", help="Write nothing; exit with an error if the models have changed"
    ),
    noinput: bool = typer.Option(False, "--noinput", help="Never ask: fail if something has to be asked"),
) -> None:
    """Write the migrations for what has changed in the models since the last"""
    project: Project = ctx.obj
    snapshot = load_models(project)
    apps = installed_apps(project)
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
                fail(f"These need an answer (so a migration cannot be written without asking):\n{questions}")
            new_confirmed, new_declined = ask_renames(result.questions)
            confirmed += new_confirmed
            declined += new_declined

        if result.is_empty:
            typer.echo("No changes")
            return
        if check:
            typer.echo(f"{len(result.changes)} changes since the last migration:")
            for change in result.changes:
                typer.echo(f"  - {change.describe()}")
            raise typer.Exit(1)

        answered = ask_answers(result.changes, result.old, noinput)
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


# ---------------------------------------------------------------------------
# migrate, showmigrations
# ---------------------------------------------------------------------------


def migrate(
    ctx: typer.Context,
    plan_only: bool = typer.Option(False, "--plan", help="Show what would be applied, and apply nothing"),
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
    yes: bool = typer.Option(False, "--yes", "-y", help="Do not ask before changes that lose data"),
    unlock: bool = typer.Option(False, "--unlock", help="Remove the lock of a migrate that was stopped"),
    check: bool = typer.Option(
        False, "--check", help="Apply nothing; exit with an error if migrations are to be applied"
    ),
) -> None:
    """Apply the migrations that the database has not had"""
    project: Project = ctx.obj
    snapshot = load_models(project)
    apps = installed_apps(project)
    graph = load_graph(apps)
    backend = migration_backend(project)

    if unlock:
        run_with_database(project, backend.unlock)
        typer.secho("Unlocked", fg="green")
        return

    async def state_of_database():
        await backend.ensure_ready()
        return await backend.applied()

    applied = run_with_database(project, state_of_database)

    found = problems(graph, applied)
    if found:
        for line in found:
            typer.secho(line, fg="red", err=True)
        fail("The migrations and the record of them in the database do not agree")

    todo = pending(graph, applied)
    if not todo:
        typer.echo("Nothing to apply")
        warn_if_models_have_changed(graph, snapshot)
        return
    if check:
        typer.echo(f"{len(todo)} migrations to apply")
        raise typer.Exit(1)

    typer.echo("To apply:")
    for migration in todo:
        typer.secho(f"  {migration}", bold=True)
        for line in describe(migration):
            typer.echo(line)
    if plan_only:
        return

    applied_keys = [key for key, record in applied.items() if record.get("status") == "applied"]
    state = graph.state(applied_keys) if applied_keys else {"version": 1, "models": {}, "enums": {}}

    if dry_run:
        reports = run_with_database(project, lambda: backend.dry_run(todo, state))
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
        return

    lossy = [m for m in todo for ch in m.changes if ch.safety == "lossy"]
    if lossy and not fake and not yes:
        typer.confirm("Some of these lose data. Go on?", abort=True)

    def progress(migration: Migration, what: str) -> None:
        typer.echo(f"  {migration}: {what}")

    async def run_all():
        await backend.lock()
        try:
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
                typer.echo(f"Models the migrations could have made unreadable: {', '.join(affected)}")
                report_data_check(project, types=affected)
            else:
                typer.echo("Nothing that exists is affected by these migrations: no data to read")


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
    graph = load_graph(apps)
    backend = migration_backend(project)

    async def read():
        await backend.ensure_ready()
        return await backend.applied()

    applied = run_with_database(project, read)
    for app in apps:
        own = [m for m in graph.order() if m.app == app]
        if not own:
            continue
        typer.secho(app, bold=True)
        for migration in own:
            record = applied.get(migration.key, {})
            status = record.get("status")
            mark = {"applied": "[X]", "failed": "[!]", "running": "[~]"}.get(status, "[ ]")
            note = " (faked)" if record.get("fake") else ""
            typer.echo(f" {mark} {migration.name}{note}")
    for line in problems(graph, applied):
        typer.secho(line, fg="red", err=True)


def report_data_check(project: Project, types: list[str] | None = None, limit: int | None = None) -> None:
    """Read the data with the models, and say what cannot be read (exit 1 if anything)"""
    typer.echo("Reading the data with the models ...")
    check = run_with_database(project, lambda: check_data(types=types, limit=limit))
    if check.ok:
        typer.secho(f"All {check.checked} can be read", fg="green")
        return
    typer.secho(f"{len(check.problems)} of {check.checked} cannot be read:", fg="red", err=True)
    for problem in check.problems[:20]:
        typer.secho(f"  {problem}", fg="red", err=True)
    if len(check.problems) > 20:
        typer.secho(f"  ... and {len(check.problems) - 20} more", fg="red", err=True)
    raise typer.Exit(1)


def check_data_command(
    ctx: typer.Context,
    type: list[str] = typer.Option([], "--type", "-t", help="Only this model (more than once for more)"),
    limit: int | None = typer.Option(None, "--limit", help="At most this many of each model"),
) -> None:
    """Read all the data with the models as they are, and report what cannot be read

    Run after a migration (`migrate` does), or to find what the models and the data no longer
    agree about."""
    project: Project = ctx.obj
    load_models(project)
    report_data_check(project, types=type or None, limit=limit)
