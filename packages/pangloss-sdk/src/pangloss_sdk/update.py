"""`pangloss-sdk update`: bring the installed SDK to what the server has now, with the command
that matches how it was installed (what `direct_url.json` in its metadata says):

| Installed from | What is run |
|-|-|
| the server's wheel (`pip install https://host/api/sdk/download/…whl`) | the server is asked for the SDK it has now; if the version differs, that wheel is installed (logging in as `login` does, if the server wants it) |
| `git clone` / `git+https://…` | the install again from that repository |
| an index | an upgrade of the package by name |
| a local directory (editable or not) | nothing: update the directory (`git pull`), and the installed copy follows if it is editable |

`uv pip` is used if `uv` is installed, else `pip`.
"""

import base64
import dataclasses
import importlib.metadata as metadata
import json
import re
import shutil
import sys
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

import httpx2 as httpx

from pangloss_sdk import credentials
from pangloss_sdk.auth import can_prompt, terminal_prompt

MARKER = "pangloss-sdk"
NOT_CLIENTS = {"pangloss-sdk", "pangloss-sdk-server"}


class UpdateError(Exception):
    pass


@dataclasses.dataclass
class Plan:
    message: str
    # What to run (None if there is nothing to run); `shown` is the same with passwords hidden
    command: list[str] | None = None
    shown: str | None = None


def normalise(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def sdk_distributions() -> list[metadata.Distribution]:
    """The installed distributions that are a project's SDK: they need `pangloss-sdk`"""
    found = []
    for distribution in metadata.distributions():
        name = normalise(distribution.metadata["Name"] or "")
        if name in NOT_CLIENTS:
            continue
        for requirement in distribution.requires or []:
            if normalise(re.split(r"[ ;<>=!~\[(@]", requirement, maxsplit=1)[0]) == MARKER:
                found.append(distribution)
                break
    return found


def choose(package: str | None, distributions: list[metadata.Distribution]) -> metadata.Distribution:
    if package:
        for distribution in distributions:
            if normalise(distribution.metadata["Name"]) == normalise(package):
                return distribution
        raise UpdateError(f"'{package}' is not installed here, or is not a Pangloss SDK")
    if not distributions:
        raise UpdateError("No Pangloss SDK is installed here (a package that needs pangloss-sdk)")
    if len(distributions) > 1:
        names = ", ".join(sorted(d.metadata["Name"] for d in distributions))
        raise UpdateError(f"There are several SDKs installed ({names}): say which")
    return distributions[0]


def installer(spec: str) -> list[str]:
    if shutil.which("uv"):
        return ["uv", "pip", "install", "--python", sys.executable, "--upgrade", spec]
    return [sys.executable, "-m", "pip", "install", "--upgrade", spec]


def server_base(url: str) -> str | None:
    """The server (and its path prefix) that a wheel was downloaded from, without a login in it"""
    parts = urlsplit(url)
    marker = parts.path.find("/api/sdk/")
    if marker < 0 or parts.scheme not in ("http", "https"):
        return None
    host = parts.netloc.rpartition("@")[2]
    return urlunsplit((parts.scheme, host, parts.path[:marker], "", ""))


def with_login(url: str, username: str, password: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(parts._replace(netloc=f"{quote(username, safe='')}:{quote(password, safe='')}@{parts.netloc}"))


def basic(username: str, password: str) -> dict[str, str]:
    encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {encoded}"}


def login_for_download(base: str, http: httpx.Client, prompt: Any) -> tuple[str, str] | None:
    """What to give as the username and password to download the SDK: None if the server
    gives it to anyone. The kept login is used (a refresh token gives an access token, which
    the server takes as a password); if there is none, the user is asked."""
    if http.get(f"{base}/api/sdk").status_code == 200:
        return None

    stored = credentials.load(base)
    if stored and "token" in stored:
        return stored.get("username", "token"), stored["token"]
    if stored and "refresh_token" in stored:
        refreshed = http.post(f"{base}/api/users/token/refresh", json={"refresh_token": stored["refresh_token"]})
        if refreshed.status_code == 200:
            return stored.get("username", ""), refreshed.json()["access_token"]
    if prompt is None and not can_prompt():
        raise UpdateError(f"{base} wants a login: run `pangloss-sdk login {base}` first")
    username, password = (prompt or terminal_prompt)(base, stored.get("username") if stored else None)
    return username, password


def plan_from_server(
    distribution: metadata.Distribution, base: str, transport: Any, prompt: Any
) -> Plan:
    name = distribution.metadata["Name"]
    with httpx.Client(timeout=30, transport=transport) as http:
        try:
            version = http.get(f"{base}/api/sdk/version")
        except httpx.TransportError as error:
            raise UpdateError(f"{base} could not be reached: {error}") from error
        if version.status_code != 200:
            raise UpdateError(f"{base} has no SDK to give (it answered {version.status_code})")
        latest = version.json()
        if normalise(latest["distribution"]) != normalise(name):
            raise UpdateError(
                f"{base} now makes the SDK '{latest['distribution']}', not '{name}'"
            )
        if latest["version"] == distribution.version:
            return Plan(f"{name} {distribution.version} is the latest on {base}")

        login = login_for_download(base, http, prompt)
        headers = basic(*login) if login else {}
        manifest = http.get(f"{base}/api/sdk", headers=headers)
        if manifest.status_code != 200:
            raise UpdateError(f"{base} refused the login for the SDK ({manifest.status_code})")
        wheel = manifest.json()["downloads"]["wheel"]

    shown = installer(wheel)
    command = installer(with_login(wheel, *login) if login else wheel)
    return Plan(
        f"{name} {distribution.version} -> {latest['version']}",
        command,
        " ".join(shown),
    )


def make_plan(
    distribution: metadata.Distribution, transport: Any = None, prompt: Any = None
) -> Plan:
    name = distribution.metadata["Name"]
    raw = distribution.read_text("direct_url.json")
    direct: dict[str, Any] = json.loads(raw) if raw else {}

    if not direct:
        # (an index: a name)
        return Plan(f"{name} {distribution.version}: from an index", installer(name), " ".join(installer(name)))

    if "dir_info" in direct:
        editable = direct["dir_info"].get("editable")
        where = direct["url"]
        how = "it is editable, so it follows the directory" if editable else "install it again from there"
        return Plan(f"{name} was installed from {where}: update that directory (`git pull`); {how}")

    url = direct["url"]
    if "vcs_info" in direct:
        revision = direct["vcs_info"].get("requested_revision")
        spec = f"git+{url}" + (f"@{revision}" if revision else "")
        note = f" (at '{revision}': it stays there)" if revision else ""
        return Plan(f"{name}: from {url}{note}", installer(spec), " ".join(installer(spec)))

    base = server_base(url)
    if base is None:
        spec = url
        return Plan(f"{name}: from {url}", installer(spec), " ".join(installer(spec)))
    return plan_from_server(distribution, base, transport, prompt)
