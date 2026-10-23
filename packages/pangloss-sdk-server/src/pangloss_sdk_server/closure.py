"""Which files of the project an SDK has: the modules that declare models, and every module
of the project that they import, found by reading the source (`ast`), never by running it.

A module is "of the project" if it is a file under the project's root (and not in a virtual
environment or installed package). Anything else that is imported is a dependency of the SDK
(or the standard library), or something a client cannot have.
"""

import ast
import dataclasses
import sys
from pathlib import Path

from pangloss_sdk_server.sources import is_server_only

# What only a server has: a model module that imports one of these cannot run on a client
SERVER_ONLY = {
    "neo4j",
    "fastapi",
    "starlette",
    "uvicorn",
    "pangloss_api",
    "pangloss_cli",
    "pangloss_history",
    "pangloss_interface",
    "pangloss_memgraph",
    "pangloss_sdk_server",
    "pangloss_users",
}


@dataclasses.dataclass
class Closure:
    # module name -> its file
    modules: dict[str, Path] = dataclasses.field(default_factory=dict)
    # top-level names imported that are not of the project (and not the standard library)
    outside: set[str] = dataclasses.field(default_factory=set)
    problems: list[str] = dataclasses.field(default_factory=list)


def is_in_environment(root: Path, path: Path) -> bool:
    return any(
        directory.name in ("site-packages", "dist-packages")
        or (directory / "pyvenv.cfg").exists()
        for directory in path.parents
        if directory.is_relative_to(root)
    )


def locate(root: Path, name: str) -> Path | None:
    """The file of a module of the project, or None"""
    base = root.joinpath(*name.split("."))
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file() and not is_in_environment(root, candidate.resolve()):
            return candidate
    return None


def is_package(path: Path) -> bool:
    return path.name == "__init__.py"


def resolve_relative(module: str, is_init: bool, level: int, name: str | None) -> str | None:
    package = module if is_init else module.rpartition(".")[0]
    parts = package.split(".") if package else []
    if level - 1 > len(parts):
        return None
    base = parts[: len(parts) - (level - 1)]
    if name:
        base = [*base, *name.split(".")]
    return ".".join(base) or None


def walk_shipped(tree: ast.AST):
    """Every node of what the SDK ships: not the body of a `@server_only` function (it is
    taken out), though its signature and decorators are read"""
    stack = [tree]
    while stack:
        node = stack.pop()
        yield node
        if is_server_only(node):
            assert isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            stack.extend(
                [*node.decorator_list, node.args, *([node.returns] if node.returns else [])]
            )
            continue
        stack.extend(ast.iter_child_nodes(node))


def imports_of(module: str, path: Path) -> tuple[list[str], list[str]]:
    """The names a module imports, as dotted module names (for `from a import b`, both `a`
    and `a.b`, as either may be a module), and what could not be resolved"""
    tree = ast.parse(path.read_text(), filename=str(path))
    names: list[str] = []
    unresolved: list[str] = []
    for node in walk_shipped(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                names.extend(".".join(parts[: i + 1]) for i in range(len(parts)))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = resolve_relative(module, is_package(path), node.level, node.module)
                if base is None:
                    unresolved.append(f"{module}: a relative import goes above the top")
                    continue
            else:
                base = node.module or ""
            parts = base.split(".")
            names.extend(".".join(parts[: i + 1]) for i in range(len(parts)))
            names.extend(f"{base}.{alias.name}" for alias in node.names if alias.name != "*")
    return names, unresolved


def init_problems(module: str, path: Path) -> list[str]:
    """A package's `__init__.py` runs when anything in it is imported, on the client too: it
    may hold only a docstring, imports and `__all__`"""
    tree = ast.parse(path.read_text(), filename=str(path))
    problems = []
    for node in tree.body:
        if isinstance(node, ast.Import | ast.ImportFrom):
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue
        if (
            isinstance(node, ast.Assign)
            and all(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets)
        ):
            continue
        problems.append(
            f"{path}:{node.lineno}: `{module}/__init__.py` does more than import "
            "(it would run on every client); keep only imports in the `__init__.py` of a "
            "package an SDK ships"
        )
        break
    return problems


def closure_of(root: Path, start: list[str]) -> Closure:
    root = root.resolve()
    result = Closure()
    queue = list(start)
    seen: set[str] = set()

    while queue:
        name = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        path = locate(root, name)
        if path is None:
            top = name.split(".")[0]
            if top not in sys.stdlib_module_names and locate(root, top) is None:
                result.outside.add(top)
            continue
        result.modules[name] = path

        # (every package above it runs its `__init__.py` too)
        parts = name.split(".")
        for i in range(1, len(parts)):
            queue.append(".".join(parts[:i]))

        if is_package(path):
            result.problems.extend(init_problems(name, path))
        names, unresolved = imports_of(name, path)
        result.problems.extend(unresolved)
        queue.extend(names)

    for name, path in sorted(result.modules.items()):
        imported_top = {
            n.split(".")[0] for n in imports_of(name, path)[0]
        }
        for forbidden in sorted(imported_top & SERVER_ONLY):
            result.problems.append(
                f"{path}: `{name}` imports `{forbidden}`, which a client of the API does "
                "not have; models must not need it"
            )
    result.problems = list(dict.fromkeys(result.problems))
    return result
