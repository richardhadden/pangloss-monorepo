"""The SDK this server has built and serves, and building it as the server starts or on the
first request."""

import asyncio
import json
import logging
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pangloss_core import settings as core_settings
from pangloss_sdk.schemas import schema_hash

from pangloss_sdk_server import config, publish
from pangloss_sdk_server.builder import SdkBuildError

logger = logging.getLogger("pangloss.sdk")


@dataclass
class Current:
    manifest: dict[str, Any]
    files: dict[str, bytes]
    built_at: str | None

    @property
    def fingerprint(self) -> str:
        return self.manifest["fingerprint"]

    @property
    def schema_hash(self) -> str:
        return schema_hash(self.manifest["schema_position"])


_current: Current | None = None
_error: str | None = None
_lock: asyncio.Lock | None = None


def current() -> Current | None:
    return _current


def last_error() -> str | None:
    return _error


def reset() -> None:
    global _current, _error, _lock
    _current = _error = _lock = None


def find_root(settings: Any = None) -> Path:
    """The project's directory: `SDK_ROOT`, or the nearest directory above the working
    directory whose pyproject.toml has `[tool.pangloss]`, or the working directory"""
    if configured := config.setting("SDK_ROOT", None, settings):
        return Path(configured).resolve()
    here = Path.cwd().resolve()
    for candidate in (here, *here.parents):
        pyproject = candidate / "pyproject.toml"
        if pyproject.is_file():
            try:
                if "pangloss" in tomllib.loads(pyproject.read_text()).get("tool", {}):
                    return candidate
            except tomllib.TOMLDecodeError:
                continue
    return here


def read_package(directory: Path) -> dict[str, bytes]:
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in sorted(directory.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
    }


def load_built(settings: Any = None) -> Current | None:
    """The last build on disk (by `pangloss sdk build`, or an earlier start of the server)"""
    global _current
    output = config.output_directory(find_root(settings), settings)
    directory = publish.package_directory(output)
    if not directory.is_dir():
        return None
    files = read_package(directory)
    manifests = [p for p in files if p.endswith("/manifest.json")]
    if len(manifests) != 1:
        return None
    _current = Current(
        manifest=json.loads(files[manifests[0]]),
        files=files,
        built_at=publish.read_state(output).get("built_at"),
    )
    return _current


def _build(settings: Any, root: Path) -> publish.Built:
    return publish.build(root, settings)


async def ensure_built(settings: Any = None, force: bool = False) -> Current:
    """Build if the models changed (or `force`), and make it the one served. A build that
    fails is kept as `last_error()` and raised"""
    global _current, _error, _lock
    settings = settings or core_settings.SETTINGS
    if _lock is None:
        _lock = asyncio.Lock()
    async with _lock:
        root = find_root(settings)
        try:
            built = await asyncio.to_thread(publish.build, root, settings, force)
        except SdkBuildError as error:
            _error = "; ".join([str(error), *error.problems])
            raise
        _error = None
        files = read_package(built.directory)
        output = config.output_directory(root, settings)
        _current = Current(
            manifest=built.manifest,
            files=files,
            built_at=publish.read_state(output).get("built_at"),
        )
        return _current


async def serving(settings: Any = None) -> Current | None:
    """What to serve now: the current build; else the last one on disk; else (unless
    `SDK_BUILD` is `"off"`) a build"""
    if _current is not None:
        return _current
    if (loaded := load_built(settings)) is not None:
        return loaded
    if config.setting("SDK_BUILD", "start", settings) == "off":
        return None
    try:
        return await ensure_built(settings)
    except SdkBuildError:
        return None


async def on_start(settings: Any) -> None:
    """As the server starts (`SDK_BUILD = "start"`, the default): build if the models changed.
    A failure is logged, and the SDK is not served; the server still starts"""
    if config.setting("SDK_BUILD", "start", settings) == "off":
        load_built(settings)
        return
    try:
        built = await ensure_built(settings)
        logger.info("SDK %s %s", built.manifest["distribution"], built.manifest["version"])
    except SdkBuildError as error:
        logger.error("The SDK could not be built: %s %s", error, error.problems)
