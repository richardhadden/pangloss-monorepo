"""A document that cites a document: `Cites[T]` (implementation_docs/entity-identity.md, part 3).

A relation to a document is containment: the document is written with the one that holds it, and belongs to it. A
**citation** is the other way of naming a document: by its id, without containing it, as an entity is referred to.

```python
class SameAs(Document):
    evidence: list[Cites[Statement]] = []        # payload: [{"type": "Activity", "id": "…"}]
```

Each citation is a small node of the citing document, a `PGCitation`, with the id of what it cites: nothing points
into the cited document, which is written again whole on every save. What may be cited is any document node of a
class `T` allows, a head document or a part of one.

Two things are built on it (implementation_docs/derived-edges-and-documents.md, part 3), neither of which the core
knows the use of:

- **a citation that does not protect** (a subclass of `Cites` with `protect = False`): read and shown as a citation
  is, but what it cites may be changed and deleted freely, and is never marked changed. Its node is of a class of its
  own, `PGUnprotectedCitation`, so that the work done for what is cited (who cites this, before every save of it)
  does not see it;
- **a cited basis** (`PGCitedBasis`): one item of a `Cites` field that stands for something that cannot itself be
  cited, and holds citations of what that rests on (`basis`) with a record of what was chosen (`via_*`). An installed
  app makes one of a citation (`hooks.resolve_citation`). There is such a class only if an app has asked for it
  (`enable_cited_basis`).

What the database does with them (the check that the target is there, the record of what was cited, the protection
of what is cited) is in the storage package (`pangloss_cypher.citations`).
"""

import contextlib
import contextvars
from collections.abc import Generator
from typing import Any, ClassVar, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, model_validator

from pangloss_models.exceptions import PanglossModelError

CITATION = "PGCitation"
UNPROTECTED = "PGUnprotectedCitation"
BASIS = "PGCitedBasis"
# (the classes of a node that names a document by its id)
CITATION_TYPES = (CITATION, UNPROTECTED)

# The marks of a cited basis (`derivation_state`): what it was made of has changed since, or is not there any more
BASIS_CHANGED = "changed"
BASIS_LOST = "lost"

# What a write sets on a citation, whatever was sent for it
WRITTEN_BY_SERVER = ("target_head_id", "cited_version", "cited_hash", "cited_label")

# What a read works out about what is cited, as it is now: never stored
WORKED_OUT = (
    "target_label",
    "target_head_type",
    "target_head_label",
    "target_spaces",
    "target_state",
)


def citation_class() -> type:
    """The class of a citation node: declared the first time a `Cites[...]` is written (so a project without
    citations has no such model), and again after the registry is reset"""
    from pangloss_models.model_registry import ModelRegistry

    existing = ModelRegistry._model_dict.get(CITATION)
    if existing is not None:
        return existing
    declared = _declare_citation()
    if _basis_enabled:
        basis_class()
    return declared


def _declare_citation() -> type:
    from pangloss_models.model_bases.document import Document

    class PGCitation(Document):
        """A citation of a document (`Cites[T]`): which document node, and what is recorded of it"""

        target_id: UUID
        """The id of the document node that is cited"""
        target_type: str
        """Its class"""
        changed_since_cited: bool = False
        """Set when what is cited was changed, by a write that acknowledged the citation. It stays until the citing
        document is saved with it false: that is how a person says they have looked"""

        # (set by the write: sent values are not kept)
        target_head_id: UUID | None = None
        """The head document the cited node is in (itself, if it is a head)"""
        cited_version: int | None = None
        """The version of that head when the citation was written"""
        cited_hash: str | None = None
        """A hash of what was cited, in a normal form (`pangloss_cypher.citations.content_hash`)"""

        cited_label: str | None = None
        """What it was called then"""

        # (worked out by a read, from what is cited as it is now: never stored)
        target_label: str | None = None
        target_head_type: str | None = None
        target_head_label: str | None = None
        target_spaces: list[str] = []
        target_state: str = "there"
        """`there`; `removed` (nothing has the id any more, or it was deleted); `hidden` (it is in a document the
        reader may not see: nothing else of it is given)"""

        _meta = Document.Meta(
            require_label=False,
            create_directly=False,
            global_search=False,
            indexes=["target_id", "target_head_id"],
        )

        @model_validator(mode="before")
        @classmethod
        def from_reference(cls, data: Any) -> Any:
            """`{"type": "Activity", "id": "…"}`, as a reference to an entity is written: a citation of it"""
            if not isinstance(data, dict):
                return data
            if data.get("type") in (None, CITATION) or "target_id" in data:
                return data
            if "id" not in data:
                return data
            return {
                "type": CITATION,
                "target_id": data["id"],
                "target_type": data["type"],
            }

    return PGCitation


