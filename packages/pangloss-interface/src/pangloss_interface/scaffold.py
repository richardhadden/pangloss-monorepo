"""The files of a new interface module (`pangloss interface new-module <app>`): a function from the
app's name and the versions of the peer packages to a dictionary of path to text. The text of the
files is in `templates/module/`, with `{{app}}` and the like filled in.
"""

import json
from pathlib import Path

from pangloss_interface.paths import CORE_PATH

TEMPLATES = Path(__file__).parent / "templates" / "module"
EXAMPLE_FILES = (
    "src/components/ExampleCard.tsx",
    "src/components/ExampleCard.test.tsx",
)


def peer_versions() -> dict[str, str]:
    """The ranges of the peer packages, from interface-core's own"""
    package = json.loads((CORE_PATH / "package.json").read_text())
    peers = dict(package["peerDependencies"])
    peers["@pangloss/interface-core"] = "*"
    peers["@solidjs/router"] = json.loads(
        (CORE_PATH.parent / "interface-app" / "package.json").read_text()
    )["dependencies"]["@solidjs/router"]
    return dict(sorted(peers.items()))


def module_files(app: str, with_example: bool = True) -> dict[str, str]:
    """Path (inside `<app>/interface/`) to text"""
    names = {
        path.relative_to(TEMPLATES).as_posix(): path
        for path in TEMPLATES.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    files = {}
    for name, path in names.items():
        if name in EXAMPLE_FILES and not with_example:
            continue
        files[name] = path.read_text().replace("{{app}}", app)
    package = json.loads(files["package.json"])
    package["peerDependencies"] = peer_versions()
    files["package.json"] = json.dumps(package, indent=2) + "\n"
    if not with_example:
        files["src/index.ts"] = files["src/index.ts"].replace(
            '    ExampleCard: () => import("./components/ExampleCard"),\n', ""
        )
    return files
