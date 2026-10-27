"""The settings of Zotero, read from the project's settings if it has them"""

from typing import Any

from pangloss_core import settings as core_settings

DEFAULT_API_URL = "https://api.zotero.org"
DEFAULT_STREAM_URL = "wss://stream.zotero.org"
DEFAULT_SKIP_TYPES = ("attachment", "note", "annotation")
DEFAULT_SYNC_USER = "zotero_sync"
BATCH_SIZE = 50  # (the most keys Zotero gives items for in one request)


def setting(name: str, default: Any, settings: Any = None) -> Any:
    settings = settings or core_settings.__dict__.get("SETTINGS")
    return getattr(settings, name, default)


def api_key(settings: Any = None) -> str | None:
    return setting("ZOTERO_API_KEY", None, settings) or None


def libraries(settings: Any = None) -> list[str]:
    return list(setting("ZOTERO_LIBRARIES", [], settings))


def watch_wanted(settings: Any = None) -> bool:
    """Whether the server runs the watcher: on unless turned off, if there is a key and a library"""
    return bool(
        setting("ZOTERO_WATCH", True, settings)
        and api_key(settings)
        and libraries(settings)
    )


def skip_types(settings: Any = None) -> set[str]:
    return set(setting("ZOTERO_SKIP_TYPES", DEFAULT_SKIP_TYPES, settings))


def sync_user(settings: Any = None) -> str:
    return setting("ZOTERO_SYNC_USER", DEFAULT_SYNC_USER, settings)


def api_url(settings: Any = None) -> str:
    return setting("ZOTERO_API_URL", DEFAULT_API_URL, settings).rstrip("/")


def stream_url(settings: Any = None) -> str:
    return setting("ZOTERO_STREAM_URL", DEFAULT_STREAM_URL, settings)
