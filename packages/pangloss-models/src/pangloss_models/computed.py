"""What the server computes (`Computed()`, `pangloss_models.markers`): which fields of which models, for a backend
that writes them (`set_computed` of its operations) and leaves them out of what counts as a reference.

A computed field is read with its model and written by nobody: `Create` and `Update` do not have it. A value is
given to it by `set_computed` alone, which makes no new version of the document it is in
(implementation_docs/matches-criteria.md, "`Computed()`").
"""

import dataclasses
from typing import Any
from uuid import UUID

from pangloss_models.field_definitions import (
    ListFieldDefinition,
    LiteralFieldDefinition,
    RelationFieldDefinition,
)
from pangloss_models.markers import is_computed

# The property of an edge of a computed relation that says who may see it (a backend marks the edges themselves as
# computed in its own way)
SEEN_BY = "seen_by"
EVERYONE = "everyone"
LOGGED_IN = "logged_in"


@dataclasses.dataclass(frozen=True)
class ComputedTarget:
    """What a computed relation is given: the entity, and who may see that it is there (`seen_by`: `everyone`, or
    `logged_in` for what rests on something not published; none said is everyone)"""

    id: UUID | str
    seen_by: str | None = None


@dataclasses.dataclass(frozen=True)
class ComputedWrite:
    """One call of `set_computed`, for the form that makes several in one transaction: the node, its computed
    fields by name (a relation: a list of ids or `ComputedTarget`s; a value: the value, or None for none), and the
    version of its head that they were worked out from (None: whatever it is now)"""

    node_id: UUID | str
    values: dict[str, Any]
    based_on_version: int | None = None


@dataclasses.dataclass(frozen=True)
class ComputedFields:
    relations: dict[str, RelationFieldDefinition]
    values: dict[str, LiteralFieldDefinition | ListFieldDefinition]

    def __bool__(self) -> bool:
        return bool(self.relations or self.values)


_fields: dict[type, ComputedFields] = {}
_any: dict[str, bool] = {}


def clear() -> None:
    """Forget what was worked out (the models have changed: `ModelRegistry._reset`, or a class declared)"""
    _fields.clear()
    _any.clear()


def computed_fields(model: type) -> ComputedFields:
    """The computed fields of a declared model (of a generic wrapper, those of the wrapper itself)"""
    origin = getattr(model, "__pydantic_generic_metadata__", {}).get("origin")
    model = origin or model
    found = _fields.get(model)
    if found is None:
        fields = model._meta.fields  # ty: ignore[unresolved-attribute]
        found = _fields[model] = ComputedFields(
            relations={
                name: definition
                for name, definition in fields.relation_fields.items()
                if is_computed(definition)
            },
            values={
                name: definition
                for name, definition in fields.literal_fields.items()
                if is_computed(definition)
            },
        )
    return found


def _some(kind: str) -> bool:
    if kind not in _any:
        from pangloss_models.model_registry import ModelRegistry

        _any[kind] = any(
            is_computed(definition)
            for model in ModelRegistry._model_dict.values()
            if hasattr(getattr(model, "_meta", None), "field_definitions")
            for definition in (
                model._meta.fields.relation_fields
                if kind == "relations"
                else model._meta.fields
            ).values()
        )
    return _any[kind]


def has_computed_relations() -> bool:
    """Whether some declared model has a computed relation: only then is there an edge that is no reference, and a
    query that counts references has to tell"""
    return _some("relations")


def has_computed() -> bool:
    """Whether some declared model has a computed field of any kind: only then does a write have anything to keep"""
    return _some("fields")


def has_computed_fields(model: type) -> bool:
    return bool(computed_fields(model))
