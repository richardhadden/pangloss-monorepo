"""Who the client is logged in as, and how it gets a login.

Reads need no login. A request that does gets, in order: the tokens already held (an access
token, renewed with the refresh token); the username and password in the settings; and, if
there is a terminal, a prompt. Without one, `PanglossAuthenticationRequired`. The password is
used to ask for the tokens and is not kept; the tokens are kept in memory only.
"""

import dataclasses
import getpass
import sys
from collections.abc import Callable
from typing import Any

from pangloss_sdk import credentials
from pangloss_sdk.exceptions import (
    PanglossAuthenticationError,
    PanglossAuthenticationRequired,
)
from pangloss_sdk.settings import SdkSettings

LOGIN_PATH = "/api/users/token"
REFRESH_PATH = "/api/users/token/refresh"

# How many times a wrong password at the prompt is asked for again
PROMPT_ATTEMPTS = 3

type Prompt = Callable[[str, str | None], tuple[str, str]]
"""Asks for a username and password: given the server's address and a username to suggest"""


def terminal_prompt(url: str, username: str | None) -> tuple[str, str]:
    print(f"Pangloss login for {url}", file=sys.stderr)
    suggestion = f" [{username}]" if username else ""
    entered = input(f"Username{suggestion}: ").strip()
    password = getpass.getpass("Password: ")
    return entered or username or "", password


def can_prompt() -> bool:
    """A terminal, or a notebook, that can be asked"""
    if "ipykernel" in sys.modules:
        return True
    try:
        return sys.stdin is not None and sys.stdin.isatty()
    except ValueError:  # (closed)
        return False


@dataclasses.dataclass
class Session:
    settings: SdkSettings
    prompt: Prompt | None = None
    access_token: str | None = None
    refresh_token: str | None = None
    username: str | None = None
    # What the settings gave is tried once; after that a failure is asked about
    _settings_tried: bool = False
    _prompts: int = 0

    def __post_init__(self) -> None:
        self.username = self.settings.USERNAME
        if self.settings.TOKEN is not None:
            self.access_token = self.settings.TOKEN.get_secret_value()
        elif self.settings.USE_STORED_LOGIN and not self.has_credentials():
            self.use_stored_login()

    def use_stored_login(self) -> None:
        """A login kept by `pangloss-sdk login`: a refresh token (to get access tokens with),
        or a personal access token (used as it is)"""
        stored = credentials.load(self.url)
        if not stored:
            return
        self.username = stored.get("username", self.username)
        if "token" in stored:
            self.access_token = stored["token"]
        else:
            self.refresh_token = stored.get("refresh_token")

    @property
    def url(self) -> str:
        return str(self.settings.URL).rstrip("/")

    def has_credentials(self) -> bool:
        return self.settings.USERNAME is not None and self.settings.PASSWORD is not None

    def credentials(self) -> tuple[str, str]:
        """A username and password to log in with, or raise: the settings the first time,
        then the prompt"""
        settings = self.settings
        if not self._settings_tried and self.has_credentials():
            self._settings_tried = True
            assert settings.USERNAME is not None and settings.PASSWORD is not None
            return settings.USERNAME, settings.PASSWORD.get_secret_value()

        asker = self.prompt or (terminal_prompt if can_prompt() else None)
        if asker is None and self._settings_tried:
            raise PanglossAuthenticationError(
                "The username and password were refused by the server"
            )
        if asker is None:
            raise PanglossAuthenticationRequired(
                "A login is needed, and there is no way to ask for one: set "
                "PANGLOSS_USERNAME and PANGLOSS_PASSWORD (or PANGLOSS_TOKEN), or give "
                "them to connect()"
            )
        if self._prompts >= PROMPT_ATTEMPTS:
            raise PanglossAuthenticationError("Too many failed logins")
        self._prompts += 1
        return asker(self.url, self.username)

    def login_form(self) -> dict[str, str]:
        username, password = self.credentials()
        self.username = username
        return {"username": username, "password": password}

    def accept(self, body: dict[str, Any]) -> None:
        """Keep the tokens of a login or a refresh"""
        self.access_token = body["access_token"]
        # (a refresh answers with an access token only)
        self.refresh_token = body.get("refresh_token", self.refresh_token)
        # (the settings can log in again when the tokens run out)
        self._prompts = 0
        self._settings_tried = False

    def forget(self) -> None:
        self.access_token = None
        self.refresh_token = None

    def headers(self) -> dict[str, str]:
        if self.access_token:
            return {"Authorization": f"Bearer {self.access_token}"}
        return {}
