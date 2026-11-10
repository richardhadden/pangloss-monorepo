#!/usr/bin/env python3
"""Checks that the Pangloss skill still fits the repository it describes

    python3 .claude/skills/pangloss/scripts/check_skill.py

It looks, in `SKILL.md` and `references/*.md`, for what can be checked without judgement:

- a path of the repository in backticks (`implementation_docs/models.md`, `packages/pangloss-core`) that is not there;
- a module or name in backticks (`pangloss_core.backend.current()`) that is not there;
- a link to a file of the skill that is not there;
- a package of `packages/` that the skill does not mention.

It cannot tell whether what the skill *says* is still true: that is for whoever makes a change (see "Keeping this
skill current" in `SKILL.md`). Exits 1 with a list if anything is found. Needs only the standard library.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
# (.claude/skills/pangloss -> the repository)
REPOSITORY = SKILL.parent.parent.parent

# What a path of the repository starts with
ROOTS = (
    "implementation_docs/",
    "guide/",
    "packages/",
    "e2e/",
    "notes/",
    "pangloss-demo/",
    "sdk-demo/",
    ".claude/",
)
ROOT_FILES = {
    "run_tests.sh",
    "TODO.md",
    "README.md",
    "pyproject.toml",
    "uv.lock",
    ".python-version",
}
# (a placeholder, a pattern or an ellipsis: not a path to look for)
NOT_LITERAL = re.compile(r"[<>*{}…\s]|NNNN")

BACKTICKED = re.compile(r"`([^`\n]+)`")
LINK = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")
DOTTED = re.compile(r"^(pangloss_[a-z0-9_]+)((?:\.[A-Za-z_][A-Za-z0-9_]*)+)")
# (the longest SKILL.md that is still read before starting work)
MOST_LINES = 500


def skill_files() -> list[Path]:
    return [SKILL / "SKILL.md", *sorted((SKILL / "references").glob("*.md"))]


def source_of(top: str) -> Path | None:
    """The directory of the top-level module `top` (`pangloss_core`) in the workspace"""
    found = sorted(REPOSITORY.glob(f"packages/*/src/{top}"))
    return found[0] if found else None


def missing_name(top: str, rest: list[str]) -> str | None:
    """What of `top.rest...` is not there, or `None`: modules are followed as files, and the first name after
    the last module is looked for in the text of that module"""
    here = source_of(top)
    if here is None:
        return top
    for position, part in enumerate(rest):
        if (here / part).is_dir():
            here = here / part
        elif (here / f"{part}.py").is_file():
            here = here / f"{part}.py"
        else:
            module = here / "__init__.py" if here.is_dir() else here
            if not module.is_file() or not re.search(
                rf"\b{re.escape(part)}\b", module.read_text(encoding="utf-8")
            ):
                return ".".join([top, *rest[: position + 1]])
            # (a name in a module: what follows it is an attribute, which is not followed)
            return None
    return None


def problems_of(file: Path) -> list[str]:
    problems = []
    text = file.read_text(encoding="utf-8")
    where = file.relative_to(SKILL)

    for token in BACKTICKED.findall(text):
        token = token.strip()
        if token.startswith(ROOTS) or token in ROOT_FILES:
            if NOT_LITERAL.search(token):
                continue
            if not (REPOSITORY / token).exists():
                problems.append(f"{where}: `{token}` is not in the repository")
            continue
        named = DOTTED.match(token)
        if named and ":" not in token and "<" not in token:
            top, rest = named.group(1), named.group(2).strip(".").split(".")
            missing = missing_name(top, rest)
            if missing:
                problems.append(f"{where}: `{token}`: there is no `{missing}`")

    for target in LINK.findall(text):
        if "://" in target or target.startswith("mailto:"):
            continue
        if not (file.parent / target).exists():
            problems.append(f"{where}: the link to {target} leads nowhere")

    return problems


def unmentioned_packages(everything: str) -> list[str]:
    return [
        f"the package `{package.name}` is not mentioned anywhere in the skill"
        for package in sorted((REPOSITORY / "packages").iterdir())
        if (package / "pyproject.toml").is_file() and package.name not in everything
    ]


def main() -> int:
    if not (REPOSITORY / "packages").is_dir():
        print(
            f"{REPOSITORY} is not the Pangloss repository (the skill has been copied elsewhere): nothing to check"
        )
        return 0

    files = skill_files()
    problems = [problem for file in files for problem in problems_of(file)]
    problems += unmentioned_packages(
        "\n".join(file.read_text(encoding="utf-8") for file in files)
    )
    lines = len((SKILL / "SKILL.md").read_text(encoding="utf-8").splitlines())
    if lines > MOST_LINES:
        problems.append(
            f"SKILL.md has {lines} lines (more than {MOST_LINES}): move detail to a reference file"
        )

    if problems:
        print("The Pangloss skill no longer fits the repository:\n")
        for problem in problems:
            print(f"  - {problem}")
        print(
            "\nCorrect .claude/skills/pangloss (see 'Keeping this skill current' in its SKILL.md)."
        )
        return 1
    print(
        f"The Pangloss skill fits the repository ({len(files)} files, {lines} lines in SKILL.md)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
