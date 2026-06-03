from typing import Any, ClassVar, Literal, Union, cast

from pydantic import ConfigDict
from pydantic import create_model as pydantic_create_model
from pydantic.alias_generators import to_camel
from pydantic.fields import FieldInfo

from pangloss_models.field_definitions import IncomingRelationDefinition
from pangloss_models.initialise_models.initialise_view_model import (
    get_relation_annotation_types,
    get_view_base_model_type,
)
from pangloss_models.model_bases.base_models import _DeclaredClass
from pangloss_models.model_bases.document import Document, _DocumentHeadViewBase
from pangloss_models.model_bases.entity import Entity, _EntityHeadViewBase
from pangloss_models.model_bases.reified_relation import (
    ReifiedRelationDocument,
    _ReifiedRelationDocumentHeadViewBase,
)


def can_have_head_view_model(model: type[_DeclaredClass]) -> bool:
    return issubclass(
        model,
        (
            Document,
            Entity,
            ReifiedRelationDocument,
        ),
    )


def get_head_view_base_model_type(
    model: type[Document | Entity | ReifiedRelationDocument],
) -> (
    type[
        _DocumentHeadViewBase
        | _EntityHeadViewBase
        | _ReifiedRelationDocumentHeadViewBase
    ]
    | None
):
    if issubclass(model, Document):
        return _DocumentHeadViewBase
    elif issubclass(model, Entity):
        return _EntityHeadViewBase
    elif issubclass(model, ReifiedRelationDocument):
        return _ReifiedRelationDocumentHeadViewBase


def build_label_field_on_head_view_model(
    head_view_model: type[
        _DocumentHeadViewBase
        | _EntityHeadViewBase
        | _ReifiedRelationDocumentHeadViewBase
    ],
):

    if getattr(head_view_model._meta, "require_label", True):
        head_view_model.model_fields["label"] = FieldInfo(annotation=str)


def build_incoming_bound_model(
    field_name: str,
    target_model: type[_DeclaredClass],
    incoming_relation_definition: IncomingRelationDefinition,
):
    source_model = cast(type[Document | Entity], incoming_relation_definition.source)

    incoming_bound_model = pydantic_create_model(
        f"{source_model.__name__}View.from.{target_model.__name__}.{field_name}",
        __base__=source_model.View,
        __module__=source_model.__module__,
        _owner=(ClassVar[source_model], source_model),
        __doc__=source_model._meta.description
        if source_model._meta.description
        else "",
        __config__=ConfigDict(alias_generator=to_camel),
        type=(Literal[source_model.__name__], source_model.__name__),  # type: ignore
    )
    annotation = get_relation_annotation_types(
        incoming_relation_definition.field_definition, field_bindings=[]
    )
    if annotation:
        incoming_bound_model.model_fields[
            incoming_relation_definition.field_definition.field_name
        ] = FieldInfo(annotation=annotation)  # type: ignore

    return incoming_bound_model


def initialise_head_view_model(
    model: type[Document | Entity | ReifiedRelationDocument],
) -> None:

    if not can_have_head_view_model(model):
        return

    # Checks if HeadView model has already been created;
    # do not duplicate as we depend on persistent model reference!
    if "HeadView" in model.__dict__:
        return

    # Extracts from the _DeclaredClass definition the annotation for .HeadView
    head_view_base_type = get_head_view_base_model_type(model)
    if not head_view_base_type:
        return

    model.HeadView = pydantic_create_model(  # ty:ignore[invalid-assignment]
        f"{model.__name__}HeadView",
        __base__=(head_view_base_type, model.View),
        __module__=model.__module__,
        _owner=(ClassVar[model], model),
        __doc__=model._meta.description if model._meta.description else "",
        __config__=ConfigDict(alias_generator=to_camel),
        type=(Literal[model.__name__], model.__name__),  # type: ignore
    )

    for field_name, field_info in model.View.model_fields.items():
        if field_name == "meta":
            continue
        model.HeadView.model_fields[field_name] = field_info

    for (
        incoming_field_name,
        incoming_relation_definitions,
    ) in model._meta.field_definitions.incoming_fields.items():
        annotation_types: list[Any] = []
        for incoming_relation_definition in incoming_relation_definitions:
            if incoming_relation_definition.via_reified:
                annotation_types.append(
                    build_incoming_bound_model(
                        incoming_field_name, model, incoming_relation_definition
                    )
                )
            else:
                annotation_types.append(
                    incoming_relation_definition.source.ReferenceView
                )

        if annotation_types:
            annotation = Union[*annotation_types]  # type:ignore

            model.HeadView.model_fields[incoming_field_name] = FieldInfo(
                annotation=list[annotation], default_factory=list
            )

    model.HeadView.model_rebuild(force=True)