def unprotected_citation_class() -> type:
    """The class of a citation that does not protect what it cites: declared the first time such a field is
    written. It records less than a citation (nothing is compared with it later): the head, the class and the label
    of what it cites"""
    from pangloss_models.model_bases.document import Document
    from pangloss_models.model_registry import ModelRegistry

    existing = ModelRegistry._model_dict.get(UNPROTECTED)
    if existing is not None:
        return existing

    class PGUnprotectedCitation(Document):
        """A citation that does not protect what it cites (a `Cites` with `protect = False`)"""

        target_id: UUID
        target_type: str

        # (set by the write: sent values are not kept)
        target_head_id: UUID | None = None
        cited_label: str | None = None

        # (worked out by a read, from what is cited as it is now: never stored)
        target_label: str | None = None
        target_head_type: str | None = None
        target_head_label: str | None = None
        target_spaces: list[str] = []
        target_state: str = "there"

        _meta = Document.Meta(
            require_label=False,
            create_directly=False,
            global_search=False,
            indexes=["target_id", "target_head_id"],
        )

        @model_validator(mode="before")
        @classmethod
        def from_reference(cls, data: Any) -> Any:
            if not isinstance(data, dict):
                return data
            if data.get("type") in (None, UNPROTECTED) or "target_id" in data:
                return data
            if "id" not in data:
                return data
            return {
                "type": UNPROTECTED,
                "target_id": data["id"],
                "target_type": data["type"],
            }

    return PGUnprotectedCitation


_basis_enabled = False


def enable_cited_basis() -> None:
    """(An installed app, when it is imported: one that resolves citations, `hooks.resolve_citation`) every `Cites`
    field also takes a `PGCitedBasis`. Without this there is no such class, and the models of a project that has
    citations are as they were"""
    global _basis_enabled
    from pangloss_models.model_registry import ModelRegistry

    _basis_enabled = True
    if CITATION in ModelRegistry._model_dict:
        basis_class()


def basis_class() -> type:
    """The class of a cited basis, declared with the class of a citation once an app has asked for it"""
    from pangloss_models.model_bases.document import Document
    from pangloss_models.model_registry import ModelRegistry

    existing = ModelRegistry._model_dict.get(BASIS)
    if existing is not None:
        return existing
    citation = ModelRegistry._model_dict.get(CITATION) or _declare_citation()

    class PGCitedBasis(Document):
        """What stands in a `Cites` field for something chosen that cannot itself be cited: citations of what it
        rests on, and a record of what was chosen"""

        via_id: UUID
        """The id of what was chosen"""
        via_type: str
        """Its class"""
        via_rule: str | None = None
        """What made it of its basis (the name of a rule)"""
        via_key: str | None = None
        """What that app knows it by (the key of a justification)"""
        via_label: str | None = None
        """What it was called when it was cited"""
        derivation_state: str = ""
        """Set when what was chosen has changed since (`changed`) or is not there any more (`lost`); cleared when it
        is back. It stays until the citing document is saved with it empty, or without the item"""
        basis: list[citation]  # ty: ignore[invalid-type-form]
        """The citations of what it rests on: citations as any other, which protect what they cite"""

        # (worked out by a read: never stored)
        via_state: str = "there"
        """Of what was chosen, as it is now: `there`, `removed` or `hidden`"""
        via_label_now: str | None = None

        _meta = Document.Meta(
            require_label=False,
            create_directly=False,
            global_search=False,
            indexes=["via_id"],
        )

    return PGCitedBasis


