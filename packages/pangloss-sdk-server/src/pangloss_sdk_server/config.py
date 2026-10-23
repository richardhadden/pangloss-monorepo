"""The settings of the SDK builder, read from the project's settings if it has them"""

from pathlib import Path
from typing import Any

from pangloss_core import settings as core_settings

DEFAULT_OUTPUT = ".pangloss/sdk"


def setting(name: str, default: Any, settings: Any = None) -> Any:
    settings = settings or core_settings.__dict__.get("SETTINGS")
    return getattr(settings, name, default)


def output_directory(root: Path, settings: Any = None) -> Path:
    path = Path(setting("SDK_OUTPUT", DEFAULT_OUTPUT, settings))
    return path if path.is_absolute() else root / path
