"""The source of a module as the SDK ships it: as written, except that the body of a function
marked `@server_only` is replaced by one that raises `PanglossServerOnly` (and the imports
inside it are not read: see `closure`), and that what it imports from `pangloss_interface` comes
from `pangloss_sdk.no_interface` (how a model is shown is not data: a client does not have the
interface, and what is declared with it is ignored there)."""

import ast
import re

INTERFACE = "pangloss_interface"
STAND_IN = "pangloss_sdk.no_interface"
# (what `pangloss_sdk.no_interface` has: the names a model is declared with)
STAND_IN_NAMES = ("Collapse", "Colour", "InterfaceMeta", "Slider")
INTERFACE_IMPORT = re.compile(rf"\bfrom\s+{INTERFACE}(\.[\w.]+)?\s+import\b")


def is_interface(module: str | None) -> bool:
    return module == INTERFACE or (module or "").startswith(INTERFACE + ".")


def interface_imports(
    tree: ast.AST, lines: list[str], filename: str
) -> tuple[list[int], list[str]]:
    """The lines (from 1) that import from `pangloss_interface` in a way the SDK can ship, and what is wrong with
    those it cannot"""
    found: list[int] = []
    problems: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(is_interface(alias.name) for alias in node.names):
                problems.append(
                    f"{filename}:{node.lineno}: `import {INTERFACE}` cannot be shipped in an SDK (a client does "
                    f"not have the interface): import the names, `from {INTERFACE} import InterfaceMeta`"
                )
        elif isinstance(node, ast.ImportFrom) and not node.level:
            if not is_interface(node.module):
                continue
            wrong = sorted(
                alias.name for alias in node.names if alias.name not in STAND_IN_NAMES
            )
            if wrong:
                problems.append(
                    f"{filename}:{node.lineno}: {', '.join(wrong)} of `{INTERFACE}` cannot be shipped in an SDK "
                    f"(a client does not have the interface; only {', '.join(STAND_IN_NAMES)}, which models are "
                    "declared with, are ignored there): keep it out of the modules the models import"
                )
            elif not INTERFACE_IMPORT.search(lines[node.lineno - 1]):
                problems.append(
                    f"{filename}:{node.lineno}: write `from {INTERFACE} import` on one line, so that the SDK can "
                    "ship the module without the interface"
                )
            else:
                found.append(node.lineno)
    return found, problems


FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef


def is_server_only(node: ast.AST) -> bool:
    """Whether a function is decorated `@server_only` (or `@something.server_only`)"""
    if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        return False
    for decorator in node.decorator_list:
        name = (
            decorator.attr
            if isinstance(decorator, ast.Attribute)
            else getattr(decorator, "id", None)
        )
        if name == "server_only":
            return True
    return False


class ServerOnlyProblem(Exception):
    pass


def shipped_source(text: str, filename: str = "<module>") -> str:
    """The source to ship. Text is changed, not the tree, so that the file keeps its comments
    and layout"""
    tree = ast.parse(text, filename=filename)
    lines = text.split("\n")
    replacements: list[tuple[int, int, list[str]]] = []

    found, problems = interface_imports(tree, lines, filename)
    if problems:
        raise ServerOnlyProblem("\n".join(problems))
    for number in found:
        lines[number - 1] = INTERFACE_IMPORT.sub(
            f"from {STAND_IN} import", lines[number - 1], count=1
        )

    for node in ast.walk(tree):
        if not is_server_only(node):
            continue
        assert isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        body = node.body
        keep_docstring = (
            isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        )
        start = body[1] if keep_docstring and len(body) > 1 else body[0]
        if keep_docstring and len(body) == 1:
            continue  # (only a docstring: nothing to take out)
        if start.lineno == node.lineno:
            raise ServerOnlyProblem(
                f"{filename}:{node.lineno}: the body of the `@server_only` function "
                f"`{node.name}` is on the line of its `def`: put it on its own lines"
            )
        # (the first line of the statement, with the comments before it kept above)
        indent = " " * start.col_offset
        replacements.append(
            (
                start.lineno,
                node.end_lineno or start.lineno,
                [
                    f"{indent}from pangloss_models.exceptions import PanglossServerOnly",
                    f"{indent}raise PanglossServerOnly("
                    f"{node.name!r} + ' is only available on the server')",
                ],
            )
        )

    # (from the end, so that the line numbers of the rest stay right; a function inside another
    # server-only one is gone with it)
    last_start = None
    for start, end, new in sorted(replacements, reverse=True):
        if last_start is not None and end >= last_start:
            continue
        lines[start - 1 : end] = new
        last_start = start
    return "\n".join(lines)
