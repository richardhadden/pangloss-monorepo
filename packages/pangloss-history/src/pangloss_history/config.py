"""The settings of history, read from the project's settings if it has them"""

from pathlib import Path
from typing import Any

from pangloss_core import settings as core_settings

DEFAULT_DB_PATH = ".pangloss/history.sqlite3"
DEFAULT_QUEUE_SIZE = 1000
DEFAULT_BATCH_SIZE = 100
DEFAULT_BATCH_MS = 50


def setting(name: str, default: Any, settings: Any = None) -> Any:
    settings = settings or core_settings.__dict__.get("SETTINGS")
    return getattr(settings, name, default)


def db_path(settings: Any = None) -> Path:
    return Path(setting("HISTORY_DB_PATH", DEFAULT_DB_PATH, settings))


def excluded_models(settings: Any = None) -> set[str]:
    return set(setting("HISTORY_EXCLUDE", [], settings))
