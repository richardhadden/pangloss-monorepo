import warnings
from typing import ClassVar, Literal, get_args, get_type_hints
from uuid import UUID

from pydantic import AnyHttpUrl, ConfigDict
from pydantic import create_model as pydantic_create_model
from pydantic.alias_generators import to_camel
from pydantic.fields import FieldInfo

from pangloss_models.exceptions import PanglossModelError
from pangloss_models.model_bases.base_models import _DeclaredClass
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.reified_relation import (
    ReifiedRelation,
    ReifiedRelationDocument,
)


def initialise_reference_set_model(model: type[_DeclaredClass]):
    if not issubclass(model, (Entity,)):
        return

    # Checks if Create model has already been created; do not duplicate as we depend
    # on model reference!
    if "ReferenceSet" in model.__dict__:
        return

    try:  # TODO! Remove this guard once all tests passing
        type_hints = get_type_hints(model)
    except Exception:
        return

    if "ReferenceSet" not in type_hints:
        warnings.warn(f"ReferenceSet class hint missing from {model.__name__}")
        return

    # Extracts from the _DeclaredClass definition the annotation for .Create
    reference_set_base_type = get_args(get_args(type_hints["ReferenceSet"])[0])[0]

    if model._meta.accept_url_as_id:
        id_type = UUID | AnyHttpUrl
    else:
        id_type = UUID

    model.ReferenceSet = pydantic_create_model(
        f"{model.__name__}ReferenceSet",
        __base__=reference_set_base_type,
        _owner=(ClassVar[model], model),
        __config__=ConfigDict(alias_generator=to_camel),
        type=(Literal[model.__name__], model.__name__),  # type: ignore
        __doc__=model._meta.description if model._meta.description else "",
        id=id_type,
        label=(str | None, None),
    )  # pyright: ignore[reportAttributeAccessIssue]

    model.ReferenceSet.model_rebuild(force=True)


def initialise_reference_view_model(model: type[_DeclaredClass]):
    if not issubclass(model, (Entity, Document, ReifiedRelationDocument)):
        return

    # Checks if Create model has already been created; do not duplicate as we depend
    # on model reference!
    if "ReferenceView" in model.__dict__:
        return

    try:  # TODO! Remove this guard once all tests passing
        type_hints = get_type_hints(model)
    except Exception:
        return

    if "ReferenceView" not in type_hints:
        warnings.warn(f"ReferenceView class hint missing from {model.__name__}")
        return

    # Extracts from the _DeclaredClass definition the annotation for .Create
    reference_view_base_type = get_args(get_args(type_hints["ReferenceView"])[0])[0]

    id_type = UUID

    if issubclass(model, (ReifiedRelation, ReifiedRelationDocument)) and (
        origin := model.__pydantic_generic_metadata__["origin"]
    ):
        type_name = origin.__name__
    else:
        type_name = model.__name__

    model.ReferenceView = pydantic_create_model(
        f"{model.__name__}ReferenceView",
        __base__=reference_view_base_type,
        _owner=(ClassVar[model], model),
        __config__=ConfigDict(alias_generator=to_camel),
        type=(Literal[type_name], type_name),  # type: ignore
        __doc__=model._meta.description if model._meta.description else "",
        id=id_type,
        label=str,
    )  # pyright: ignore[reportAttributeAccessIssue]

    for field_name in model._meta.reference_view_extra_fields:
        if field_name not in model._meta.fields.literal_fields:
            raise PanglossModelError(
                f"{model.__name__}._meta.reference_view_extra_fields '{field_name}' "
                "either does not exist, is a DBField, or is not a literal field"
            )

        field_definition = model._meta.fields[field_name]

        model.ReferenceView.model_fields[field_name] = FieldInfo(
            annotation=field_definition.annotated_type,  # type: ignore
            validation_alias=to_camel(field_name),
            metadata=field_definition.validators,  # type: ignore
            description=field_definition.description,
        )

    model.ReferenceView.model_rebuild(force=True)
