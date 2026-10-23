"""Building the SDK into the project's `.pangloss/sdk`: only when the content changed, checked
before it replaces the last one."""

import dataclasses
import datetime
import difflib
import json
import shutil
from pathlib import Path
from typing import Any

from pangloss_sdk_server import config
from pangloss_sdk_server.builder import Package, build_package
from pangloss_sdk_server.check import check_package

STATE_FILE = "state.json"
PACKAGE_DIRECTORY = "package"


@dataclasses.dataclass
class Built:
    changed: bool
    manifest: dict[str, Any]
    directory: Path


def read_state(output: Path) -> dict[str, Any]:
    try:
        return json.loads((output / STATE_FILE).read_text())
    except (FileNotFoundError, ValueError):
        return {}


def package_directory(output: Path) -> Path:
    return output / PACKAGE_DIRECTORY


def current_package(root: Path, settings: Any, output: Path) -> Package:
    """The SDK as the models are now (the version is that of the last build, or the next
    if this is not it: use `needs_build` to tell)"""
    state = read_state(output)
    return build_package(root, settings, state.get("number", 0) + 1)


def needs_build(package: Package, output: Path) -> bool:
    state = read_state(output)
    return (
        state.get("fingerprint") != package.fingerprint
        or not package_directory(output).is_dir()
    )


def write_files(directory: Path, files: dict[str, bytes]) -> None:
    for relative, content in files.items():
        path = directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def build(root: Path, settings: Any, force: bool = False) -> Built:
    """Build the SDK if the models changed (or `force`), check it on a clean client, and put
    it in place. Raises `SdkBuildError` and leaves the last build as it was"""
    output = config.output_directory(root, settings)
    state = read_state(output)
    package = build_package(root, settings, state.get("number", 0) + 1)
    final = package_directory(output)

    if not needs_build(package, output) and not force:
        # (as built: the number is of the last build)
        package = build_package(root, settings, max(state.get("number", 1), 1))
        return Built(False, package.manifest, final)

    number = state.get("number", 0)
    if state.get("fingerprint") != package.fingerprint:
        number += 1
    package = build_package(root, settings, max(number, 1))

    output.mkdir(parents=True, exist_ok=True)
    staging = output / ".building"
    shutil.rmtree(staging, ignore_errors=True)
    write_files(staging, package.files)
    try:
        check_package(
            staging, package.manifest["module"], set(package.manifest["modules"])
        )
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    shutil.rmtree(final, ignore_errors=True)
    staging.rename(final)
    (output / STATE_FILE).write_text(
        json.dumps(
            {
                "fingerprint": package.fingerprint,
                "number": max(number, 1),
                "built_at": datetime.datetime.now(datetime.UTC).isoformat(),
                "schema_position": package.manifest["schema_position"],
            },
            indent=2,
        )
        + "\n"
    )
    return Built(True, package.manifest, final)


def diff_against_built(package: Package, output: Path) -> list[str]:
    """A unified diff of the SDK as the models are now against the last build"""
    built = package_directory(output)
    lines: list[str] = []
    paths = set(package.files)
    if built.is_dir():
        paths |= {
            p.relative_to(built).as_posix() for p in built.rglob("*") if p.is_file()
        }
    for relative in sorted(paths):
        # (the version and the manifest follow the build number: not a change in themselves)
        if relative.endswith("manifest.json") or relative == "pyproject.toml":
            continue
        new = package.files.get(relative)
        old_path = built / relative
        old = old_path.read_bytes() if old_path.is_file() else None
        if new == old:
            continue
        lines.extend(
            difflib.unified_diff(
                [] if old is None else old.decode(errors="replace").splitlines(),
                [] if new is None else new.decode(errors="replace").splitlines(),
                fromfile=f"built/{relative}",
                tofile=f"now/{relative}",
                lineterm="",
            )
        )
    return lines
