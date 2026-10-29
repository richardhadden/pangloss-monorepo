"""Interface modules: the Solid library an installed app may ship in `<app>/interface/`
(docs/interface-modules-implementation.md).

`discover` finds them without importing the apps; `problems` checks what the models and the
configs name against what the modules' manifests say they provide (the manifests are read by
`read_manifests`, which runs Vite's loader in Node, since they are TypeScript).
"""

import importlib.util
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pangloss_interface.paths import CORE_PATH
from pangloss_interface.runtime import Runtime, run_captured

MODULE_DIRECTORY = "interface"
SLOT_KEYS = ("listPage", "itemPage", "viewCard", "editCard")
READ_SCRIPT = "scripts/read-manifests.mjs"


@dataclass(frozen=True)
class InterfaceModule:
    app: str
    root: Path  # (<app dir>/interface)

    @property
    def package_json(self) -> Path:
        return self.root / "package.json"

    @property
    def package_name(self) -> str:
        return json.loads(self.package_json.read_text()).get("name", "")


def app_directory(app: str) -> Path | None:
    """Where an app's package is, without importing it"""
    try:
        spec = importlib.util.find_spec(app)
    except ImportError, ValueError:
        return None
    locations = list(spec.submodule_search_locations or []) if spec else []
    return Path(locations[0]) if locations else None


def discover(installed_apps: Iterable[str]) -> list[InterfaceModule]:
    """The interface modules of the installed apps, in the order of `INSTALLED_APPS`"""
    found = []
    for app in installed_apps:
        directory = app_directory(app)
        if directory and (directory / MODULE_DIRECTORY / "package.json").is_file():
            found.append(InterfaceModule(app, directory / MODULE_DIRECTORY))
    return found


@dataclass(frozen=True)
class Manifest:
    """What a module's `defineModule` says (as the reader gives it)"""

    name: str
    components: tuple[str, ...] = ()
    routes: tuple[Mapping[str, Any], ...] = ()
    requires: tuple[str, ...] = ()

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> Manifest:
        return cls(
            name=data.get("name", ""),
            components=tuple(data.get("components", [])),
            routes=tuple(data.get("routes", [])),
            requires=tuple(data.get("requires", [])),
        )


def core_version() -> str:
    return json.loads((CORE_PATH / "package.json").read_text())["version"]


def _version(text: str) -> tuple[int, int, int]:
    parts = (re.findall(r"\d+", text) + ["0", "0", "0"])[:3]
    return int(parts[0]), int(parts[1]), int(parts[2])


def satisfies(version: str, range_: str) -> bool:
    """Whether a version meets an npm range: `*`, `1.2.3`, `^`, `~`, `>=` `>` `<=` `<`, `1.x`, spaces (and) and `||` (or).
    Enough for the peer ranges of modules; pre-release tags are ignored."""
    have = _version(version)

    def one(comparator: str) -> bool:
        comparator = comparator.strip()
        if comparator in ("", "*", "x", "latest"):
            return True
        if comparator[0] in "^~":
            low = _version(comparator[1:])
            if comparator[0] == "~" or low[0] == 0:
                # (~1.2.3 is below 1.3.0; ^0.1.2 is below 0.2.0, ^0.0.3 below 0.0.4)
                high = (
                    (low[0], low[1] + 1, 0)
                    if comparator[0] == "~" or low[1]
                    else (0, 0, low[2] + 1)
                )
            else:
                high = (low[0] + 1, 0, 0)
            return low <= have < high
        match = re.match(r"(>=|<=|>|<|=)?\s*(.*)", comparator)
        assert match
        operator, text = match.group(1) or "=", match.group(2)
        if re.search(r"[xX*]", text):  # (1.x, 1.2.x)
            fixed = [int(n) for n in re.findall(r"\d+", text)]
            return list(have[: len(fixed)]) == fixed
        want = _version(text)
        return {
            "=": have == want,
            ">=": have >= want,
            "<=": have <= want,
            ">": have > want,
            "<": have < want,
        }[operator]

    return any(
        all(
            one(part)
            for part in re.split(r"\s+(?![^<>=]*\d)|\s+", alternative.strip())
            if part
        )
        for alternative in range_.split("||")
    )


def _route_pattern(path: str) -> re.Pattern[str]:
    parts = [
        "[^/]+"
        if part.startswith(":")
        else ".+"
        if part.startswith("*")
        else re.escape(part)
        for part in path.strip("/").split("/")
    ]
    return re.compile("^/" + "/".join(parts) + "/?$")


