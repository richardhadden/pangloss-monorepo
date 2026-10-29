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
# (where `gather` puts the translations, next to the models, for the interface to import)
TRANSLATIONS_PATH = "interface-app/src/generated/translations.json"
# (the modules of the installed apps, and where the application imports them from)
MODULES_PATH = "interface-app/src/generated/modules.ts"
SOURCES_PATH = "interface-app/src/generated/sources.css"
MODULES_MANIFEST = ".synced-modules.json"
EXCLUDED_FILES = {".env", MODELS_MODULE_PATH, TRANSLATIONS_PATH, MODULES_PATH, SOURCES_PATH}


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
    destination: Path,
    source: Path = JS_ROOT,
    replaced: dict[str, bytes] | None = None,
) -> tuple[list[str], list[str]]:
    """Copy the JavaScript of the package. Returns the files written, and those removed
    (that an earlier copy had, and the package no longer has). `replaced` gives the content
    of a file that is not the package's own (`package.json`, with the modules' workspaces)."""
    files = package_files(source)
    replaced = replaced or {}
    written = [
        name
        for name in files
        if write_if_changed(
            destination / name,
            replaced[name] if name in replaced else (source / name).read_bytes(),
        )
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

    from pangloss_interface.meta import export_definitions

    project.import_models()
    initialise()
    return export_definitions()


class ModuleSource(Protocol):
    """An interface module: `pangloss_interface.modules.InterfaceModule`"""

    app: str
    root: Path


def module_files(root: Path) -> list[str]:
    """The files of a module to copy (as the package's are: not what npm installs or builds)"""
    return package_files(root)


def workspace_package_json(has_modules: bool, source: Path = JS_ROOT) -> bytes:
    """`package.json` of the working directory: the package's, with the modules as workspaces if there are any"""
    package = json.loads((source / "package.json").read_text())
    if has_modules:
        package["workspaces"] = [*package["workspaces"], "modules/*"]
    return (json.dumps(package, indent=2) + "\n").encode()


def modules_module(apps: list[str]) -> str:
    """`generated/modules.ts`: the manifests (small; the components are lazy), imported by path"""
    imports = "".join(
        f'import module{n} from "../../../modules/{app}/src/index";\n'
        for n, app in enumerate(apps)
    )
    names = ", ".join(f"module{n}" for n in range(len(apps)))
    return (
        "// Generated by `pangloss interface` from the interface modules of the installed apps: do not edit.\n"
        'import type { ModuleManifest } from "@pangloss/interface-core";\n'
        f"{imports}\n"
        f"export const modules: ModuleManifest[] = [{names}];\n"
    )


def sources_css(has_modules: bool) -> str:
    """`generated/sources.css`: for Tailwind to look in the modules for the classes it uses"""
    if not has_modules:
        return "/* (no interface modules) */\n"
    return '@source "../../../modules";\n'


def sync_modules(
    destination: Path, modules: list[ModuleSource]
) -> tuple[list[str], list[str]]:
    """Copy the interface modules into `modules/<app>/`; the files written, and those removed
    (of a module that has lost them, or that is no longer installed)"""
    wanted: dict[str, Path] = {}
    for module in modules:
        for name in module_files(module.root):
            wanted[f"modules/{module.app}/{name}"] = module.root / name
    written = [
        name
        for name, path in wanted.items()
        if write_if_changed(destination / name, path.read_bytes())
    ]
    manifest = destination / MODULES_MANIFEST
    previous: list[str] = json.loads(manifest.read_text()) if manifest.is_file() else []
    removed = []
    for name in sorted(set(previous) - set(wanted)):
        stale = destination / name
        if stale.is_file():
            stale.unlink()
            removed.append(name)
    write_if_changed(manifest, (json.dumps(sorted(wanted), indent=2) + "\n").encode())
    return written, removed


def prepare(
    project_root: Path,
    exported: dict[str, Any],
    modules: list[ModuleSource] | None = None,
) -> Prepared:
    """Make the working directory ready: the package's JavaScript, the models, and the
    interface modules of the installed apps"""
    modules = modules or []
    directory = working_directory(project_root)
    directory.mkdir(parents=True, exist_ok=True)
    written, removed = sync_sources(
        directory, replaced={"package.json": workspace_package_json(bool(modules))}
    )
    module_written, module_removed = sync_modules(directory, modules)
    written += module_written
    removed += module_removed
    apps = [module.app for module in modules]
    for path, content in (
        (MODULES_PATH, modules_module(apps)),
        (SOURCES_PATH, sources_css(bool(modules))),
    ):
        if write_if_changed(directory / path, content.encode()):
            written.append(path)
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


def linked_translations_path(project_root: Path) -> Path:
    return working_directory(project_root) / "linked" / "translations.json"


@dataclass
class Linked:
    """What `dev --link` points the application at"""

    models: Path
    modules: Path
    sources: Path
    module_roots: list[Path]


def linked_modules_path(project_root: Path) -> Path:
    return working_directory(project_root) / "linked" / "modules.ts"


def linked_sources_path(project_root: Path) -> Path:
    return working_directory(project_root) / "linked" / "sources.css"


def prepare_linked(
    project_root: Path,
    exported: dict[str, Any],
    modules: list[ModuleSource] | None = None,
) -> Linked:
    """Write only the project's models and the list of its interface modules, for the interface to
    be run from the package's own source. The modules are used **where they are** (an app that
    is checked out: editing it is seen at once), not copied. Returns the paths."""
    modules = modules or []
    path = linked_models_path(project_root)
    write_if_changed(path, models_module(exported).encode())
    imports = "".join(
        f"import module{n} from {json.dumps(str(module.root / 'src' / 'index'))};\n"
        for n, module in enumerate(modules)
    )
    names = ", ".join(f"module{n}" for n in range(len(modules)))
    modules_path = linked_modules_path(project_root)
    write_if_changed(
        modules_path,
        (
            "// Generated by `pangloss interface dev --link`: do not edit.\n"
            'import type { ModuleManifest } from "@pangloss/interface-core";\n'
            f"{imports}\nexport const modules: ModuleManifest[] = [{names}];\n"
        ).encode(),
    )
    sources_path = linked_sources_path(project_root)
    sources = "".join(f'@source {json.dumps(str(m.root))};\n' for m in modules)
    write_if_changed(
        sources_path, (sources or "/* (no interface modules) */\n").encode()
    )
    gitignore = working_directory(project_root) / ".gitignore"
    write_if_changed(gitignore, GITIGNORE.encode())
    return Linked(path, modules_path, sources_path, [m.root for m in modules])


def remove_working_directory(project_root: Path) -> None:
    shutil.rmtree(working_directory(project_root), ignore_errors=True)
