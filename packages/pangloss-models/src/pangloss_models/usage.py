"""Entities that are brought in by the thousand, of which only those something refers to are of interest.

    class ZoteroBacked(Entity):
        _usage_meta = Usage(include_only_when_referenced=True)

It says something about the data and does nothing itself: each package that shows or publishes a whole class decides
what to do with it (the interface's list pages, the RDF dump). An item nothing refers to is still an item, with its
page and its URI. `False` turns off a parent's; a function of the class is for a package whose base is used by classes
that differ.
"""

from collections.abc import Callable
from dataclasses import dataclass

from pangloss_models.exceptions import PanglossMetaError
from pangloss_models.meta_slots import register_meta_slot

SLOT = "_usage_meta"


@dataclass(frozen=True)
class Usage:
    include_only_when_referenced: bool | Callable[[type], bool]
    """True, False to turn off a parent's, or a function of the class (the subclass's own, when it is asked)"""

    def __post_init__(self) -> None:
        value = self.include_only_when_referenced
        if not (isinstance(value, bool) or callable(value)):
            raise PanglossMetaError(
                f"Usage(include_only_when_referenced={value!r}): True, False to turn off the parent's, or a "
                "function of the class"
            )


register_meta_slot(SLOT, Usage)


def included_only_when_referenced(model: type) -> bool:
    """Whether an item of this class is of interest only if something refers to it"""
    usage = getattr(model, SLOT, None)
    if usage is None:
        return False
    value = usage.include_only_when_referenced
    return bool(value(model) if callable(value) else value)


def check_usage(models: list[type]) -> None:
    """Called by `initialise()`. Only an entity is referred to as a thing in its own right"""
    from pangloss_models import Document

    for model in models:
        if issubclass(model, Document) and included_only_when_referenced(model):
            raise PanglossMetaError(
                f"{model.__name__}: Usage(include_only_when_referenced=...) is for an Entity, and this is a Document"
            )
