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

What the database does with them (the check that the target is there, the record of what was cited, the protection
of what is cited) is in the storage package (`pangloss_cypher.citations`).
"""

import contextlib
import contextvars
from collections.abc import Generator
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, model_validator

from pangloss_models.exceptions import PanglossModelError

CITATION = "PGCitation"

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
    from pangloss_models.model_bases.document import Document
    from pangloss_models.model_registry import ModelRegistry

    existing = ModelRegistry._model_dict.get(CITATION)
    if existing is not None:
        return existing

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


class Cites[Target](BaseModel):
    """`evidence: list[Cites[Statement]]`: a relation that cites documents of the class (or any of a union) by id,
    without containing them"""

    def __class_getitem__(cls, item: Any) -> Any:  # ty: ignore[invalid-method-override]
        # (the class of the node is a model as any other, and has to be declared before the models are initialised)
        citation_class()
        return super().__class_getitem__(item)


def is_cites(annotation: Any) -> bool:
    metadata = getattr(annotation, "__pydantic_generic_metadata__", None)
    return bool(metadata and metadata["origin"] is Cites)


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


def is_citation(value: Any) -> bool:
    """Whether a generated model's instance, or a node read from the database, is a citation"""
    if isinstance(value, dict):
        return value.get("type") == CITATION
    return getattr(getattr(type(value), "_owner", None), "__name__", None) == CITATION


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
