"""`EditView`: a head node as it is edited. It is the `HeadView` without the incoming
relations: only the node's own values and its outgoing relations. (An incoming relation
is written in the document that holds it, so it is not for editing here.)"""

from copy import copy
from typing import ClassVar, Literal

from pydantic import ConfigDict
from pydantic import create_model as pydantic_create_model
from pydantic.alias_generators import to_camel

from pangloss_models.model_bases.base_models import _DeclaredClass
from pangloss_models.model_bases.entity import Entity, _EntityEditViewBase
from pangloss_models.model_bases.model_tools import set_field


def can_have_edit_view_model(model: type[_DeclaredClass]) -> bool:
    return issubclass(model, Entity)


def initialise_edit_view_model(model: type[Entity]) -> None:
    if not can_have_edit_view_model(model):
        return

    # (a persistent reference to the model is depended on: do not make it twice)
    if "EditView" in model.__dict__:
        return

    model.EditView = pydantic_create_model(
        f"{model.__name__}EditView",
        __base__=(_EntityEditViewBase, model.View),
        __module__=model.__module__,
        _owner=(ClassVar[model], model),
        __doc__=model._meta.description if model._meta.description else "",
        __config__=ConfigDict(alias_generator=to_camel),
        type=(Literal[model.__name__], model.__name__),  # type: ignore
    )

    for field_name, field_info in model.View.model_fields.items():
        if field_name == "meta":
            continue
        set_field(model.EditView, field_name, copy(field_info))

    model.EditView.model_rebuild(force=True)
