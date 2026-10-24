"""Running the JavaScript tools: Node (with npm) or Bun.

The commands of `pangloss interface` wrap them. Node is the default, as it is what Vite
and the server that Solid builds are made for, and what is most often there already; Bun
can be chosen with `--runtime bun` or the environment variable
`PANGLOSS_INTERFACE_RUNTIME`.
"""

import os
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

RUNTIME_ENVIRONMENT_VARIABLE = "PANGLOSS_INTERFACE_RUNTIME"
RuntimeName = Literal["node", "bun"]
DEFAULT_RUNTIME: RuntimeName = "node"
RUNTIMES: tuple[RuntimeName, ...] = ("node", "bun")

# What the application needs of Node (Vite 8)
MINIMUM_NODE = (22, 12)


class InterfaceRuntimeError(Exception):
    """The JavaScript tools cannot be run"""


@dataclass(frozen=True)
class Runtime:
    name: RuntimeName
    # The command that runs JavaScript, and that which installs packages and runs scripts
    executable: str
    package_manager: str

    def install(self) -> list[str]:
        return [self.package_manager, "install"]

    def script(self, name: str, *args: str) -> list[str]:
        """The command for a script of the `package.json` of the application"""
        command = [self.package_manager, "run", name]
        if args:
            command += ["--", *args]
        return command

    def run_file(self, path: Path) -> list[str]:
        return [self.executable, str(path)]


def choose_runtime(
    requested: str | None = None, environment: Mapping[str, str] | None = None
) -> RuntimeName:
    environment = os.environ if environment is None else environment
    name = requested or environment.get(RUNTIME_ENVIRONMENT_VARIABLE) or DEFAULT_RUNTIME
    if name not in RUNTIMES:
        raise InterfaceRuntimeError(
            f"Unknown runtime '{name}': use one of {', '.join(RUNTIMES)}"
        )
    return name  # type: ignore[return-value]


def find_runtime(
    requested: str | None = None, environment: Mapping[str, str] | None = None
) -> Runtime:
    """The runtime to use; `InterfaceRuntimeError` says what to install if it is not there"""
    name = choose_runtime(requested, environment)
    if name == "node":
        node, npm = shutil.which("node"), shutil.which("npm")
        if not node or not npm:
            raise InterfaceRuntimeError(
                "Node.js (with npm) is needed to run the interface: install Node "
                f"{MINIMUM_NODE[0]}.{MINIMUM_NODE[1]} or later, or use --runtime bun"
            )
        return Runtime("node", node, npm)
    bun = shutil.which("bun")
    if not bun:
        raise InterfaceRuntimeError(
            "Bun was asked for, but is not installed (https://bun.sh)"
        )
    return Runtime("bun", bun, bun)


def run(
    command: Sequence[str],
    cwd: Path,
    environment: Mapping[str, str] | None = None,
) -> int:
    """Run a command in a directory, with the output shown; the exit code"""
    env = {**os.environ, **(environment or {})}
    try:
        return subprocess.run(list(command), cwd=cwd, env=env, check=False).returncode
    except KeyboardInterrupt:
        return 130
