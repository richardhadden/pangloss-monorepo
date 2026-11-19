"""Which classes of head a description can be inside: a write of one of them leaves work for the worker
(`hooks.pending_work`, kind `criteria`)."""

from typing import Any

from pangloss_models import ModelRegistry
from pangloss_models.field_definitions import (
    RelationToCitation,
    RelationToDocument,
)

from pangloss_criteria.models import NAME

KIND = "criteria"

_holds: dict[type, bool] = {}


def forget() -> None:
    """(`ModelRegistry.on_reset`) the models have changed"""
    _holds.clear()


def description_classes() -> list[type]:
    """`MatchesCriteria`, and the classes declared below it"""
    models = ModelRegistry.all_models()
    base = models.get(NAME)
    if not isinstance(base, type):
        return []
    return [
        model
        for model in models.values()
        if isinstance(model, type)
        and issubclass(model, base)
        and not getattr(model, "__pydantic_generic_metadata__", {}).get("origin")
    ]


def description_labels() -> list[str]:
    """The labels a node that is a description has one of"""
    return sorted(model.__name__ for model in description_classes())


def can_hold(model: type) -> bool:
    """Whether a head of the class can have a description somewhere in it: in a relation of its own, of a document
    nested in it, or of a wrapper or an embedded object on the way"""
    if model in _holds:
        return _holds[model]
    descriptions = tuple(description_classes())
    seen: set[type] = set()

    def in_options(options: Any) -> bool:
        for option in options:
            base = getattr(option, "base_type", None)
            if (
                isinstance(base, type)
                and descriptions
                and issubclass(base, descriptions)
            ):
                return True
            # (a citation names a document that is not part of this one)
            if isinstance(option, RelationToDocument) and not isinstance(
                option, RelationToCitation
            ):
                if in_class(option.annotated_type):
                    return True
            if base is not None and in_class(base):
                return True
            for parameter in getattr(option, "parameter_type_options", {}).values():
                if in_options(parameter.type_options):
                    return True
        return False

    def in_class(cls: Any) -> bool:
        if not isinstance(cls, type) or cls in seen:
            return False
        seen.add(cls)
        fields = getattr(getattr(cls, "_meta", None), "fields", None)
        if fields is None:
            return False
        for definition in fields.relation_fields.values():
            if in_options(definition.type_options):
                return True
        for definition in fields.embedded_fields.values():
            for option in definition.type_options:
                if in_class(option.annotated_type):
                    return True
        return False

    found = _holds[model] = bool(descriptions) and in_class(model)
    return found


def pending_work_of(model: type) -> list[str]:
    """(`hooks.pending_work`) a write of a head that can hold a description leaves it to be evaluated"""
    return [KIND] if can_hold(model) else []
