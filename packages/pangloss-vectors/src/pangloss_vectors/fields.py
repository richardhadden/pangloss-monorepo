"""The classes a search is narrowed to, by name (step 7a.4 of implementation_docs/similarity-build-plan.md): those a
class of documents or entities stands for (it and the classes below it that are not abstract:
`pangloss_models.utils.get_concrete_types`), and those a field of a model can hold.

    classes_of("Agent")                         ["Group", "Person"]   (a trait: the classes that have it)
    field_types("Activity.carried_out_by")      ["Group", "Person"]

A field's classes are the entity classes its relation reaches, as the reverse fields of an entity's `HeadView` are
worked out (`initialise_incoming_relation_definitions.entities_reached`): through generic wrappers (`InRole[Agent]`,
a wrapper in a wrapper), and not the documents that may be given in place of an entity (the stand-ins: review's
`Unreconciled`). Nothing here reads a database: `search.nearest(types=...)` is given what these say.
"""

from inspect import isclass
from typing import Any

from pangloss_models import (
    Document,
    Entity,
    ModelRegistry,
    NonHeritableTrait,
    Trait,
)


class NotAClass(ValueError):
    """A name that is no class of documents or entities (nor a trait that such classes have)"""


class NotAField(ValueError):
    """`Model.field` that is no model's, no field of it, or not a relation that reaches an entity"""


def concrete_classes(model: type) -> list[str]:
    """The names of the classes of documents and entities of `get_concrete_types(model)` that are not abstract"""
    from pangloss_models.utils import get_concrete_types

    return sorted(
        found.__name__
        for found in get_concrete_types(model)
        if issubclass(found, (Document, Entity)) and not found._meta.abstract
    )


def classes_of(type_name: str) -> list[str]:
    """The names of the classes of items a class stands for, in order: it (unless it is abstract) and each class below
    it that is not; of a trait, the classes that have it and those below them. `NotAClass` for any other name"""
    model = ModelRegistry._model_dict.get(type_name)
    if not (
        isclass(model)
        and issubclass(model, (Document, Entity, Trait, NonHeritableTrait))
    ):
        raise NotAClass(
            f"{type_name!r} is not a class of documents or entities: a search is narrowed to those"
        )
    return concrete_classes(model)


def _field_named(model: Any, name: str) -> Any:
    """The field of the model of this name, in Python's spelling or in JSON's (`carriedOutBy`)"""
    from pydantic.alias_generators import to_camel

    fields = model._meta.fields
    if name in fields:
        return fields[name]
    return next(
        (definition for key, definition in fields.items() if to_camel(key) == name),
        None,
    )


def relation_field(spec: str) -> Any:
    """The definition of the relation `Model.field` (`NotAField` if it is no model's, no field of it, or not a
    relation)"""
    from pangloss_models.field_definitions import RelationFieldDefinition

    model_name, dot, field_name = spec.partition(".")
    if not dot or not model_name or not field_name:
        raise NotAField(
            f"{spec!r} is not a field: a field is named as Model.field (Activity.carried_out_by)"
        )
    model = ModelRegistry._model_dict.get(model_name)
    if model is None or not hasattr(model, "_meta"):
        raise NotAField(f"{spec!r}: there is no model {model_name!r}")
    definition = _field_named(model, field_name)
    if definition is None:
        raise NotAField(f"{spec!r}: {model_name} has no field {field_name!r}")
    if not isinstance(definition, RelationFieldDefinition):
        raise NotAField(
            f"{spec!r} is not a relation: only a relation's entities can be searched for"
        )
    return definition


def field_types(spec: str) -> list[str]:
    """The names of the entity classes the field `Model.field` can hold, in order (`NotAField` if it is not a relation
    of a model that reaches one)"""
    from pangloss_models.initialise_models.initialise_incoming_relation_definitions import (
        entities_reached,
    )

    definition = relation_field(spec)
    names = sorted(
        {
            name
            for reached, _through_wrapper in entities_reached(definition)
            for name in concrete_classes(reached)
        }
    )
    if not names:
        raise NotAField(
            f"{spec!r} reaches no class of entities: a search by a field is for the entities it can hold"
        )
    return names
