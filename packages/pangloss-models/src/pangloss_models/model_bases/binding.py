"""Field bindings: a value of a model given to the fields of what it holds (`FieldBinding`).

`bind_values_to_children` is what `_CreateBase` and `_UpdateBase` do once they are made."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pangloss_models.field_definitions import FieldBinding
    from pangloss_models.model_bases.base_models import _CreateBase, _UpdateBase


def allow_bind_on_this_item(
    item: _CreateBase | _UpdateBase, binding: FieldBinding
) -> bool:
    """Whether a binding applies to an item of this type: it must be one of `allowed_type_names`
    (if there are any) and none of `excluded_type_names`"""
    if binding.allowed_type_names and item.type not in binding.allowed_type_names:
        return False
    return item.type not in binding.excluded_type_names


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
            if hasattr(item, child_bound_field) and not getattr(
                item, child_bound_field, None
            ):
                setattr(item, child_bound_field, value)

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