def problems(
    modules: Sequence[InterfaceModule],
    manifests: Mapping[str, Manifest],
    exported: Mapping[str, Any],
    interface_version: str | None = None,
) -> list[str]:
    """What is wrong, as sentences: a model that names a component no module has, a manifest
    that is not its app's, a route that would be read as a type, requirements that are not met"""
    found: list[str] = []
    by_app = {m.app: m for m in modules}
    for module in modules:
        manifest = manifests.get(module.app)
        if manifest is None:
            found.append(
                f"{module.app}: the manifest of its interface module could not be read"
            )
        elif manifest.name != module.app:
            found.append(
                f"{module.app}: its manifest says name {manifest.name!r}, which has to be the app's"
            )
    for module in modules:
        manifest = manifests.get(module.app)
        if manifest is None:
            continue
        for required in manifest.requires:
            if required not in by_app:
                found.append(
                    f"{module.app} requires {required!r}, which has no interface module"
                )
        for route in manifest.routes:
            if route.get("component") not in manifest.components:
                found.append(
                    f"{module.app}: route {route.get('path')!r} names component {route.get('component')!r}, "
                    f"which is not in components ({', '.join(manifest.components) or 'none'})"
                )
    found += _peers(modules, interface_version or core_version())
    found += _nav_links(modules, manifests, exported)
    found += _cycles(manifests)
    found += _route_clashes(modules, manifests, exported)
    for name, model in exported.get("models", {}).items():
        meta = model.get("interfaceMeta") or {}
        for slot in SLOT_KEYS:
            ref = meta.get(slot)
            if not ref:
                continue
            app, key = ref["module"], ref["name"]
            snake = {
                "listPage": "list_page",
                "itemPage": "item_page",
                "viewCard": "view_card",
                "editCard": "edit_card",
            }[slot]
            where = f"{name}.{snake} '{app}:{key}'"
            if app not in by_app:
                found.append(
                    f"{where}: no installed app {app!r} has an interface module (pangloss interface new-module {app})"
                )
            elif (manifest := manifests.get(app)) and key not in manifest.components:
                found.append(
                    f"{where}: {key!r} is not in the components of {app} ({', '.join(manifest.components) or 'none'})"
                )
    return found


def _peers(modules: Sequence[InterfaceModule], version: str) -> list[str]:
    found = []
    for module in modules:
        wanted = (
            json.loads(module.package_json.read_text())
            .get("peerDependencies", {})
            .get("@pangloss/interface-core")
        )
        if wanted is None:
            found.append(
                f"{module.app}: package.json has no peerDependencies on @pangloss/interface-core (this is {version})"
            )
        elif not satisfies(version, wanted):
            found.append(
                f"{module.app}: it needs @pangloss/interface-core {wanted}, and this is {version}: update the module"
            )
    return found


def _nav_links(
    modules: Sequence[InterfaceModule],
    manifests: Mapping[str, Manifest],
    exported: Mapping[str, Any],
) -> list[str]:
    """A link inside the interface goes to a type, or to a route of a module (or home)"""
    models = set(exported.get("models", {}))
    patterns = [
        _route_pattern(str(route.get("path", "")))
        for module in modules
        if (manifest := manifests.get(module.app))
        for route in manifest.routes
    ]
    found = []
    for link in (exported.get("nav") or {}).get("links", []):
        if link.get("external"):
            continue
        path = re.split(r"[?#]", link["href"])[0]
        first = path.strip("/").split("/")[0]
        if path == "/" or first in models or any(p.match(path) for p in patterns):
            continue
        found.append(
            f"NavLink {link['label']!r}: {link['href']!r} is neither a type nor a route of an interface module"
        )
    return found


def _cycles(manifests: Mapping[str, Manifest]) -> list[str]:
    found = []
    done: set[str] = set()

    def visit(app: str, path: list[str]) -> None:
        if app in path:
            found.append(
                "interface modules require each other in a circle: "
                + " -> ".join([*path[path.index(app) :], app])
            )
            return
        if app in done or app not in manifests:
            return
        for required in manifests[app].requires:
            visit(required, [*path, app])
        done.add(app)

    for app in manifests:
        visit(app, [])
    return found


def _route_clashes(
    modules: Sequence[InterfaceModule],
    manifests: Mapping[str, Manifest],
    exported: Mapping[str, Any],
) -> list[str]:
    found = []
    models = set(exported.get("models", {}))
    seen: dict[str, str] = {}
    for module in modules:
        manifest = manifests.get(module.app)
        for route in manifest.routes if manifest else ():
            path = str(route.get("path", ""))
            first = path.strip("/").split("/")[0]
            if first in models:
                found.append(
                    f"{module.app}: route {path!r} would be read as the type {first!r}"
                )
            if path in seen:
                found.append(
                    f"{module.app}: route {path!r} is also a route of {seen[path]}"
                )
            seen[path] = module.app
    return found


def read_manifests(
    runtime: Runtime, workspace: Path, modules: Sequence[InterfaceModule]
) -> dict[str, Manifest]:
    """Load the manifests (in the working directory's copies) with Vite's loader, in Node"""
    if not modules:
        return {}
    files = [str(workspace / "modules" / m.app / "src" / "index.ts") for m in modules]
    code, output = run_captured(
        [runtime.executable, READ_SCRIPT, *files], workspace / "interface-app"
    )
    if code != 0:
        raise ManifestError(output.strip()[-2000:] or "reading the manifests failed")
    data = json.loads(output.strip().splitlines()[-1])
    return {m.app: Manifest.from_data(item) for m, item in zip(modules, data)}


class ManifestError(Exception):
    """The manifests of the modules could not be read"""


__all__ = [
    "InterfaceModule",
    "Manifest",
    "ManifestError",
    "discover",
    "problems",
    "read_manifests",
]
