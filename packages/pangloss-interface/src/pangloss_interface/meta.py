"""`InterfaceMeta`: what the interface is told about a model, on the class (the meta slot
`_interface_meta`, see docs/meta-slots.md):

    class Negative[T](SemanticSpace[T]):
        _interface_meta = InterfaceMeta(colour="rose")

A subclass that sets none has its parent's.
"""

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


@dataclass(frozen=True)
class InterfaceMeta:
    """How the interface shows a model"""

    # The colour of the model's type wherever it is shown, and of the band round an item in a
    # semantic space. Without one: blue for entities, green for documents, and for a semantic
    # space a colour by how deep it is.
    colour: Colour | None = None

    def __post_init__(self) -> None:
        if self.colour is not None and self.colour not in COLOURS:
            raise PanglossMetaError(
                f"InterfaceMeta(colour={self.colour!r}): the colour must be one of Tailwind's base colours "
                f"(not black or white): {', '.join(COLOURS)}"
            )


def export_definitions() -> dict[str, Any]:
    """`export_models()`, with the `interfaceMeta` of each model: `{"colour": ...}`, or None"""
    from pangloss_models.export import export_models
    from pangloss_models.model_registry import ModelRegistry

    exported = export_models()
    classes = {
        model.__name__: model
        for model in ModelRegistry._models
        if not (getattr(model, "__pydantic_generic_metadata__", None) or {}).get("origin")
    }
    for name, definition in exported["models"].items():
        meta = getattr(classes.get(name), "_interface_meta", None)
        definition["interfaceMeta"] = (
            None if not isinstance(meta, InterfaceMeta) else {"colour": meta.colour}
        )
    return exported
