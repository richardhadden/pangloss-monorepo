"""The parts of a dump that are not documents and entities, which other packages add (what is derived from them,
`pangloss-derived`).

Apart from `dump`, and importing nothing of the conversion, because an app's `rdf.py` imports this to add its part:
importing `pangloss_rdf.convert` (the module) before the package's own `convert` (the function, imported lazily) has
been used leaves the package with the module under that name.
"""

from collections.abc import AsyncIterator, Callable, Iterable
from dataclasses import dataclass

from pangloss_rdf.terms import Quad


@dataclass(frozen=True)
class DumpSection:
    """A part of a dump that is not the documents and entities, which another package adds (what is derived from
    them, `pangloss-derived`). Left out unless asked for by its name (`dump(include=["derived"])`,
    `pangloss rdf dump --include-derived`).

    - `quads()`: an async iterator of the quads of one item after another (what a reader who is not logged in can
      see, unless `see_unpublished` is set: `dump` sets it before);
    - `ontology()`: the terms it uses, for the ontology written with it (`ontology_quads(include=[name])`)."""

    name: str
    quads: Callable[[], AsyncIterator[list[Quad]]]
    ontology: Callable[[], Iterable[Quad]] | None = None


_sections: dict[str, DumpSection] = {}


def register_dump_section(section: DumpSection) -> None:
    """A package does this in its `rdf.py` module, found by name in `INSTALLED_APPS` (as its converters are), so it
    need not depend on this one"""
    _sections[section.name] = section


def dump_sections() -> dict[str, DumpSection]:
    """The sections the installed apps have added, by name"""
    from pangloss_rdf.convert import load_app_converters

    load_app_converters()
    return dict(_sections)


def sections_named(names: Iterable[str]) -> list[DumpSection]:
    known = dump_sections()
    found = []
    for name in names:
        if name not in known:
            there = ", ".join(sorted(known)) or "none"
            raise ValueError(
                f"There is no part of a dump called {name!r} (there are: {there}): is the app that adds it in "
                "INSTALLED_APPS?"
            )
        found.append(known[name])
    return found
