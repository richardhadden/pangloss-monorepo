"""Companion documents: a document offered with a new entity, and written with it (implementation_docs/companion-documents.md).

An entity declares them in its `Meta` (`Entity.Meta(companions=[Companion(...)])`). When one of the entity is made, the
interface offers each companion that fits where it is made (`offered`); a companion that is filled in is written in
the same transaction as the entity, with the entity put in the field of each part that is for it (`entity_field`).

The declaration is not data: a change to it is not a migration. Its names are strings (the entity is usually declared
before the documents that refer to it) and are checked at `initialise()` (`check_companions`)."""

from dataclasses import dataclass
from typing import Any


def _tuple(value: Any) -> tuple:
    return (
        tuple(value) if isinstance(value, (list, tuple, set, frozenset)) else (value,)
    )


@dataclass(frozen=True, kw_only=True)
class CompanionPart:
    """A document the companion holds in its `field`, offered already added: `type` is its class, `entity_field` its
    relation that the new entity is put in"""

    type: str
    entity_field: str


@dataclass(frozen=True, kw_only=True)
class CopyFromOuter:
    """A field of the document the entity is made from (its head), copied into a field of the companion (`to`, by
    default the same name). A relation is copied as a value of its own, as a field binding copies"""

    field: str
    to: str | None = None

    @property
    def target(self) -> str:
        return self.to or self.field


@dataclass(frozen=True, kw_only=True)
class Within:
    """Offered when the entity is made from the form of a document: one whose head is of one of `heads` (with the types
    below them; none: any), from one of `fields` (`"Statement.involves"`, with the fields that stand for it; none: any),
    of a document of one of `holders` (with the types below; none: any)"""

    heads: tuple[str, ...] = ()
    fields: tuple[str, ...] = ()
    holders: tuple[str, ...] = ()

    def __post_init__(self):
        for name in ("heads", "fields", "holders"):
            object.__setattr__(self, name, _tuple(getattr(self, name)))


@dataclass(frozen=True)
class Standalone:
    """Offered when the entity is made on its own (its own page; a dialog with no document behind it)"""


@dataclass(frozen=True, kw_only=True)
class Companion:
    """A document offered with a new entity of the class that declares it.

    `document` is its class (a document that can be made on its own). With `field`, a list relation of it, the
    companion holds `parts`, each a document with a relation for the entity; without, the companion is itself the
    one part, and `entity_field` is its relation for the entity. `copies` are taken from the document the entity is
    made from. `offered` says where it is offered (any of them; none: everywhere)"""

    name: str
    document: str
    field: str | None = None
    parts: tuple[CompanionPart, ...] = ()
    entity_field: str | None = None
    copies: tuple[CopyFromOuter, ...] = ()
    offered: tuple[Within | Standalone, ...] = ()

    def __post_init__(self):
        for name in ("parts", "copies", "offered"):
            object.__setattr__(self, name, _tuple(getattr(self, name)))

    @property
    def slots(self) -> tuple[tuple[str | None, str], ...]:
        """Where the entity goes: (the type of each part, or `None` for the companion itself; the field)"""
        if self.field is None:
            return ((None, self.entity_field or ""),)
        return tuple((part.type, part.entity_field) for part in self.parts)


def companions_of(model: type) -> tuple[Companion, ...]:
    """The companions an entity class has (its own, or those it inherits)"""
    return tuple(getattr(getattr(model, "_meta", None), "companions", None) or ())


def companion_named(model: type, name: str) -> Companion | None:
    return next((c for c in companions_of(model) if c.name == name), None)
