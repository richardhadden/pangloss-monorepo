"""`guide/cli.md` lists every command, grouped by package: each command and each of its options must be named there,
so that a new one, or a new option, is not forgotten (`pangloss <command> --help` is where the list comes from)"""

import importlib
import re
from pathlib import Path

import pytest
import typer
from pangloss_cli.main import build_app
from typer.main import get_command

GUIDE = Path(__file__).parents[3] / "guide" / "cli.md"
# The apps whose `cli.py` adds a group (`cli`, a Typer): all there are
APPS = [
    "pangloss_admin",
    "pangloss_calendar",
    "pangloss_derived",
    "pangloss_history",
    "pangloss_interface",
    "pangloss_memgraph",
    "pangloss_neo4j",
    "pangloss_review",
    "pangloss_rdf",
    "pangloss_sdk_server",
    "pangloss_typology",
    "pangloss_zotero",
]
# (typer's own, on a group run by itself)
NOT_OURS = {"--help", "--install-completion", "--show-completion", "--settings"}


def commands(command, path: list[str]):
    """Each command that is not hidden, as its words, with the options it takes"""
    if hasattr(command, "list_commands"):
        for name in command.list_commands(None):
            yield from commands(command.get_command(None, name), [*path, name])
    elif not command.hidden:
        options = [
            flag
            for parameter in command.params
            if not type(parameter).__name__.endswith("Argument")
            for flag in (*parameter.opts, *parameter.secondary_opts)
            if flag.startswith("--") and flag not in NOT_OURS
        ]
        yield " ".join(path), options


def every_command() -> list[tuple[str, list[str]]]:
    found = list(commands(get_command(build_app(argv=[])), ["pangloss"]))
    for app in APPS:
        cli = importlib.import_module(f"{app}.cli").cli
        assert isinstance(cli, typer.Typer)
        found += [
            item
            for item in commands(get_command(cli), ["pangloss", cli.info.name])
            if item not in found
        ]
    return found


def section_of(guide: str, command: str) -> str:
    """The rows of the guide that are about a command: where it is named, and the rows after it that go on about the
    same one (`… --plan`)"""
    words = command.split()
    name = re.compile(
        r"`pangloss "
        + re.escape(" ".join(words[1:-1]))
        + r"[^`|]*\b"
        + re.escape(words[-1])
        + r"\b[^`]*`"
        if len(words) > 2
        else r"`pangloss " + re.escape(words[-1]) + r"\b[^`]*`"
    )
    lines = guide.splitlines()
    rows: list[str] = []
    for index, line in enumerate(lines):
        if not name.search(line):
            continue
        rows.append(line)
        for more in lines[index + 1 :]:
            if not more.startswith("| …"):
                break
            rows.append(more)
    return "\n".join(rows)


def part_of(guide: str, command: str) -> str:
    """The part of the guide (under one `## `) that lists the command: an option every command of a package takes is
    said once there, above its table (`--runtime`)"""
    rows = section_of(guide, command)
    return next(
        (
            part
            for part in guide.split("\n## ")
            if rows and rows.splitlines()[0] in part
        ),
        "",
    )


def test_every_app_with_commands_is_in_the_list():
    packages = Path(__file__).parents[2]
    with_commands = sorted(
        module.parent.name
        for module in packages.glob("pangloss-*/src/*/cli.py")
        if module.parent.name not in ("pangloss_cli", "pangloss_sdk")
    )
    assert with_commands == sorted(APPS)


@pytest.mark.parametrize(
    "command,options",
    every_command(),
    ids=lambda value: value if isinstance(value, str) else "",
)
def test_the_guide_names_the_command_and_its_options(command: str, options: list[str]):
    guide = GUIDE.read_text()
    rows = section_of(guide, command)
    assert rows, f"guide/cli.md does not list `{command}`"
    above = part_of(guide, command).split("\n|", 1)[0]

    def named(option: str) -> bool:
        said = re.compile(re.escape(option) + r"(?![\w-])")
        return bool(said.search(rows) or said.search(above))

    missing = [
        option
        for option in options
        # (`--admin/--no-admin`: either says the option is there)
        if not named(option)
        and not named(option.replace("--no-", "--"))
        and not named(option.replace("--", "--no-", 1))
    ]
    assert not missing, f"guide/cli.md does not name {missing} of `{command}`"
