"""Small tools for making and writing the generated models (see `base_models.py`)"""

from copy import copy
from typing import Any
from uuid import uuid7

from pydantic import BaseModel
from pydantic.fields import FieldInfo


def set_field(model: type, name: str, field: FieldInfo) -> None:
    """The one place that puts a field on a generated model. (Pydantic offers no way to add a field
    to a model that has been made; the model is rebuilt afterwards.)"""
    model.model_fields[name] = field


def forget_schema(model: type[BaseModel]) -> None:
    """Drop the schema that pydantic made for a model, so that a model that refers to it makes the schema
    afresh from the fields, instead of embedding the one that was made when the fields were not all there"""
    for attribute in (
        "__pydantic_core_schema__",
        "__pydantic_validator__",
        "__pydantic_serializer__",
    ):
        if attribute in model.__dict__:
            delattr(model, attribute)
    model.__pydantic_complete__ = False


def inherit_fields(model: type[BaseModel], base: type[BaseModel]) -> None:
    """Give `model` the fields of `base` that it lacks.

    The models that are made for a declared model are given most of their fields after they are made,
    by putting them in `model_fields`. A model made from one of them afterwards (the variant with an edge
    model) does not take those fields: pydantic finds the fields of a subclass from the annotations of
    its bases. Without this, `ViaEdge[Note, Weight]` offered a model with only `type` and `edge_properties`,
    and the note's own fields were silently left out."""
    changed = False
    for name, field in base.model_fields.items():
        if name not in model.model_fields:
            set_field(model, name, copy(field))
            changed = True
    if changed:
        model.model_rebuild(force=True)


def make_id(model: type[BaseModel], data: dict[str, Any]) -> None:
    """Give a thing that is to be written the id it does not have yet.

    An id that is made now is a new thing's, so for a class that can be given an id (`create_with_id`)
    `create_new` goes with it: an id without it is refused, which made it impossible to write one that
    had been created without an id."""
    data["id"] = uuid7()
    if "create_new" in model.model_fields:
        data["create_new"] = True


def data_for_db(
    instance: Any, kwargs: dict[str, Any], *hook_names: str
) -> dict[str, Any]:
    """The data a `CreateDB` / `UpdateDB` is made from: what it is given, or, if the declared model has a
    hook for it (`to_db_create`, `to_db_update`, or `to_db` for both: the first of `hook_names` it has),
    what the hook makes of it"""
    owner = instance._owner
    hook = next((h for name in hook_names if (h := getattr(owner, name, None))), None)
    if hook is None:
        return kwargs
    # (the hook is given the data as it is, not yet validated: validation comes when it is made)
    data = hook(instance.__class__.model_construct(**kwargs))
    return data if isinstance(data, dict) else data.model_dump()
