"""`pangloss interface translations <command>`: make, gather and check the translation files.

See `docs/translations.md`. They need the project's models (to know what there is to translate)."""

import json
from pathlib import Path
from typing import Any

import typer

from pangloss_interface.i18n import files
from pangloss_interface.i18n.check import check as run_check
from pangloss_interface.i18n.check import failing
from pangloss_interface.i18n.extract import Extracted, extract
from pangloss_interface.i18n.gather import gather as run_gather
from pangloss_interface.i18n.generate import generate as run_generate
from pangloss_interface.i18n.generate import languages_of
from pangloss_interface.i18n.renames import rename_steps, unmigrated
from pangloss_interface.i18n.resolve import Layers, load_layers
from pangloss_interface.workspace import TRANSLATIONS_PATH, working_directory

translations = typer.Typer(
    name="translations",
    help="The texts of the interface in each language",
    no_args_is_help=True,
)


# What the interface gets when the translations cannot be gathered
NO_TRANSLATIONS = {
    "default": "en",
    "languages": ["en"],
    "ui": {"en": {}},
    "models": {"en": {}},
    "enums": {"en": {}},
}


def gathered_text(project: Any, exported: dict[str, Any]) -> str:
    """The gathered translations of the project, as the JSON the interface loads"""
    settings = project.require_settings()
    apps = list(settings.INSTALLED_APPS)
    default, languages = languages_of(settings)
    extracted = extract(exported, apps)
    layers = load_layers(project.location.root, extracted, apps, default, languages)
    return json.dumps(run_gather(layers), indent=2, ensure_ascii=False) + "\n"


def write_translations(project: Any, exported: dict[str, Any], target: Path) -> None:
    """Gather the translations into the file the interface imports (when it is prepared). A file that
    cannot be read is a warning, not a stop: the interface can be built without translations"""
    try:
        text = gathered_text(project, exported)
    except files.TranslationFileError as error:
        typer.secho(f"Translations not gathered: {error}", fg="yellow", err=True)
        text = None
        if not target.is_file():
            # (the interface imports the file, so there has to be one: English only, with nothing in it)
            text = json.dumps(NO_TRANSLATIONS, indent=2) + "\n"
    if text is not None:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.is_file() or target.read_text(encoding="utf-8") != text:
            target.write_text(text, encoding="utf-8")
            typer.echo(f"  wrote {target.name}")


def fail(message: str) -> typer.Exit:
    typer.secho(message, fg="red", err=True)
    return typer.Exit(1)


def loaded(ctx: typer.Context) -> tuple[Any, Extracted, str, list[str], list[str]]:
    """The project, what its models give, the default language, the languages and the apps"""
    from pangloss_interface.cli import export_or_exit, project_of

    project = project_of(ctx)
    settings = project.require_settings()
    apps = list(settings.INSTALLED_APPS)
    extracted = extract(export_or_exit(project), apps)
    default, languages = languages_of(settings)
    return project, extracted, default, languages, apps


def layers_or_exit(
    project: Any,
    extracted: Extracted,
    apps: list[str],
    default: str,
    languages: list[str],
) -> Layers:
    try:
        return load_layers(project.location.root, extracted, apps, default, languages)
    except files.TranslationFileError as error:
        raise fail(str(error)) from error


@translations.command()
def generate(
    ctx: typer.Context,
    app: str | None = typer.Option(None, "--app", help="Only this app"),
    prune: bool = typer.Option(
        False, "--prune", help="Remove what is under _obsolete (names that have gone)"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Say what would change, and write nothing"
    ),
    strict: bool = typer.Option(
        False, "--strict", help="Fail if the models have changes with no migration"
    ),
) -> None:
    """Write or update each app's translations/models.jsonc

    What a person has written is kept; texts that have not been edited follow the models; a text
    that is edited and whose model has changed is marked NEEDS REVIEW."""
    project, extracted, default, languages, apps = loaded(ctx)
    if app is not None and app not in apps:
        raise fail(f"{app} is not one of the INSTALLED_APPS")

    pending = unmigrated(apps)
    if pending:
        typer.secho(
            "The models have changes with no migration (run `pangloss makemigrations` first: "
            "a rename is only carried over to the new name once a migration records it):",
            fg="yellow",
            err=True,
        )
        for line in pending:
            typer.secho(f"  - {line}", fg="yellow", err=True)
        if strict:
            raise fail("--strict: not going on")

    try:
        done = run_generate(
            project.location.root,
            extracted,
            apps,
            default,
            languages,
            rename_steps(apps),
            only=app,
            prune=prune,
            dry_run=dry_run,
        )
    except files.TranslationFileError as error:
        raise fail(str(error)) from error

    root = project.location.root
    if not done.apps:
        typer.echo("No app has models to translate.")
    for result in done.apps:
        if result.skipped:
            typer.echo(f"{result.app}: skipped, {result.skipped}")
            continue
        report = result.report
        assert report is not None and result.directory is not None
        shown = (result.directory / files.MODELS_FILE).relative_to(root, walk_up=True)
        verb = (
            "would write" if dry_run else ("wrote" if result.written else "unchanged")
        )
        typer.echo(f"{result.app}: {verb} {shown}")
        for label, paths in (
            ("added", report.added),
            ("followed the models", report.followed),
            ("moved to a new name", report.moved),
            ("put in _obsolete", report.obsolete),
            ("removed from _obsolete", report.pruned),
            ("need review", report.review),
        ):
            if paths:
                typer.echo(f"  {len(paths):>5} {label}")
    for path in done.created:
        typer.echo(f"made {path.relative_to(root)}")


@translations.command()
def gather(
    ctx: typer.Context,
    out: Path | None = typer.Option(
        None,
        "--out",
        "-o",
        help=f"The file to write (default: .pangloss/interface/{TRANSLATIONS_PATH})",
    ),
) -> None:
    """Merge the apps' files, the project's overrides and the interface's own into one JSON file"""
    project, extracted, default, languages, apps = loaded(ctx)
    layers = layers_or_exit(project, extracted, apps, default, languages)
    target = out or working_directory(project.location.root) / TRANSLATIONS_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(run_gather(layers), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    typer.echo(f"Wrote {target} ({', '.join(languages)})")


@translations.command()
def check(
    ctx: typer.Context,
    lang: str | None = typer.Option(None, "--lang", help="Only this language"),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Fail on texts that need review and on names that point at nothing too",
    ),
) -> None:
    """List what is missing in a language (exit code 1 if anything is)"""
    project, extracted, default, languages, apps = loaded(ctx)
    if lang is not None and lang not in languages:
        raise fail(f"{lang} is not one of the languages ({', '.join(languages)})")
    layers = layers_or_exit(project, extracted, apps, default, languages)
    problems = run_check(layers, lang)
    for problem in problems:
        typer.echo(str(problem))
    missing = sum(p.kind == "missing" for p in problems)
    typer.echo(
        f"{missing} missing, {sum(p.kind == 'review' for p in problems)} to review, "
        f"{sum(p.kind == 'unknown' for p in problems)} pointing at nothing"
    )
    if failing(problems, strict):
        raise typer.Exit(1)
