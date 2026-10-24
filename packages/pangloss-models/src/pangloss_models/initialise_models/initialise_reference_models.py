"""`ReferenceSet` (what is given to refer to an entity) and `ReferenceView` (a short form of a
document or entity, as it is read)."""

import annotationlib
from typing import Any, ClassVar, Literal, get_args
from uuid import UUID

from pydantic import AnyHttpUrl, ConfigDict
from pydantic import create_model as pydantic_create_model
from pydantic.alias_generators import to_camel
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

from pangloss_models.exceptions import PanglossModelError
from pangloss_models.model_bases.base_models import _DeclaredClass
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.model_tools import set_field
from pangloss_models.model_bases.reified_relation import (
    ReifiedRelation,
    ReifiedRelationDocument,
)
from pangloss_models.utils import annotation_is_optional


def declared_reference_base(model: type[_DeclaredClass], attribute: str) -> type:
    """The class that the model made for `attribute` (`ReferenceSet`, `ReferenceView`) is based on.

    The base class of the kind of model declares it, as `ReferenceSet: ClassVar[type[Base]]`. Only that
    annotation is read (not those of the fields, which may refer to models that are not defined in
    a place `typing.get_type_hints` can see, such as one defined in a function)."""
    for cls in model.__mro__:
        annotations = annotationlib.get_annotations(
            cls, format=annotationlib.Format.FORWARDREF
        )
        if attribute in annotations:
            hint: Any = annotations[attribute]
            try:
                return get_args(get_args(hint)[0])[0]
            except IndexError:
                break
    raise PanglossModelError(
        f"{model.__name__} has no base class for its {attribute}: it should be declared as "
        f"`{attribute}: ClassVar[type[<base class>]]` on the class that it is a kind of"
    )


def initialise_reference_set_model(model: type[_DeclaredClass]):
    if not issubclass(model, (Entity,)):
        return

    # (the model is referred to by other models: make it once)
    if "ReferenceSet" in model.__dict__:
        return

    reference_set_base_type = declared_reference_base(model, "ReferenceSet")

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
    )

    model.ReferenceSet.model_rebuild(force=True)


def initialise_reference_view_model(model: type[_DeclaredClass]):
    if not issubclass(model, (Entity, Document, ReifiedRelationDocument)):
        return

    # (the model is referred to by other models: make it once)
    if "ReferenceView" in model.__dict__:
        return

    reference_view_base_type = declared_reference_base(model, "ReferenceView")

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
        # (a thing that requires no label may have none)
        label=str
        if getattr(model._meta, "require_label", True)
        else (str | None, None),
    )

    for field_name in model._meta.reference_view_extra_fields:
        if field_name not in model._meta.fields.literal_fields:
            raise PanglossModelError(
                f"{model.__name__}._meta.reference_view_extra_fields '{field_name}' "
                "either does not exist, is a DBField, or is not a literal field"
            )

        field_definition = model._meta.fields[field_name]

        set_field(
            model.ReferenceView,
            field_name,
            FieldInfo(
                annotation=field_definition.annotated_type,  # type: ignore
                validation_alias=to_camel(field_name),
                metadata=field_definition.validators,  # type: ignore
                description=field_definition.description,
                # An optional literal that is unset is not stored, so cannot be
                # required when reading it back
                default=None
                if annotation_is_optional(field_definition.annotated_type)
                else PydanticUndefined,
            ),
        )

    model.ReferenceView.model_rebuild(force=True)
