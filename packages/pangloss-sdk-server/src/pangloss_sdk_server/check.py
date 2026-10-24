"""Trying an SDK before it is published: on its own, as a client would have it.

A subprocess puts the package first on its path, forbids the modules only a server has, imports
it, initialises the models with no server, and prints the schema of what it made. These must be
the schemas of the models the server has.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from pangloss_sdk.schemas import head_model_schemas

from pangloss_sdk_server.builder import SdkBuildError
from pangloss_sdk_server.closure import SERVER_ONLY

MARKER = "SDK-SCHEMAS:"

SCRIPT = """
import json, sys
sys.path.insert(0, {directory!r})

class Blocker:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in {forbidden!r}:
            raise ImportError("a client does not have " + name)

sys.meta_path.insert(0, Blocker())

import {module} as sdk
sdk.connect_offline()

from pangloss_sdk.schemas import head_model_schemas
print({marker!r} + json.dumps(head_model_schemas(), sort_keys=True, default=str))
"""


def run_in_clean_process(directory: Path, module: str) -> dict[str, Any]:
    script = SCRIPT.format(
        directory=str(directory),
        forbidden=sorted(SERVER_ONLY),
        module=module,
        marker=MARKER,
    )
    environment = {k: v for k, v in os.environ.items() if not k.startswith("PANGLOSS_")}
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", script],
        capture_output=True,
        text=True,
        cwd=directory,
        env=environment,
    )
    if result.returncode != 0:
        tail = "\n".join(result.stderr.strip().splitlines()[-6:])
        raise SdkBuildError(
            "The SDK does not import or initialise on a clean client", [tail]
        )
    line = next((l for l in result.stdout.splitlines() if l.startswith(MARKER)), None)
    if line is None:
        raise SdkBuildError(
            "The check of the SDK gave no answer", [result.stdout[-300:]]
        )
    return json.loads(line.removeprefix(MARKER))


def differences(server: dict[str, Any], client: dict[str, Any]) -> list[str]:
    problems = []
    for name, schemas in sorted(client.items()):
        if name not in server:
            problems.append(f"{name}: the client has it, the server does not")
            continue
        for kind, schema in schemas.items():
            if json.loads(json.dumps(server[name].get(kind), default=str)) != schema:
                problems.append(
                    f"{name}.{kind}: the client's model is not the server's"
                )
    for name in sorted(set(server) - set(client)):
        problems.append(f"{name}: the server has it, the SDK does not")
    return problems


def check_package(directory: Path, module: str, shipped_modules: set[str]) -> None:
    """Raise `SdkBuildError` unless the package, on a clean client, makes the models the
    server has (of the shipped modules)"""
    client = run_in_clean_process(directory, module)
    server = head_model_schemas(shipped_modules)
    problems = differences(server, client)
    if problems:
        raise SdkBuildError("The SDK's models are not those of the server", problems)