class Cites[Target](BaseModel):
    """`evidence: list[Cites[Statement]]`: a relation that cites documents of the class (or any of a union) by id,
    without containing them.

    A subclass with `protect = False` is a citation that does not protect what it cites
    (`class DerivedFrom[Target](Cites[Target]): protect = False`)"""

    protect: ClassVar[bool] = True

    def __class_getitem__(cls, item: Any) -> Any:  # ty: ignore[invalid-method-override]
        # (the class of the node is a model as any other, and has to be declared before the models are initialised)
        # (but not when a subclass is declared, `class DerivedFrom[Target](Cites[Target])`: nothing is cited yet)
        if not isinstance(item, TypeVar):
            if cls.protect:
                citation_class()
            else:
                unprotected_citation_class()
        return super().__class_getitem__(item)


def cites_origin(annotation: Any) -> type | None:
    """The `Cites` class (or subclass) an annotation is a use of: `Cites[Statement]`"""
    metadata = getattr(annotation, "__pydantic_generic_metadata__", None)
    origin = metadata["origin"] if metadata else None
    if isinstance(origin, type) and issubclass(origin, Cites):
        return origin
    return None


def is_cites(annotation: Any) -> bool:
    return cites_origin(annotation) is not None


def protects(annotation: Any) -> bool:
    """Whether a `Cites[...]` annotation is of a citation that protects what it cites"""
    origin = cites_origin(annotation)
    return bool(origin is None or getattr(origin, "protect", True))


def cited_types(annotation: Any) -> frozenset[type]:
    """The document classes a `Cites[...]` allows (those written: their subclasses are allowed too)"""
    from types import UnionType
    from typing import Union, get_args, get_origin

    from pangloss_models.model_bases.document import Document
    from pangloss_models.model_bases.reified_relation import ReifiedRelationDocument

    (argument,) = annotation.__pydantic_generic_metadata__["args"]
    members = (
        get_args(argument)
        if get_origin(argument) in (UnionType, Union)
        else (argument,)
    )
    for member in members:
        origin = getattr(member, "__pydantic_generic_metadata__", {}).get("origin")
        if not (
            isinstance(member, type)
            and issubclass(origin or member, (Document, ReifiedRelationDocument))
        ):
            raise PanglossModelError(
                f"Cites[{getattr(member, '__name__', member)}]: only a document can be cited (a Document class, or "
                "a union of them). An entity is referred to as it is, without `Cites`"
            )
    return frozenset(members)


def type_name_of(value: Any) -> str | None:
    """The class of a generated model's instance, or of a node read from the database"""
    if isinstance(value, dict):
        return value.get("type")
    return getattr(getattr(type(value), "_owner", None), "__name__", None)


def is_citation(value: Any) -> bool:
    """Whether a generated model's instance, or a node read from the database, is a citation (one that protects, or
    one that does not)"""
    return type_name_of(value) in CITATION_TYPES


def is_protecting(value: Any) -> bool:
    return type_name_of(value) == CITATION


def is_basis(value: Any) -> bool:
    return type_name_of(value) == BASIS


def allows(cited: frozenset[type], type_name: str) -> bool:
    """Whether a node of the class named may be cited where `cited` are allowed"""
    from pangloss_models.model_registry import ModelRegistry

    made_as = ModelRegistry._model_dict.get(type_name)
    if made_as is None:
        # (a generic's nodes are of its base: `SameEntity[Person]` is stored as `SameEntity`)
        return any(
            getattr(
                getattr(c, "__pydantic_generic_metadata__", {}).get("origin"),
                "__name__",
                None,
            )
            == type_name
            for c in cited
        )
    return any(
        made_as is c
        or issubclass(made_as, c)
        or getattr(c, "__pydantic_generic_metadata__", {}).get("origin") is made_as
        for c in cited
    )


# What a write says of the citations of what it changes: nothing (a change to something cited is refused);
# `changes` (the writer has been told: the write goes ahead, and each citation is marked changed);
# `removals` (an admin's override: what is cited may be removed as well, and the citations are left pointing at
# nothing, shown as removed). `save(acknowledge_citations=...)`, `?acknowledge_citations=` of the API
type Acknowledgement = Literal["changes", "removals"] | None

acknowledged: contextvars.ContextVar[Acknowledgement] = contextvars.ContextVar(
    "acknowledged_citations", default=None
)


@contextlib.contextmanager
def acknowledging(what: Acknowledgement | bool) -> Generator[None]:
    """The writes made inside the block acknowledge the citations of what they change"""
    if not what:
        yield
        return
    token = acknowledged.set("changes" if what is True else what)
    try:
        yield
    finally:
        acknowledged.reset(token)
