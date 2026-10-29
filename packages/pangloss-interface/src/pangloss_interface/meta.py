"""`InterfaceMeta`: what the interface is told about a model, on the class (the meta slot
`_interface_meta`, see docs/meta-slots.md):

    class Negative[T](SemanticSpace[T]):
        _interface_meta = InterfaceMeta(colour="rose")

A subclass that sets none has its parent's.
"""

import re
from dataclasses import dataclass
from typing import Any, Literal, get_args

from pangloss_models.exceptions import PanglossMetaError

# The base colours of Tailwind, except black and white. (The interface has the same list in
# `interface-core/src/types/models.ts`; a test holds the two together.)
Colour = Literal[
    "slate",
    "gray",
    "zinc",
    "neutral",
    "stone",
    "mauve",
    "olive",
    "mist",
    "taupe",
    "red",
    "orange",
    "amber",
    "yellow",
    "lime",
    "green",
    "emerald",
    "teal",
    "cyan",
    "sky",
    "blue",
    "indigo",
    "violet",
    "purple",
    "fuchsia",
    "pink",
    "rose",
]
COLOURS: tuple[str, ...] = get_args(Colour)


# Where the interface finds a component for a model: "<app>:<name>", the name of an installed app and
# a key of `components` in the manifest of its interface module (docs/interface-modules-implementation.md)
ComponentRef = str
COMPONENT_REF = re.compile(r"^([A-Za-z_]\w*):([A-Za-z_]\w*)$")
# (`False` turns off one that a parent model names: the generic page or card is used again)
Slot = ComponentRef | Literal[False] | None
SLOTS = ("list_page", "item_page", "view_card", "edit_card")


@dataclass(frozen=True)
class InterfaceMeta:
    """How the interface shows a model. A field that is not set (None) is the parent's; `False`
    turns off a component that a parent names."""

    # The colour of the model's type wherever it is shown, and of the band round an item in a
    # semantic space. Without one: blue for entities, green for documents, and for a semantic
    # space a colour by how deep it is.
    colour: Colour | None = None
    # A component of an interface module, for the whole page of the list of the type
    list_page: Slot = None
    # ... for the whole page of one item
    item_page: Slot = None
    # ... for a card that shows an item where it is part of something else (a result in a list,
    # a reference, an embedded item)
    view_card: Slot = None
    # ... for a card (a form) that edits an item
    edit_card: Slot = None

    def __post_init__(self) -> None:
        if self.colour is not None and self.colour not in COLOURS:
            raise PanglossMetaError(
                f"InterfaceMeta(colour={self.colour!r}): the colour must be one of Tailwind's base colours "
                f"(not black or white): {', '.join(COLOURS)}"
            )
        for slot in SLOTS:
            value = getattr(self, slot)
            if value is None or value is False:
                continue
            if not isinstance(value, str) or not COMPONENT_REF.match(value):
                raise PanglossMetaError(
                    f"InterfaceMeta({slot}={value!r}): a component is named '<app>:<Name>' "
                    "(an installed app, and a key of 'components' in its interface module), or False "
                    "to turn off the parent's"
                )


def split_reference(reference: str) -> dict[str, str]:
    app, name = reference.split(":")
    return {"module": app, "name": name}


def resolved_meta(model: type) -> dict[str, Any] | None:
    """The `InterfaceMeta` of a class, field by field: each from the nearest class (the class
    itself, then its parents) that sets it. None if no class sets any."""
    metas = [
        meta
        for klass in model.__mro__
        if isinstance(meta := klass.__dict__.get("_interface_meta"), InterfaceMeta)
    ]
    if not metas:
        # (a slot that is not in `__dict__`, as an older class has it)
        meta = getattr(model, "_interface_meta", None)
        metas = [meta] if isinstance(meta, InterfaceMeta) else []
    if not metas:
        return None
    resolved: dict[str, Any] = {
        "colour": next((m.colour for m in metas if m.colour is not None), None)
    }
    for slot in SLOTS:
        value = next((v for m in metas if (v := getattr(m, slot)) is not None), None)
        resolved[_camel(slot)] = (
            split_reference(value) if isinstance(value, str) else None
        )
    return resolved


def _camel(name: str) -> str:
    first, *rest = name.split("_")
    return first + "".join(word.title() for word in rest)


def export_definitions() -> dict[str, Any]:
    """`export_models()`, with the `interfaceMeta` of each model: `{"colour": ..., "listPage": {"module",
    "name"} or None, ...}`, resolved through the parents, or None for a model with none"""
    from pangloss_models.export import export_models
    from pangloss_models.model_registry import ModelRegistry

    exported = export_models()
    classes = {
        model.__name__: model
        for model in ModelRegistry._models
        if not (getattr(model, "__pydantic_generic_metadata__", None) or {}).get("origin")
    }
    from pangloss_core import settings as core_settings

    from pangloss_interface.config import export_nav

    apps = getattr(core_settings.__dict__.get("SETTINGS"), "INSTALLED_APPS", [])
    exported["nav"] = export_nav(apps, exported["models"])
    for name, definition in exported["models"].items():
        cls = classes.get(name)
        definition["interfaceMeta"] = None if cls is None else resolved_meta(cls)
    return exported
