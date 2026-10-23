"""Keeping a login between runs, only when the user says so (`pangloss-sdk login`).

What is kept is a **refresh token** (never the password), or a personal access token, for one
server URL: in the operating system's keyring if `keyring` is installed and has a backend,
else in a file only the user can read (`~/.config/pangloss/credentials.json`, mode 600, in a
directory of mode 700). A client reads it when it has no other login; `pangloss-sdk logout`
revokes the token on the server and removes it here.

`PANGLOSS_CREDENTIALS_FILE` names another file, and `PANGLOSS_NO_KEYRING=1` keeps to a file.
"""

import json
import os
import stat
import warnings
from pathlib import Path
from typing import Any

SERVICE = "pangloss"


def normalise(url: str) -> str:
    return url.rstrip("/").lower()


def credentials_file() -> Path:
    if configured := os.environ.get("PANGLOSS_CREDENTIALS_FILE"):
        return Path(configured)
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "pangloss" / "credentials.json"


def keyring_module() -> Any | None:
    """The `keyring` module, if it is installed and has a backend that can keep things"""
    if os.environ.get("PANGLOSS_NO_KEYRING"):
        return None
    try:
        import keyring  # ty: ignore[unresolved-import]
        from keyring.backends import fail  # ty: ignore[unresolved-import]
    except ImportError:
        return None
    return None if isinstance(keyring.get_keyring(), fail.Keyring) else keyring


def read_file() -> dict[str, Any]:
    path = credentials_file()
    try:
        mode = path.stat().st_mode
    except FileNotFoundError:
        return {}
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        warnings.warn(
            f"{path} can be read by others, so it is not used: chmod 600 it, or log in again",
            stacklevel=3,
        )
        return {}
    try:
        data = json.loads(path.read_text())
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def write_file(data: dict[str, Any]) -> None:
    path = credentials_file()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as file:
        file.write(json.dumps(data, indent=2))
    path.chmod(0o600)


def load(url: str) -> dict[str, Any] | None:
    """What is kept for the server: `{"refresh_token": ..., "username": ...}` or `{"token": ...}`"""
    key = normalise(url)
    if (keyring := keyring_module()) is not None:
        stored = keyring.get_password(SERVICE, key)
        if stored:
            return json.loads(stored)
    return read_file().get(key)


def save(url: str, entry: dict[str, Any]) -> str:
    """Keep a login for the server. Returns where: `keyring` or the file's path"""
    key = normalise(url)
    if (keyring := keyring_module()) is not None:
        keyring.set_password(SERVICE, key, json.dumps(entry))
        return "the keyring"
    data = read_file()
    data[key] = entry
    write_file(data)
    return str(credentials_file())


def forget(url: str) -> bool:
    """Remove what is kept for the server: whether there was anything"""
    key = normalise(url)
    found = False
    if (keyring := keyring_module()) is not None:
        if keyring.get_password(SERVICE, key):
            keyring.delete_password(SERVICE, key)
            found = True
    data = read_file()
    if key in data:
        del data[key]
        write_file(data)
        found = True
    return found
