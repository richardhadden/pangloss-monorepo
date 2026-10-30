"""Check that what a relation points to can be pointed to.

A relation to an abstract class means "any of its subclasses". With no subclass there is nothing it can point
to, and the generated models would have an empty union. That is reported here, at the field, instead.
"""

from collections.abc import Iterator
from inspect import isclass
from types import UnionType
from typing import Annotated, Any, Union, get_args, get_origin

from pangloss_models.exceptions import PanglossModelError
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.trait import NonHeritableTrait, Trait
from pangloss_models.utils import generic_get_subclasses, get_concrete_types


def targets_of(annotation: Any) -> Iterator[type]:
    """The Documents, Entities and Traits an annotation of a relation field can point to, through
    unions, lists, annotations, and the type arguments of generics (`Negative[...]`, `ViaEdge[..., ...]`)"""
    origin = get_origin(annotation)
    if origin is Annotated:
        yield from targets_of(get_args(annotation)[0])
    elif origin is Union or origin is UnionType or origin in (list, tuple, set):
        for argument in get_args(annotation):
            yield from targets_of(argument)
    elif isclass(annotation):
        if issubclass(annotation, (Document, Entity, Trait, NonHeritableTrait)):
            yield annotation
        for argument in getattr(annotation, "__pydantic_generic_metadata__", {}).get(
            "args", ()
        ):
            yield from targets_of(argument)


def describe_missing(target: type) -> str:
    if issubclass(target, (Trait, NonHeritableTrait)):
        return f"{target.__name__} is a trait that no Entity or Document has"
    subclasses = sorted(c.__name__ for c in generic_get_subclasses(target, True))
    if not target._meta.abstract:  # type: ignore[attr-defined]
        return f"{target.__name__} has no concrete type"
    if subclasses:
        return (
            f"{target.__name__} is abstract and all of its subclasses are abstract "
            f"({', '.join(subclasses)})"
        )
    return f"{target.__name__} is abstract and has no subclass"


def check_relation_targets(models: Iterator[type] | list[type]) -> None:
    """Raise `PanglossModelError` for every relation field that points to something with no concrete type"""
    problems: list[str] = []
    for model in models:
        fields = getattr(getattr(model, "_meta", None), "fields", None)
        relation_fields = getattr(fields, "relation_fields", None)
        if not relation_fields:
            continue
        for name, definition in relation_fields.items():
            if definition.field_on_model is not model:
                continue
            for target in targets_of(definition.annotated_type):
                if not get_concrete_types(target):
                    problems.append(
                        f"  {model.__name__}.{name} points to {target.__name__}: "
                        f"{describe_missing(target)}"
                    )
    if problems:
        raise PanglossModelError(
            "A relation points to a class that nothing can be created from:\n"
            + "\n".join(dict.fromkeys(problems))
            + "\nDeclare a concrete subclass (or a Document or Entity that has the trait), "
            "or point the relation at something else."
        )
