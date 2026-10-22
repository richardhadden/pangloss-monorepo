"""Making new projects and apps from templates (`pangloss new-project`, `new-app`)"""

import ast
import importlib.util
import keyword
import re
import secrets
import string
import tomllib
from dataclasses import dataclass
from importlib import resources
from pathlib import Path


class ScaffoldError(Exception):
    """Something stops the project or app being made (nothing has been written)"""


NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def check_name(name: str, directory: Path, what: str) -> None:
    """The name must be usable as a Python package, and not be taken"""
    if not NAME.match(name) or keyword.iskeyword(name):
        raise ScaffoldError(
            f"'{name}' cannot be the name of {what}: it must be a valid Python name "
            "(letters, numbers and '_', not starting with a number)"
            + (f". Perhaps '{name.replace('-', '_')}'?" if "-" in name else "")
        )
    if (directory / name).exists():
        raise ScaffoldError(f"'{directory / name}' already exists")
    if importlib.util.find_spec(name) is not None:
        raise ScaffoldError(
            f"'{name}' cannot be the name of {what}: there is already a Python module "
            "of that name"
        )


def render(template: str, **values: str) -> str:
    text = (resources.files("pangloss_cli") / "templates" / template).read_text()
    return string.Template(text).substitute(**values)


@dataclass
class Plan:
    """What would be written: files to create, and text to add to existing ones"""

    create: dict[Path, str]
    append: dict[Path, str]

    def apply(self) -> None:
        for path, text in self.create.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        for path, text in self.append.items():
            with path.open("a") as file:
                file.write(text)


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

MINIMAL_PYPROJECT = """[project]
name = "{name}"
version = "0.1.0"
requires-python = ">=3.14"
# Add the Pangloss packages you use, such as pangloss-cli and pangloss-memgraph
dependencies = []

{section}"""

PANGLOSS_SECTION = """[tool.pangloss]
settings = "{name}.settings"
"""

GITIGNORE = """.env
.venv/
__pycache__/
"""


def has_line(text: str, line: str) -> bool:
    return any(existing.strip() == line for existing in text.splitlines())


def plan_project(name: str, directory: Path) -> Plan:
    check_name(name, directory, "a project")

    plan = Plan(create={}, append={})
    section = PANGLOSS_SECTION.format(name=name)

    pyproject = directory / "pyproject.toml"
    if pyproject.exists():
        text = pyproject.read_text()
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError as error:
            raise ScaffoldError(f"Cannot read {pyproject}: {error}") from error
        if "pangloss" in data.get("tool", {}):
            raise ScaffoldError(
                f"{pyproject} already has a [tool.pangloss] section: this is already "
                "a Pangloss project"
            )
        plan.append[pyproject] = ("" if text.endswith("\n") else "\n") + "\n" + section
    else:
        plan.create[pyproject] = MINIMAL_PYPROJECT.format(
            name=name.replace("_", "-"), section=section
        )

    plan.create[directory / name / "__init__.py"] = ""
    plan.create[directory / name / "settings.py"] = render(
        "project/settings.py.tmpl", project_name=name
    )

    secret_line = f"AUTHJWT_SECRET_KEY={secrets.token_urlsafe(48)}\n"
    env = directory / ".env"
    if not env.exists():
        plan.create[env] = secret_line
    elif "AUTHJWT_SECRET_KEY=" not in env.read_text():
        text = env.read_text()
        plan.append[env] = ("" if text.endswith("\n") or not text else "\n") + secret_line

    gitignore = directory / ".gitignore"
    if not gitignore.exists():
        plan.create[gitignore] = GITIGNORE
    elif not has_line(gitignore.read_text(), ".env"):
        text = gitignore.read_text()
        plan.append[gitignore] = ("" if text.endswith("\n") or not text else "\n") + ".env\n"

    return plan


# ---------------------------------------------------------------------------
# Apps
# ---------------------------------------------------------------------------


def plan_app(name: str, project_root: Path) -> Plan:
    check_name(name, project_root, "an app")
    return Plan(
        create={
            project_root / name / "__init__.py": "",
            project_root / name / "models.py": render(
                "app/models.py.tmpl", app_name=name
            ),
        },
        append={},
    )


def offset_of(source: str, line: int, byte_column: int) -> int:
    """Where (line, column) is in the text (`ast` columns are UTF-8 bytes)"""
    lines = source.splitlines(keepends=True)
    prefix = lines[line - 1].encode()[:byte_column].decode()
    return sum(len(text) for text in lines[: line - 1]) + len(prefix)


def installed_apps_list(tree: ast.AST) -> ast.List | None:
    """The list literal assigned to `INSTALLED_APPS`, if there is exactly one"""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        if any(isinstance(t, ast.Name) and t.id == "INSTALLED_APPS" for t in targets):
            found.append(value)
    if len(found) != 1 or not isinstance(found[0], ast.List):
        return None
    if not all(
        isinstance(e, ast.Constant) and isinstance(e.value, str) for e in found[0].elts
    ):
        return None
    return found[0]


def add_to_installed_apps(source: str, app: str) -> str | None:
    """The settings source with `app` added to the `INSTALLED_APPS` list, or None if
    that cannot be done reliably (it is not a plain list of strings). The text is
    otherwise left as it was."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    node = installed_apps_list(tree)
    if node is None:
        return None
    if any(isinstance(e, ast.Constant) and e.value == app for e in node.elts):
        return source

    start = offset_of(source, node.lineno, node.col_offset)
    end = offset_of(source, node.end_lineno, node.end_col_offset)  # ty: ignore[invalid-argument-type]
    quoted = f'"{app}"'

    if not node.elts:
        edited = source[:start] + f"[{quoted}]" + source[end:]
    else:
        last_element = node.elts[-1]
        last = offset_of(source, last_element.end_lineno, last_element.end_col_offset)  # ty: ignore[invalid-argument-type]
        if node.lineno == node.end_lineno or node.end_lineno == last_element.end_lineno:
            # The last one shares its line with the end of the list: `["a", "b"]`
            edited = source[:last] + f", {quoted}" + source[last:]
        else:
            # One to a line: the new one goes on a line of its own, after the line of
            # the last (and any comment on it)
            indent_line = source.splitlines()[last_element.lineno - 1]
            indent = indent_line[: len(indent_line) - len(indent_line.lstrip())]
            line_end = source.index("\n", last)
            between = source[last:line_end]
            if between.lstrip().startswith(","):
                edited = source[:line_end] + f"\n{indent}{quoted}," + source[line_end:]
            else:
                edited = (
                    source[:last]
                    + ","
                    + between
                    + f"\n{indent}{quoted}"
                    + source[line_end:]
                )

    # Check the result is what was meant
    try:
        new_node = installed_apps_list(ast.parse(edited))
    except SyntaxError:
        return None
    if new_node is None or [e.value for e in new_node.elts] != [  # ty: ignore[unresolved-attribute]
        *[e.value for e in node.elts],  # ty: ignore[unresolved-attribute]
        app,
    ]:
        return None
    return edited


def settings_file(module: str, project_root: Path) -> Path | None:
    """The file of a settings module (`my_project.settings`), if it is there"""
    base = project_root.joinpath(*module.split("."))
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None
