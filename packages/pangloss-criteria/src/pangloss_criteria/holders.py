"""Which classes of head leave work for the worker when one is written (`hooks.pending_work`, kind `criteria`):
those a description can be inside, and those the criteria of some description could reach."""

from typing import Any

from pangloss_models import ModelRegistry
from pangloss_models.field_definitions import (
    RelationToCitation,
    RelationToDocument,
)

from pangloss_criteria.models import NAME

KIND = "criteria"

_holds: dict[type, bool] = {}
_reached: set[type] | None = None


def forget() -> None:
    """(`ModelRegistry.on_reset`) the models have changed"""
    global _reached
    _holds.clear()
    _reached = None


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


def reached() -> set[type]:
    """The classes of entities and documents that the criteria of some description could reach: a write of a head
    of one of them may change who a description finds.

    A pattern goes from the class it is of along relations in either direction (a field, or `$incoming`), through
    wrappers, embedded objects and nested documents, and a relation to a class holds its subclasses. So two classes
    are joined if one has a relation that can hold the other (directly, or inside a wrapper or an embedded object),
    or if one is declared below the other; and what is reached is everything joined, by any number of such steps,
    to a class that some `MatchesCriteria[T]` of the models stands for. It errs on the side of more: a class that
    is marked and that no stored pattern names costs a mark, and the worker chooses nothing for it."""
    global _reached
    if _reached is not None:
        return _reached
    models = ModelRegistry.all_models()
    descriptions = tuple(description_classes())
    declared = {
        model
        for model in models.values()
        if isinstance(model, type)
        and getattr(model, "__metatype__", None) in ("Entity", "Document")
    }
    roots: set[type] = set()

    def leaves(
        options: Any, found: set[type], seen: set[type], described: bool
    ) -> None:
        """The entities and documents the options can hold, through wrappers (with what the wrappers' own fields
        hold). `described`: inside a description, where what is held is what it stands for"""
        for option in options:
            base = getattr(option, "base_type", None)
            target = getattr(option, "annotated_type", None)
            if base is None and isinstance(target, type) and target in declared:
                found.add(target)
                if described:
                    roots.add(target)
            if isinstance(base, type):
                inside = described or (
                    bool(descriptions) and issubclass(base, descriptions)
                )
                for parameter in getattr(option, "parameter_type_options", {}).values():
                    leaves(parameter.type_options, found, seen, inside)
                held_by(base, found, seen)

    def held_by(cls: Any, found: set[type], seen: set[type]) -> None:
        """What the fields of a class can hold"""
        if not isinstance(cls, type) or cls in seen:
            return
        seen.add(cls)
        fields = getattr(getattr(cls, "_meta", None), "fields", None)
        if fields is None:
            return
        for definition in fields.relation_fields.values():
            leaves(definition.type_options, found, seen, False)
        for definition in fields.embedded_fields.values():
            for option in definition.type_options:
                held_by(option.annotated_type, found, seen)

    joined: dict[type, set[type]] = {model: set() for model in declared}
    for model in declared:
        found: set[type] = set()
        held_by(model, found, set())
        found.update(base for base in model.__mro__[1:] if base in declared)
        for other in found:
            joined[model].add(other)
            joined[other].add(model)
    result: set[type] = set()
    todo = list(roots)
    while todo:
        model = todo.pop()
        if model not in result:
            result.add(model)
            todo.extend(joined[model] - result)
    _reached = result
    return result


def pending_work_of(model: type) -> list[str]:
    """(`hooks.pending_work`) a write of a head that can hold a description leaves it to be evaluated, and so
    does a write of a head that the criteria of some description could reach"""
    return [KIND] if can_hold(model) or model in reached() else []
