"""The source of a module as the SDK ships it: as written, except that the body of a function
marked `@server_only` is replaced by one that raises `PanglossServerOnly` (and the imports
inside it are not read: see `closure`)."""

import ast

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef


def is_server_only(node: ast.AST) -> bool:
    """Whether a function is decorated `@server_only` (or `@something.server_only`)"""
    if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        return False
    for decorator in node.decorator_list:
        name = decorator.attr if isinstance(decorator, ast.Attribute) else getattr(decorator, "id", None)
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
