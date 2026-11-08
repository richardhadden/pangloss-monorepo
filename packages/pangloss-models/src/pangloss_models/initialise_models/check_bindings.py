"""The names a `FieldBinding` gives, against the models: one that is misspelt does not fail, it never applies."""

from pangloss_models.diagnostics import reported
from pangloss_models.exceptions import AtString, PanglossModelError, did_you_mean
from pangloss_models.field_definitions import FieldBinding
from pangloss_models.model_bases.binding import NOT_MODELS


def check_binding(model: type, field_name: str, binding: FieldBinding) -> None:
    from pangloss_models.model_registry import ModelRegistry

    where = f"{model.__name__}.{field_name}: FieldBinding"
    models = ModelRegistry.all_models()

    # (`label` and `id` are on every document and entity, and not among the fields)
    own = [*model._meta.fields, "label", "id"]  # type: ignore[attr-defined]
    if binding.bound_field not in own:
        raise PanglossModelError(
            f"{where}(bound_field={binding.bound_field!r}): {model.__name__} has no field of that name."
            + did_you_mean(binding.bound_field, own),
            at_string=AtString("bound_field", binding.bound_field, tuple(own)),
        )

    # (any field of any model: which classes a child field is on depends on what the field holds)
    every_field = {
        name
        for other in models.values()
        for name in getattr(getattr(other, "_meta", None), "fields", ())
    }
    for name in binding.child_fields:
        if name not in every_field:
            raise PanglossModelError(
                f"{where}(child_fields=[... {name!r} ...]): no model has a field of that name."
                + did_you_mean(name, every_field),
                at_string=AtString("child_fields", name, tuple(sorted(every_field))),
            )

    # (a binding applies to a class by its own name and those of the classes above it)
    every_name = set(models) | {
        parent.__name__
        for other in models.values()
        for parent in other.__mro__
        if not parent.__module__.startswith(NOT_MODELS)
    }
    for option, names in (
        ("allowed_type_names", binding.allowed_type_names),
        ("excluded_type_names", binding.excluded_type_names),
    ):
        for name in names:
            if name not in every_name:
                raise PanglossModelError(
                    f"{where}({option}=[... {name!r} ...]): there is no model of that name."
                    + did_you_mean(name, every_name),
                    at_string=AtString(option, name, tuple(sorted(every_name))),
                )


def check_bindings(models: list[type]) -> None:
    """Raise `PanglossModelError` for a binding that names a field or a model that does not exist"""
    for model in models:
        relation_fields = getattr(
            getattr(getattr(model, "_meta", None), "fields", None),
            "relation_fields",
            None,
        )
        for field_name, definition in (relation_fields or {}).items():
            if definition.field_on_model is not model:
                continue
            for binding in definition.bind_to_child_field:
                with reported(model, field_name):
                    check_binding(model, field_name, binding)
