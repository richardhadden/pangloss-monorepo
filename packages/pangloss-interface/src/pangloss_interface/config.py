"""`InterfaceConfig`: what an app tells the interface that is not about one model. For now, where its
links go in the navigation bar (docs/interface-modules-implementation.md, 4.4).

An app has it in `<app>/interface_config.py`, as `config`:

    config = InterfaceConfig(
        nav=[
            NavModel("Manuscript", label="Manuscripts", section="Sources", order=10),
            NavModel("Folio", hidden=True),
            NavLink("Collation chart", href="/manuscripts/collation", section="Sources", order=20),
        ],
        sections=["Sources"],
    )

`merge` takes the configs of the installed apps, in the order of `INSTALLED_APPS`; for the same type
the later app wins, so the project's own app has the last word. What it returns is what the interface
reads (`nav` in the exported definitions); the hierarchy of the types is drawn by the interface, as
it always was, so a type with no entry stays where it is.
"""

import importlib
import importlib.util
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from pangloss_models.exceptions import PanglossMetaError

# (the sections the bar has without any configuration, first and in this order)
DEFAULT_SECTIONS = ("Entities", "Documents")
CONFIG_MODULE = "interface_config"


@dataclass(frozen=True)
class NavModel:
    """A type's place in the bar: its link is to `/<model>`"""

    model: str
    label: str | None = None  # (default: the model's name)
    section: str | None = None  # (default: Entities or Documents, by kind)
    order: int | None = (
        None  # (entries with an order come first, by it; the rest in the order of the hierarchy)
    )
    hidden: bool = False  # (kept out of the bar; its page is still at /<model>)


@dataclass(frozen=True)
class NavLink:
    """Any other link: a page of an interface module, or an address elsewhere"""

    label: str
    href: str
    section: str | None = None
    order: int | None = None
    external: bool = False
    requires_login: bool = False

    def __post_init__(self) -> None:
        if not self.external and not self.href.startswith("/"):
            raise PanglossMetaError(
                f"NavLink({self.label!r}): href {self.href!r} is inside the interface, so starts with '/' "
                "(or the link is external=True)"
            )


@dataclass(frozen=True)
class InterfaceConfig:
    nav: Sequence[NavModel | NavLink] = field(default_factory=tuple)
    # The sections that this app introduces, in order (a section that only entries name comes
    # after these, in the order they are met)
    sections: Sequence[str] = field(default_factory=tuple)


def label_slot(app: str, label: str) -> str:
    """The UI translation slot of a link's label: `nav_<app>_<label>`, in `snake_case`. The label as
    written is the default-language text, so a link needs no entry in `ui.jsonc` until it is translated."""
    slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    return f"nav_{app}_{slug}"


def nav_defaults(configs: Iterable[tuple[str, InterfaceConfig]]) -> dict[str, str]:
    """Slot to default text, for every label the configs give (a type without one: its name)"""
    texts = {}
    for app, config in configs:
        for entry in config.nav:
            label = (
                entry.label
                if isinstance(entry, NavLink)
                else (entry.label or entry.model)
            )
            texts[label_slot(app, label)] = label
    return texts


def load_configs(installed_apps: Iterable[str]) -> list[tuple[str, InterfaceConfig]]:
    """The `config` of each installed app that has an `interface_config` module, in order"""
    found = []
    for app in installed_apps:
        name = f"{app}.{CONFIG_MODULE}"
        try:
            if importlib.util.find_spec(name) is None:
                continue
        except ModuleNotFoundError:  # (the app itself is not importable: others say so)
            continue
        config = getattr(importlib.import_module(name), "config", None)
        if not isinstance(config, InterfaceConfig):
            raise PanglossMetaError(
                f"{name} has to define `config = InterfaceConfig(...)`"
            )
        found.append((app, config))
    return found


def merge(
    configs: Iterable[tuple[str, InterfaceConfig]],
    models: Iterable[str] | None = None,
) -> dict[str, Any]:
    """The configs of the apps as one `nav` for the interface: `sections` (their titles in order),
    `models` (by name: label, section, order, hidden) and `links`. With `models` given, a
    `NavModel` for a type that is not one is an error that names the app."""
    known = None if models is None else set(models)
    sections: list[str] = list(DEFAULT_SECTIONS)
    placed: dict[str, dict[str, Any]] = {}
    links: dict[tuple[str, str, str], dict[str, Any]] = {}

    def add_section(title: str | None) -> None:
        if title and title not in sections:
            sections.append(title)

    for app, config in configs:
        for title in config.sections:
            add_section(title)
        for entry in config.nav:
            add_section(entry.section)
            if isinstance(entry, NavModel):
                if known is not None and entry.model not in known:
                    raise PanglossMetaError(
                        f"{app}.{CONFIG_MODULE}: NavModel({entry.model!r}) is not a model of the project"
                    )
                placed[entry.model] = {
                    "label": entry.label,
                    "labelSlot": label_slot(app, entry.label or entry.model),
                    "section": entry.section,
                    "order": entry.order,
                    "hidden": entry.hidden,
                }
            else:
                # (the same link again, from a later app, replaces it)
                links[(entry.section or "", entry.label, entry.href)] = {
                    "label": entry.label,
                    "labelSlot": label_slot(app, entry.label),
                    "href": entry.href,
                    "section": entry.section,
                    "order": entry.order,
                    "external": entry.external,
                    "requiresLogin": entry.requires_login,
                }
    return {"sections": sections, "models": placed, "links": list(links.values())}


def export_nav(installed_apps: Iterable[str], models: Iterable[str]) -> dict[str, Any]:
    return merge(load_configs(installed_apps), models)
