"""The working directory of a project's interface: `.pangloss/interface`.

The interface is built there, not in the installed package (which should not be written
to). `prepare` copies the JavaScript of the package into it, and writes the definitions
of the project's models as a TypeScript module that the interface imports. What npm
installs and builds is in it too (`node_modules`, `dist`), and those are ignored by git;
the rest (the sources and the generated models) is not, so a project can keep it if it
wants to, or ignore `.pangloss` as a whole.

The files that come from the package are listed in `.synced.json`, so that one that the
package no longer has is removed.
"""

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from pangloss_interface.paths import JS_ROOT
from pangloss_interface.typescript import MODELS_MODULE_PATH, models_module

WORKING_DIRECTORY = Path(".pangloss") / "interface"
MANIFEST = ".synced.json"
GITIGNORE = "node_modules\ndist\n.env\n*.tsbuildinfo\n"

# Not copied from the package (they are what npm installs and builds there, or are made
# for the project)
EXCLUDED_DIRECTORIES = {"node_modules", "dist"}
EXCLUDED_FILES = {".env", MODELS_MODULE_PATH}


class Project(Protocol):
    """What is needed of the project that `pangloss-cli` loads"""

    def import_models(self) -> None: ...


@dataclass
class Prepared:
    directory: Path
    written: list[str]
    removed: list[str]


def working_directory(project_root: Path) -> Path:
    return project_root / WORKING_DIRECTORY


def package_files(source: Path = JS_ROOT) -> list[str]:
    """The files of the package's JavaScript to copy (relative paths, sorted)"""
    files = []
    for path in source.rglob("*"):
        relative = path.relative_to(source)
        if not path.is_file() or EXCLUDED_DIRECTORIES & set(relative.parts):
            continue
        if relative.name in EXCLUDED_FILES or relative.as_posix() in EXCLUDED_FILES:
            continue
        if relative.suffix == ".tsbuildinfo":
            continue
        files.append(relative.as_posix())
    return sorted(files)


def write_if_changed(path: Path, content: bytes) -> bool:
    """Write a file unless it is as it should be (so that watchers are not woken)"""
    if path.is_file() and path.read_bytes() == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return True


def sync_sources(
    destination: Path, source: Path = JS_ROOT
) -> tuple[list[str], list[str]]:
    """Copy the JavaScript of the package. Returns the files written, and those removed
    (that an earlier copy had, and the package no longer has)."""
    files = package_files(source)
    written = [
        name
        for name in files
        if write_if_changed(destination / name, (source / name).read_bytes())
    ]

    manifest = destination / MANIFEST
    previous: list[str] = json.loads(manifest.read_text()) if manifest.is_file() else []
    removed = []
    for name in sorted(set(previous) - set(files)):
        stale = destination / name
        if stale.is_file():
            stale.unlink()
            removed.append(name)
    write_if_changed(manifest, (json.dumps(files, indent=2) + "\n").encode())
    write_if_changed(destination / ".gitignore", GITIGNORE.encode())
    return written, removed


def export_project_models(project: Project) -> dict[str, Any]:
    """The definitions of the models of the project's installed apps"""
    from pangloss_models import initialise
    from pangloss_models.export import export_models

    project.import_models()
    initialise()
    return export_models()


def prepare(project_root: Path, exported: dict[str, Any]) -> Prepared:
    """Make the working directory ready: the package's JavaScript, and the models"""
    directory = working_directory(project_root)
    directory.mkdir(parents=True, exist_ok=True)
    written, removed = sync_sources(directory)
    if write_if_changed(
        directory / MODELS_MODULE_PATH, models_module(exported).encode()
    ):
        written.append(MODELS_MODULE_PATH)
    return Prepared(directory, written, removed)


def linked_models_path(project_root: Path) -> Path:
    """Where the models are for `dev --link`: not in the interface's source, which is
    the package's own"""
    return working_directory(project_root) / "linked" / "models.ts"


def is_source_checkout() -> bool:
    """Whether the package's JavaScript can be run where it is: a checkout of the
    source (editable install), not a copy in `site-packages`"""
    return "site-packages" not in JS_ROOT.parts and "dist-packages" not in JS_ROOT.parts


def prepare_linked(project_root: Path, exported: dict[str, Any]) -> Path:
    """Write only the project's models, for the interface to be run from the package's
    own source. Returns the path of the module."""
    path = linked_models_path(project_root)
    write_if_changed(path, models_module(exported).encode())
    gitignore = working_directory(project_root) / ".gitignore"
    write_if_changed(gitignore, GITIGNORE.encode())
    return path


def remove_working_directory(project_root: Path) -> None:
    shutil.rmtree(working_directory(project_root), ignore_errors=True)
