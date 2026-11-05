"""Field bindings: a value of a model given to the fields of what it holds (`FieldBinding`).

`bind_values_to_children` is what `_CreateBase` and `_UpdateBase` do once they are made."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pangloss_models.field_definitions import FieldBinding, FieldDefinition
    from pangloss_models.model_bases.base_models import _CreateBase, _UpdateBase


# (where the classes above a model that are not models of a project come from: this library's bases and kit, pydantic's)
NOT_MODELS = ("pangloss_models.", "pydantic", "builtins", "typing")


def class_names(model: type | None, type_name: str) -> set[str]:
    """The names a binding's types are matched against: those of the class and of every class above it (its parents
    and traits), so that a binding to `CreationOfPhysicalObject` applies to a `CreationOfPainting` too. Not the
    library's bases (`Document`): the interface's binder has the same names, from the export's `parent` and `traits`.
    Without the class, only `type_name`"""
    if model is None:
        return {type_name}
    return {type_name} | {
        cls.__name__
        for cls in model.__mro__
        if not cls.__module__.startswith(NOT_MODELS)
    }


def binding_applies(binding: FieldBinding, names: set[str]) -> bool:
    """Whether a binding applies to a class with these `names` (`class_names`): it must be, or be below, one of
    `allowed_type_names` (if there are any), and be, or be below, none of `excluded_type_names`. (Being below one
    excluded excludes it, even if it is also below one allowed)"""
    if binding.allowed_type_names and names.isdisjoint(binding.allowed_type_names):
        return False
    return names.isdisjoint(binding.excluded_type_names)


def allow_bind_on_this_item(
    item: _CreateBase | _UpdateBase, binding: FieldBinding
) -> bool:
    """Whether a binding applies to an item: by its class and the classes above it (`binding_applies`)"""
    return binding_applies(
        binding, class_names(getattr(type(item), "_owner", None), item.type)
    )


def names_stood_for(definition: FieldDefinition) -> set[str]:
    """The names of the fields of classes above that a relation field stands for (`subclasses_parent_fields`, which
    initialisation makes transitive: `painting_created` stands for `artwork_created` and `object_created`)"""
    return {
        getattr(subclassed, "field_name", subclassed)
        for subclassed in getattr(definition, "subclasses_parent_fields", ())
    }


def bound_names(name: str, definition: FieldDefinition) -> set[str]:
    """The names a binding's `child_fields` reach a field by: its own, and those of the fields it stands for"""
    return {name} | names_stood_for(definition)


def fields_bound(item, child_field: str) -> list[str]:
    """The fields of `item` that a binding into `child_field` gives a value to: the field of that name, or (in a class
    that narrows it) the field that stands for it, so a binding into `object_created` gives `painting_created` of a
    `CreationOfPainting`"""
    fields = item._meta.fields
    return [
        name
        for name in type(item).model_fields
        if name in fields and child_field in bound_names(name, fields[name])
    ]


def give(item, field: str, value) -> None:
    """Sets the bound `value` on a field of `item`, validated as that field's own type: a relation (a reference, a
    reified relation) is made again from what it holds, so the child has an object of its own, of the class its
    field has (the parent's is another class, for another field), and each is written as a node of its own"""
    from pydantic import BaseModel

    def plain(v):
        if isinstance(v, BaseModel):
            return v.model_dump()
        if isinstance(v, list | tuple):
            return [plain(each) for each in v]
        return v

    type(item).__pydantic_validator__.validate_assignment(item, field, plain(value))


def recursively_add_bound_field_values(item, binding: FieldBinding, value=None) -> None:
    """Given an item, a FieldBinding instance and a value, try to bind values where rules are
    followed, and call itself to try on all nested items.

    Only what is being written (a `Create` or an `Update`) is given values and looked into: a
    reference to something that exists (`PersonReferenceSet`) has only its id and type."""
    from pangloss_models.model_bases.base_models import _CreateBase, _UpdateBase

    # (the value of a relation to a list of things is a list)
    if isinstance(item, list | tuple):
        for list_item in item:
            recursively_add_bound_field_values(list_item, binding, value)
        return

    if not isinstance(item, _CreateBase | _UpdateBase):
        return

    if allow_bind_on_this_item(item, binding):
        for child_bound_field in binding.child_fields:
            # (a value the field cannot hold, an artwork bound to the painting created, is refused by its validation)
            for field_name in fields_bound(item, child_bound_field):
                if not getattr(item, field_name, None):
                    give(item, field_name, value)

    for related_field_name in item._meta.fields.relation_fields:
        recursively_add_bound_field_values(
            getattr(item, related_field_name), binding, value
        )


def bind_values_to_children(item: _CreateBase | _UpdateBase) -> None:
    """Get any binding-fields for this model and try to bind on nested objects"""
    for field_name, bindings in item._meta.fields.bind_to_child_field_bindings.items():
        for binding in bindings:
            value = getattr(item, binding.bound_field)
            if binding.converter:
                value = binding.converter(value)
            recursively_add_bound_field_values(
                getattr(item, field_name), binding, value=value
            )
