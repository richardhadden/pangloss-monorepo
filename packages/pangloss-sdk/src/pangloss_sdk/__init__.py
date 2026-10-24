"""Use a Pangloss project's models against its API.

    await pangloss_sdk.connect("https://pangloss.example.org", apps=["demo_app"])
    from demo_app.models import Person
    person = await Person.get(id)

See `docs/sdk.md`.
"""

import importlib
from collections.abc import Iterable
from typing import Any

from pangloss_sdk import client as _client
from pangloss_sdk.auth import Prompt
from pangloss_sdk.exceptions import (
    PanglossAuthenticationError,
    PanglossAuthenticationRequired,
    PanglossConnectionError,
    PanglossNotConnected,
    PanglossPermissionError,
    PanglossRequestError,
    PanglossSdkError,
    PanglossSdkMismatch,
    PanglossSdkOutOfDate,
    PanglossSdkOutOfDateWarning,
    PanglossServerError,
)
from pangloss_sdk.iterate import iterate, iterate_sync
from pangloss_sdk.settings import (
    ASYNC_DATABASE_MODULE,
    SYNC_DATABASE_MODULE,
    SdkSettings,
)
from pangloss_sdk.status import check, check_sync

__all__ = (
    "PanglossAuthenticationError",
    "PanglossAuthenticationRequired",
    "PanglossConnectionError",
    "PanglossNotConnected",
    "PanglossPermissionError",
    "PanglossRequestError",
    "PanglossSdkError",
    "PanglossSdkMismatch",
    "PanglossSdkOutOfDate",
    "PanglossSdkOutOfDateWarning",
    "PanglossServerError",
    "SdkSettings",
    "check",
    "check_sync",
    "connect",
    "connect_offline",
    "disconnect",
    "disconnect_sync",
    "iterate",
    "iterate_sync",
)


def connect(
    url: str | None = None,
    *,
    apps: Iterable[str] = (),
    sync: bool = False,
    transport: Any = None,
    prompt: Prompt | None = None,
    sdk: dict[str, Any] | None = None,
    **settings: Any,
) -> None:
    """Connect to a Pangloss API: makes the settings, imports `<app>.models` of each app,
    and initialises the models, with the model functions bound to requests.

    `sync=True` binds the blocking functions (a script or a notebook with no event loop to
    spare); the default is async, like the server's own. `username`, `password` and `token`
    are optional: a login is asked for when a request needs one. Any of the settings can
    be in the environment instead (`PANGLOSS_URL`, ...). `sdk` is the manifest of a generated SDK,
    which tells the server which one this is (so it can say when it is out of date). `transport`
    is for tests."""
    from pangloss_models import initialise

    if url is not None:
        settings["URL"] = url
    app_list = list(apps)
    for key in ("username", "password", "token"):
        if key in settings:
            settings[key.upper()] = settings.pop(key)
    configured = SdkSettings(  # type: ignore[call-arg]
        INSTALLED_APPS=app_list,
        DATABASE_MODULE=SYNC_DATABASE_MODULE if sync else ASYNC_DATABASE_MODULE,
        **settings,
    )
    _client.install(
        _client.Client(configured, transport, prompt, sdk)
        if sync
        else _client.AsyncClient(configured, transport, prompt, sdk)
    )
    for app in app_list:
        importlib.import_module(f"{app}.models")
    initialise()


def connect_offline(apps: Iterable[str]) -> None:
    """Import and initialise the models of the apps with no server: the model functions
    are bound to the API, and fail if used. For checking that an SDK imports and that its
    models are the server's."""
    from pangloss_core.settings import ClientSettings
    from pangloss_models import initialise

    app_list = list(apps)
    ClientSettings(INSTALLED_APPS=app_list, DATABASE_MODULE=ASYNC_DATABASE_MODULE)
    for app in app_list:
        importlib.import_module(f"{app}.models")
    initialise()


async def disconnect() -> None:
    """Close the connections (the blocking client is closed by `disconnect_sync`)"""
    if _client._async_client is not None:
        await _client._async_client.close()
    _client.install(None)


def disconnect_sync() -> None:
    if _client._client is not None:
        _client._client.close()
    _client.install(None)
