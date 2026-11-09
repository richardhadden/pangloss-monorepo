"""`_rdf_meta`: what a class is called in RDF.

    class Person(Entity):
        _rdf_meta = RDFMeta(class_name="HistoricalPerson")

`exclude` and `dump` are inherited as any slot is. A name is not: a subclass with its parent's name would have its parent's URI, so
`class_name` and `class_uri` count only on the class that says them.
"""

import re
from dataclasses import dataclass
from typing import Literal

from pangloss_models import included_only_when_referenced, register_meta_slot
from pangloss_models.exceptions import PanglossMetaError
from pangloss_models.meta_slots import declared_slots

SLOT = "_rdf_meta"

# (a dot joins a class to its property, and a slash divides a URI: neither may be in a name)
_NAME = re.compile(r"[^\W\d][\w-]*")
_ABSOLUTE = re.compile(r"[a-zA-Z][a-zA-Z0-9+.-]*:\S+")


def is_valid_name(name: str) -> bool:
    return _NAME.fullmatch(name) is not None


@dataclass(frozen=True)
class RDFMeta:
    class_name: str | None = None
    """Replaces the name of the class in its class URI and in the URIs of its items"""
    class_uri: str | None = None
    """A whole URI, to use an outside class as this class itself"""
    exclude: bool = False
    """The class is not exported, nor any relation to it"""
    dump: Literal["all", "used"] | None = None
    """(an Entity only) Whether a dump has every item or only those something refers to, whatever the class's `Usage`
    says. The item's URI resolves either way"""

    def __post_init__(self) -> None:
        if self.class_name is not None and self.class_uri is not None:
            raise PanglossMetaError("RDFMeta: give class_name or class_uri, not both")
        if self.class_name is not None and not is_valid_name(self.class_name):
            raise PanglossMetaError(
                f"RDFMeta: class_name {self.class_name!r} cannot be part of a URI: "
                "use letters, digits, '_' and '-', not starting with a digit"
            )
        if self.class_uri is not None and not _ABSOLUTE.fullmatch(self.class_uri):
            raise PanglossMetaError(
                f"RDFMeta: class_uri {self.class_uri!r} is not an absolute URI"
            )
        if self.dump not in (None, "all", "used"):
            raise PanglossMetaError(
                f"RDFMeta: dump {self.dump!r} is not 'all' or 'used'"
            )


register_meta_slot(SLOT, RDFMeta)


def declared_class(model: type) -> type:
    """The class as declared: `InRole` for `InRole[Agent]`, which has no name of its own in RDF"""
    metadata = getattr(model, "__pydantic_generic_metadata__", None)
    origin = metadata["origin"] if metadata else None
    return declared_class(origin) if origin is not None else model


def own_rdf_meta(model: type) -> RDFMeta | None:
    """The `RDFMeta` the class says itself (not one it inherits)"""
    model = declared_class(model)
    return getattr(model, SLOT, None) if SLOT in declared_slots(model) else None


def is_excluded(model: type) -> bool:
    meta = getattr(declared_class(model), SLOT, None)
    return isinstance(meta, RDFMeta) and meta.exclude


def dumps_only_used(model: type) -> bool:
    """Whether a dump leaves out the items of this class that nothing refers to: what the project says in `RDFMeta`,
    or else what the class says of itself"""
    model = declared_class(model)
    meta = getattr(model, SLOT, None)
    if isinstance(meta, RDFMeta) and meta.dump is not None:
        return meta.dump == "used"
    return included_only_when_referenced(model)
