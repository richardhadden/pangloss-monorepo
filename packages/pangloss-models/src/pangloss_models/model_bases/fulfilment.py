"""`Fulfils`: what an instance can be written as, as well as its own model.

A class that `Fulfils` another supplies what that class requires (its fields named in `field_required_to_fulfil`).
An instance is written as each class it holds everything for."""

from collections import defaultdict
from typing import TYPE_CHECKING, Literal, NamedTuple

from pydantic import ValidationError, create_model

from pangloss_models.model_bases.model_tools import set_field

if TYPE_CHECKING:
    from pangloss_models.model_bases.base_models import (
        _CreateDBBase,
        _DeclaredClass,
        _UpdateDBBase,
    )


class Fulfilment(NamedTuple):
    this_field_name: str
    class_to_fulfil: type[_DeclaredClass]
    field_on_class_to_fulfil: str


def get_fulfillable_models(self) -> dict[type[_DeclaredClass], list[Fulfilment]]:
    """The classes the model of `self` could fulfil, each with what supplies what it requires"""
    ffs: list[Fulfilment] = []
    for field_name, field_info in self._meta.fields.items():
        for field_fulfilment in field_info.field_required_to_fulfil:
            ffs.append(
                Fulfilment(
                    this_field_name=field_name,
                    class_to_fulfil=field_fulfilment.fulfils_class,
                    field_on_class_to_fulfil=field_fulfilment.field_name,
                )
            )

    model_fulfilments: dict[type[_DeclaredClass], list[Fulfilment]] = defaultdict(list)
    for ff in ffs:
        model_fulfilments[ff.class_to_fulfil].append(ff)
    return model_fulfilments


def get_fulfilled_classes(self, metafunction: Literal["Update", "Create"]):
    """The classes `self` holds everything for: those it can be made as, with its values"""
    model_fulfilments = get_fulfillable_models(self)

    models_fulfilled = []
    for model_to_fulfil_base, fulfilments in model_fulfilments.items():
        model_to_fulfil = getattr(model_to_fulfil_base, f"{metafunction}DB")
        data = self.model_dump()
        del data["type"]
        for fulfilment in fulfilments:
            data[fulfilment.field_on_class_to_fulfil] = getattr(self, fulfilment.this_field_name)
        try:
            model_to_fulfil(**data, type=model_to_fulfil_base.__name__)
            models_fulfilled.append(model_to_fulfil_base)
        except ValidationError:
            pass

    return models_fulfilled


def fulfilled_classes_of(self, metafunction: Literal["Update", "Create"]):
    """`get_fulfilled_classes`, worked out once for an instance (it builds models to find out, and is
    asked for by the labels and by the write; an instance that is written is not changed after)"""
    if self._fulfils_cache is None:
        self._fulfils_cache = get_fulfilled_classes(self, metafunction)
    return self._fulfils_cache


def build_fulfilled_model[T: _CreateDBBase | _UpdateDBBase](
    instance: T, fulfilled_classes: list[type[_DeclaredClass]]
) -> T:
    """The instance made again as a model of its own class and the classes it fulfils"""
    from pangloss_models.model_bases.base_models import _CreateDBBase

    metafunction = "Create" if isinstance(instance, _CreateDBBase) else "Update"

    base_models: list[type[_DeclaredClass]] = [instance._owner, *fulfilled_classes]
    names = [c.__name__ for c in base_models]
    base_db_models = [getattr(m, f"{metafunction}DB") for m in base_models]

    new_fulfilled_model = create_model(
        f"({','.join(names)}){metafunction}DB",
        __base__=tuple(base_db_models),
        __module__=instance.__class__.__module__,
    )

    fulfilled_fields = {}
    fulfilled_data = instance.model_dump()

    for fm, fulfilments in get_fulfillable_models(instance).items():
        if fm in fulfilled_classes:
            for f in fulfilments:
                fulfilled_fields[f.field_on_class_to_fulfil] = getattr(
                    fm, f"{metafunction}DB"
                ).model_fields[f.field_on_class_to_fulfil]
                fulfilled_data[f.field_on_class_to_fulfil] = getattr(instance, f.this_field_name)

    for field_name, field_info in {**fulfilled_fields, **instance.__class__.model_fields}.items():
        set_field(new_fulfilled_model, field_name, field_info)

    # (the fields are not copied: a relation might point at a new Create that has been given an id)
    new_fulfilled_model.model_rebuild(force=True)

    # TODO: find a way to copy _meta fields...

    return new_fulfilled_model(**fulfilled_data)
