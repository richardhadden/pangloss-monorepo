"""Type-checking the stubs of an SDK before it is published, with `ty`, in both kinds.

Each kind (the stubs next to the models, for `await Person.get(...)`; and `sync_stubs`, for the
blocking `connect(sync=True)`) is checked as a user would have it: a file that **uses** every
model in the way the kind says (`assert_type(await Person.get(id), Person.HeadView | None)`, and
so on), together with the stubs themselves. A stub that does not parse, names what is not there,
or has the wrong type for `get`, `list` or `save` is an error that stops the build.

`ty` has to be installed with the server (`SDK_TYPECHECK`: `"auto"` checks if it is found and says
so when it is not, `"required"` fails without it, `"off"` does not look).
"""

import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterable
from pathlib import Path

from pangloss_models.typestubs import has_operations

from pangloss_sdk_server.builder import SYNC_STUBS, SdkBuildError

TIMEOUT = 180
# (what the stubs say that a checker takes for a mistake, as they override what the base classes
# declare: the same as `make-stubs` writes comments for)
IGNORED_RULES = ("unused-type-ignore-comment", "invalid-attribute-override")


def find_ty() -> str | None:
    beside = shutil.which("ty", path=str(Path(sys.executable).parent))
    return beside or shutil.which("ty")


def usage_source(models: Iterable[type], mode: str) -> str:
    """A file that uses each model's functions as the kind of stub says they are, with the types
    they should have"""
    from pangloss_models.model_bases.entity import Entity

    wait = "await " if mode == "async" else ""
    define = "async def" if mode == "async" else "def"
    lines = [
        "import uuid",
        "from typing import assert_type",
        "from pangloss_models.model_bases.base_models import _ListItems",
        "",
    ]
    imports: dict[str, set[str]] = {}
    for model in models:
        imports.setdefault(model.__module__, set()).add(model.__qualname__.split(".")[0])
    for module, names in sorted(imports.items()):
        lines.append(f"from {module} import {', '.join(sorted(names))}")
    lines.append("")

    for index, model in enumerate(models):
        name = model.__qualname__
        entity = issubclass(model, Entity)
        lines += [
            f"{define} check_{index}(i: uuid.UUID, c: {name}.Create, u: {name}.Update) -> None:",
            f"    assert_type({wait}{name}.get(i), {name}.HeadView | None)",
            f"    assert_type({wait}{name}.list(), _ListItems[{name}.ReferenceView])",
            f"    assert_type({wait}{name}.delete(i), None)",
            f"    assert_type({wait}{name}.undelete(i), None)",
            f"    assert_type({wait}c.save(), {name}.ReferenceView)",
            f"    assert_type({wait}c.save(detail=True), {name}.HeadView)",
            f"    assert_type({wait}u.save(), {name}.ReferenceView)",
            f"    assert_type({wait}u.save(detail=True, expected_version=3), {name}.HeadView)",
        ]
        if entity:
            lines.append(f"    assert_type({wait}{name}.get_for_edit(i), {name}.EditView | None)")
        lines.append("")
    return "\n".join(lines)


def run_ty(
    ty: str, directory: Path, search: list[Path], files: list[Path]
) -> list[str]:
    command = [
        ty,
        "check",
        "--python",
        sys.prefix,
        "--output-format",
        "concise",
        *[f"--ignore={rule}" for rule in IGNORED_RULES],
        *[f"--extra-search-path={path}" for path in search],
        *map(str, files),
    ]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, cwd=directory, timeout=TIMEOUT
        )
    except subprocess.TimeoutExpired:
        return [f"ty did not finish in {TIMEOUT} seconds"]
    if result.returncode == 0:
        return []
    output = [line for line in (result.stdout + result.stderr).splitlines() if line.strip()]
    return output[:15] + ([f"... and {len(output) - 15} more"] if len(output) > 15 else [])


def check_types(
    package: Path, module: str, models: Iterable[type], setting: str = "auto"
) -> str | None:
    """Check both kinds of stub. Returns a note if it could not (no `ty`, and `auto`); raises
    `SdkBuildError` if a stub is wrong"""
    if setting == "off":
        return None
    ty = find_ty()
    if ty is None:
        if setting == "required":
            raise SdkBuildError(
                "The stubs cannot be type-checked: `ty` is not installed (SDK_TYPECHECK is "
                "'required')",
                [],
            )
        return "the stubs were not type-checked: `ty` is not installed (SDK_TYPECHECK = 'auto')"

    operations = [m for m in models if has_operations(m) and "<locals>" not in m.__qualname__]
    sync_directory = package / module / SYNC_STUBS
    problems: list[str] = []
    for mode in ("async", "sync"):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            usage = directory / f"usage_{mode}.py"
            usage.write_text(usage_source(operations, mode))
            if mode == "async":
                # (the stubs beside the modules, in the package)
                search = [package]
                stubs = [p for p in package.rglob("*.pyi") if SYNC_STUBS not in p.parts]
            else:
                # (the directory of blocking stubs, first: as a user's `typings` would be)
                search = [sync_directory, package]
                stubs = list(sync_directory.rglob("*.pyi"))
            problems += [
                f"[{mode}] {line}" for line in run_ty(ty, directory, search, [usage, *stubs])
            ]
    if problems:
        raise SdkBuildError("The stubs of the SDK do not type-check", problems)
    return None
