"""Finding and loading a Pangloss project: its settings, installed apps and database.

The settings are found, in this order, from:

1. `--settings <module>` on the command line;
2. the environment variable `PANGLOSS_SETTINGS`;
3. `[tool.pangloss] settings = "<module>"` in the `pyproject.toml` of the current
   directory, or of the nearest directory above it that has one with that setting.

The module is imported, which (as `BaseSettings` records itself when constructed)
sets the settings for the whole of Pangloss.
"""

import importlib
import os
import sys
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

import typer
from pangloss_core import settings as core_settings
from pangloss_core.settings import BaseSettings

SETTINGS_ENVIRONMENT_VARIABLE = "PANGLOSS_SETTINGS"
SETTINGS_OPTION = "--settings"

NO_SETTINGS_MESSAGE = (
    "No settings found. Give the module with --settings, set PANGLOSS_SETTINGS, or "
    'put\n\n[tool.pangloss]\nsettings = "your_project.settings"\n\nin pyproject.toml'
)


@dataclass
class SettingsLocation:
    module: str
    # The directory to import it from
    root: Path


def settings_option_from(argv: Sequence[str]) -> str | None:
    """The value of `--settings`, from the command line (it is needed before the
    commands are known, as the settings say which apps add commands)"""
    for index, argument in enumerate(argv):
        if argument == SETTINGS_OPTION and index + 1 < len(argv):
            return argv[index + 1]
        if argument.startswith(f"{SETTINGS_OPTION}="):
            return argument.split("=", 1)[1]
    return None


def settings_from_pyproject(directory: Path) -> SettingsLocation | None:
    for candidate in (directory, *directory.parents):
        pyproject = candidate / "pyproject.toml"
        if not pyproject.is_file():
            continue
        try:
            data = tomllib.loads(pyproject.read_text())
        except tomllib.TOMLDecodeError:
            continue
        module = data.get("tool", {}).get("pangloss", {}).get("settings")
        if module:
            return SettingsLocation(module=module, root=candidate)
    return None


def find_settings(
    argv: Sequence[str], environment: Mapping[str, str], directory: Path
) -> SettingsLocation | None:
    if module := settings_option_from(argv):
        return SettingsLocation(module=module, root=directory)
    if module := environment.get(SETTINGS_ENVIRONMENT_VARIABLE):
        return SettingsLocation(module=module, root=directory)
    return settings_from_pyproject(directory)


def import_if_present(name: str) -> ModuleType | None:
    """Import a module, or return None if there is no such module. (An error inside
    a module that exists is not hidden.)"""
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as error:
        if error.name and (name == error.name or name.startswith(f"{error.name}.")):
            return None
        raise


def app_command_group(app: str) -> typer.Typer | None:
    """The Typer object named `cli` in `<app>/cli.py`, if the app has one"""
    module = import_if_present(f"{app}.cli")
    if module is None:
        return None
    group = getattr(module, "cli", None)
    if not isinstance(group, typer.Typer):
        raise TypeError(f"{app}.cli has no Typer object named 'cli'")
    return group


def group_name(app: str, group: typer.Typer) -> str:
    """`pangloss <name> <command>`: the name the group gives itself, or that of the
    app without a `pangloss_` prefix"""
    return group.info.name or app.removeprefix("pangloss_")


@dataclass
class Project:
    settings: BaseSettings | None = None
    # Where the settings are, if a project was found (even if it cannot be loaded)
    location: SettingsLocation | None = None
    # Why there are no settings, or the database is not available
    settings_error: str | None = None
    database_error: str | None = None
    backend: ModuleType | None = None
    # (app, why its commands could not be added)
    app_errors: list[tuple[str, str]] = field(default_factory=list)

    def require_settings(self) -> BaseSettings:
        if self.settings is None:
            fail(self.settings_error or NO_SETTINGS_MESSAGE)
        assert self.settings is not None
        return self.settings

    def require_database(self) -> ModuleType:
        self.require_settings()
        if self.backend is None:
            fail(self.database_error or "The database could not be set up")
        assert self.backend is not None
        return self.backend

    def import_models(self) -> None:
        """Import the `models` module of each installed app, which registers them"""
        for app in self.require_settings().INSTALLED_APPS:
            import_if_present(f"{app}.models")


def fail(message: str, code: int = 1):
    typer.secho(message, fg="red", err=True)
    raise typer.Exit(code)


def load_settings(location: SettingsLocation) -> BaseSettings:
    root = str(location.root)
    if root not in sys.path:
        sys.path.insert(0, root)

    try:
        importlib.import_module(location.module)
    except ModuleNotFoundError as error:
        if error.name and location.module.startswith(error.name):
            raise ImportError(f"There is no settings module '{location.module}'")
        raise

    settings = getattr(core_settings, "SETTINGS", None)
    if settings is None:
        raise ImportError(
            f"'{location.module}' was imported, but did not create the settings: it "
            "should construct an instance of its BaseSettings subclass"
        )
    return settings


def load_database(settings: BaseSettings) -> ModuleType:
    """The `setup` module of the database backend, having made its database object"""
    backend = importlib.import_module(f"{settings.DATABASE_MODULE}.setup")
    backend.create_database(settings)
    return backend


def load_project(
    argv: Sequence[str] | None = None,
    environment: Mapping[str, str] | None = None,
    directory: Path | None = None,
) -> Project:
    """Find and load the settings and the database backend. This does not stop at an
    error, so that `pangloss --help` and the like work without a project: the error
    is kept, and shown by a command that needs what is missing."""
    argv = sys.argv[1:] if argv is None else argv
    environment = os.environ if environment is None else environment
    directory = Path.cwd() if directory is None else directory

    project = Project()

    location = find_settings(argv, environment, directory)
    if location is None:
        project.settings_error = NO_SETTINGS_MESSAGE
        return project

    project.location = location
    try:
        project.settings = load_settings(location)
    except Exception as error:
        project.settings_error = (
            f"Cannot load the settings '{location.module}': {error}"
        )
        return project

    try:
        project.backend = load_database(project.settings)
    except Exception as error:
        project.database_error = (
            f"Cannot load the database '{project.settings.DATABASE_MODULE}': {error}"
        )

    return project
