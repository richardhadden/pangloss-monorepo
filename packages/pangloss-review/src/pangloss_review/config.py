"""The settings of review, read from the project's settings if it has them"""

from typing import Any

from pangloss_core import settings as core_settings


def setting(name: str, default: Any, settings: Any = None) -> Any:
    settings = settings or core_settings.__dict__.get("SETTINGS")
    return getattr(settings, name, default)


def allow_self_review(settings: Any = None) -> bool:
    return bool(setting("REVIEW_ALLOW_SELF_REVIEW", True, settings))
