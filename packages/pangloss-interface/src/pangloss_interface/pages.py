"""A project's own pages: the files of `<project>/pages/` (docs/homepage-and-pages.md). The application reads the names
the same way (`interface-core/src/schema/pageFiles.ts`)."""

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

PAGES_DIRECTORY = "pages"
HOME_FILE = "index.tsx"
PAGE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9 _-]*$")


def pages_directory(project_root: Path) -> Path:
    return project_root / PAGES_DIRECTORY


def file_stem(name: str) -> str:
    """What a page called `name` is saved as: `Our Team` is `Our-Team`"""
    return re.sub(r"\s+", "-", name.strip())


def component_name(name: str) -> str:
    """A name for its function: `Our Team` is `OurTeam`"""
    return "".join(
        part[:1].upper() + part[1:] for part in re.split(r"[\s_-]+", name) if part
    )


def slug_of(stem: str) -> str:
    """The address of a file, by the name without `.tsx`: `_10-Our_Team` is `our-team`"""
    return re.sub(r"^\d+[-_]", "", stem.removeprefix("_")).lower().replace("_", "-")


def page_problems(
    project_root: Path, exported: dict[str, Any], routes: Iterable[str]
) -> list[str]:
    """The pages whose addresses are taken: by another page, a model, or a page of an interface module"""
    directory = pages_directory(project_root)
    if not directory.is_dir():
        return []
    taken = {name.lower(): f"the model {name}" for name in exported.get("models", {})}
    for route in routes:
        first = route.strip("/").split("/")[0]
        if first and not first.startswith((":", "*")):
            taken[first.lower()] = f"the route {route}"
    taken["api"] = "the API"
    wrong = []
    for file in sorted(directory.glob("*.tsx")):
        if file.name == HOME_FILE:
            continue
        slug = slug_of(file.stem)
        if slug in taken:
            wrong.append(
                f"pages/{file.name}: the address /{slug} is that of {taken[slug]}"
            )
        taken.setdefault(slug, f"pages/{file.name}")
    return wrong
