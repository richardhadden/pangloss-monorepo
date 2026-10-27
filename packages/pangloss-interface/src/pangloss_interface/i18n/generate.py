"""`generate`: write or update the translation file of each app, and make the project's override files."""

from dataclasses import dataclass, field
from pathlib import Path as FilePath
from typing import Any

from pangloss_interface.i18n import files
from pangloss_interface.i18n.extract import Extracted
from pangloss_interface.i18n.merge import ItemRename, Report, reconcile

OVERRIDE_HEADER = [
    "The project's own texts: they win over those of the apps. Same form as an app's models.jsonc",
    "(models / enums, then the name, the language, and the texts); put only what you want different.",
    "`pangloss interface translations generate` never changes this file.",
]
UI_HEADER = [
    'The project\'s own texts for the page, and its slots: {"log_in": {"en": "Log in", "de": "Anmelden"}}.',
    "`pangloss interface translations generate` never changes this file.",
]


@dataclass
class AppResult:
    app: str
    directory: FilePath | None = None
    report: Report | None = None
    written: bool = False
    skipped: str | None = None


@dataclass
class Generated:
    apps: list[AppResult] = field(default_factory=list)
    created: list[FilePath] = field(default_factory=list)


def languages_of(settings: Any) -> tuple[str, list[str]]:
    """The default language, and every language (the default first) of the settings"""
    default = settings.DEFAULT_INTERFACE_LANGUAGE
    others = [lang for lang in settings.INTERFACE_LANGUAGES if lang != default]
    return default, [default, *dict.fromkeys(others)]


def project_folder(root: FilePath) -> FilePath:
    return root / files.FOLDER


def ensure_project_files(root: FilePath) -> list[FilePath]:
    """The project's override files, empty, if they are not there; those made"""
    from pangloss_interface.i18n import jsonc

    made = []
    for name, header in (
        (files.MODELS_FILE, OVERRIDE_HEADER),
        (files.UI_FILE, UI_HEADER),
    ):
        path = project_folder(root) / name
        if not path.exists():
            files.write_if_changed(path, jsonc.render({}, header=header))
            made.append(path)
    return made


def generate(
    root: FilePath,
    extracted: Extracted,
    apps: list[str],
    default: str,
    languages: list[str],
    renames: list[ItemRename],
    only: str | None = None,
    prune: bool = False,
    dry_run: bool = False,
) -> Generated:
    """Bring the files of the apps (all that have models, or `only` one) up to date"""
    result = Generated()
    for app in apps:
        if only not in (None, app):
            continue
        generated = extracted.texts_of(app)
        if not generated:
            continue
        directory = files.app_directory(app)
        if directory is None or not files.in_project(directory, root):
            result.apps.append(
                AppResult(
                    app,
                    directory,
                    skipped="not part of the project (use the project's overrides)",
                )
            )
            continue
        folder = directory / files.FOLDER
        existing = files.read_models_file(folder, languages)
        outcome = reconcile(
            generated,
            languages,
            default,
            existing.texts,
            existing.obsolete,
            existing.state,
            renames,
            prune,
        )
        written = False
        if not dry_run:
            written = files.write_models_file(
                folder,
                outcome.texts,
                outcome.obsolete,
                outcome.state,
                default,
                existing.comments,
            )
        result.apps.append(AppResult(app, folder, outcome.report, written))
    if not dry_run and only is None:
        result.created = ensure_project_files(root)
    return result
