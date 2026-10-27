"""The texts that the models give (the default language), as a flat map of paths to text.

A path has no language: `("models", "Person", "fields", "birth_place", "name")`. The files put the
language after the entity (`("models", "Person", "de", "fields", ...)`, see `paths.py`).

What there is for:

    models   name, plural, description, help;  fields:   name, plural, help;
             incoming (relations from other models): name, plural, help
    enums    name, plural, description, help;  members:  name

Where a text comes from: the name is the verbose name (`Field(title=...)`) if there is one, else the
name in the code, written as words ("BirthRecord" is "Birth record"); the description is the
docstring; the help of a field is `Field(description=...)`; a plural and the help of a model are empty
(an empty plural means: use the singular).
"""

import annotationlib
import enum
import re
from dataclasses import dataclass, field
from typing import Any

from pangloss_models.exceptions import PanglossInitialisationError
from pangloss_models.migrations.planner import app_of_module
from pangloss_models.model_registry import ModelRegistry

from pangloss_interface.i18n.paths import Path

ENTITY_KEYS = ("name", "plural", "description", "help")
ITEM_KEYS = ("name", "plural", "help")


def words(name: str, member: bool = False) -> str:
    """A name in code as words: `BirthRecord` and `birth_record` are "Birth record"; a member
    `RED_WINE` is "Red wine" (but `HTTPError` is "HTTP error")"""
    if member and name.isupper():
        return name.replace("_", " ").capitalize()
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", name)
    parts = spaced.replace("_", " ").split()
    if not parts:
        return name
    lowered = [p if p.isupper() and len(p) > 1 else p.lower() for p in parts]
    first = lowered[0]
    lowered[0] = first[0].upper() + first[1:]
    return " ".join(lowered)


@dataclass
class Extracted:
    """What the models give"""

    # (section, entity, *rest) -> text, in a steady order
    texts: dict[Path, str] = field(default_factory=dict)
    # (section, entity) -> the installed app it belongs to
    apps: dict[tuple[str, str], str] = field(default_factory=dict)
    # model -> {field name: the models that say it, from the model up (see `field_chain`)}
    field_chain: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    # model -> its kind ("Entity", "Document", ...)
    kinds: dict[str, str] = field(default_factory=dict)

    def entities(self, app: str | None = None) -> list[tuple[str, str]]:
        return [key for key, owner in self.apps.items() if app in (None, owner)]

    def texts_of(self, app: str) -> dict[Path, str]:
        mine = {key for key, owner in self.apps.items() if owner == app}
        return {p: t for p, t in self.texts.items() if p[:2] in mine}


def declares(cls: type, field_name: str) -> bool:
    """Whether the class itself says the field (it is in its own annotations), not only has it by
    inheritance"""
    try:
        return field_name in annotationlib.get_annotations(
            cls, format=annotationlib.Format.FORWARDREF
        )
    except TypeError, AttributeError:
        return False


def field_chain(
    model: type, field_name: str, apps: list[str], known: set[str]
) -> list[str]:
    """The models that say a field, from this one up: a class that redeclares a field (to narrow it)
    is in the chain with the class it narrows. The last is the base-most, which has the texts of the
    field; a redeclaring class has its own, empty, which are used if they are filled in."""
    chain = [
        cls.__name__
        for cls in model.__mro__
        if field_name in (getattr(cls, "model_fields", None) or {})
        and cls.__name__ in known
        and app_of_module(cls.__module__, apps) is not None
        and declares(cls, field_name)
    ]
    # (the base-most class that has the field says it, whether or not the annotations show it)
    base_most = [
        cls.__name__
        for cls in model.__mro__
        if field_name in (getattr(cls, "model_fields", None) or {})
        and cls.__name__ in known
        and app_of_module(cls.__module__, apps) is not None
    ]
    if base_most and base_most[-1] not in chain:
        chain.append(base_most[-1])
    return chain or [model.__name__]


def verbose_name(definition: Any) -> str | None:
    try:
        return definition.model_field.title or None
    except PanglossInitialisationError:  # (not yet available: the name in code is used)
        return None


def help_of(definition: Any) -> str:
    text = getattr(definition, "description", None)
    if not text:
        try:
            text = definition.model_field.description
        except PanglossInitialisationError:
            text = None
    return (text or "").strip()


def enum_classes() -> dict[str, type[enum.Enum]]:
    """Every enum class by name (the export knows enums by name)"""
    found: dict[str, type[enum.Enum]] = {}
    pending = list(enum.Enum.__subclasses__())
    while pending:
        cls = pending.pop()
        pending.extend(cls.__subclasses__())
        found.setdefault(cls.__name__, cls)
    return found


def extract(exported: dict[str, Any], apps: list[str]) -> Extracted:
    """The texts of the models and enums of `export_models()`, for those in the installed apps
    (a model in no app, such as one made in a function, has no file to go in)"""
    result = Extracted()
    registry = ModelRegistry.all_models()

    for name, entry in sorted(exported["models"].items()):
        model = registry.get(name)
        app = app_of_module(model.__module__, apps) if model else None
        if model is None or app is None:
            continue
        key = ("models", name)
        result.apps[key] = app
        result.texts[(*key, "name")] = words(name)
        result.texts[(*key, "plural")] = ""
        result.texts[(*key, "description")] = entry.get("description") or ""
        result.texts[(*key, "help")] = ""

        definitions = model._meta.field_definitions  # type: ignore[attr-defined]
        result.kinds[name] = entry["kind"]
        chains: dict[str, list[str]] = {}
        for field_entry in entry["fields"]:
            field_name = field_entry["name"]
            definition = definitions.fields[field_name]
            chain = field_chain(model, field_name, apps, set(exported["models"]))
            chains[field_name] = chain
            if name not in chain:
                continue  # (translated where it is declared)
            item = (*key, "fields", field_name)
            first = (
                chain[-1] == name
            )  # (the base-most has the texts; a narrowing class, none)
            result.texts[(*item, "name")] = (
                verbose_name(definition) or words(field_name) if first else ""
            )
            result.texts[(*item, "plural")] = ""
            result.texts[(*item, "help")] = help_of(definition) if first else ""
        result.field_chain[name] = chains

        for incoming in entry["incoming"]:
            item = (*key, "incoming", incoming["name"])
            result.texts[(*item, "name")] = words(incoming["name"])
            result.texts[(*item, "plural")] = ""
            result.texts[(*item, "help")] = ""

    classes = enum_classes()
    for name, entry in sorted(exported["enums"].items()):
        cls = classes.get(name)
        app = app_of_module(cls.__module__, apps) if cls else None
        if cls is None or app is None:
            continue
        key = ("enums", name)
        result.apps[key] = app
        doc = cls.__dict__.get("__doc__")
        result.texts[(*key, "name")] = words(name)
        result.texts[(*key, "plural")] = ""
        result.texts[(*key, "description")] = (doc or "").strip()
        result.texts[(*key, "help")] = ""
        for member in entry["members"]:
            result.texts[(*key, "members", member["name"], "name")] = words(
                member["name"], member=True
            )
    return result
