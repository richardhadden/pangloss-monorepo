from types import UnionType
from typing import Annotated, ClassVar, Literal, TypeVar, Union, cast

from frozendict import frozendict
from pydantic import ConfigDict, Field
from pydantic import create_model as pydantic_create_model
from pydantic.alias_generators import to_camel
from pydantic.fields import FieldInfo

from pangloss_models.field_definitions import (
    EmbeddedFieldDefinition,
    FieldBinding,
    ParameterTypeOptions,
    RelationFieldDefinition,
    RelationToDocument,
    RelationToEntity,
    RelationToGeneric,
    RelationToTypeVar,
)
from pangloss_models.model_bases.base_models import (
    _DeclaredClass,
    _ViewBase,
)
from pangloss_models.model_bases.conjunction import (
    Conjunction,
    _ConjunctionViewBase,
)
from pangloss_models.model_bases.document import (
    Document,
    _DocumentViewBase,
)
from pangloss_models.model_bases.embedded import (
    Embedded,
    _EmbeddedViewBase,
)
from pangloss_models.model_bases.entity import (
    Entity,
    _EntityViewBase,
)
from pangloss_models.model_bases.reified_relation import (
    ReifiedRelation,
    ReifiedRelationDocument,
    _ReifiedRelationDocumentViewBase,
    _ReifiedRelationViewBase,
)
from pangloss_models.model_bases.semantic_space import (
    SemanticSpace,
    _SemanticSpaceViewBase,
)
from pangloss_models.utils import (
    field_has_inherited_field_bindings,
    map_validators_to_kwargs,
)


def build_label_field_on_view_model(
    view_model: type[_ViewBase],
):

    if getattr(view_model._meta, "require_label", True):
        view_model.model_fields["label"] = FieldInfo(annotation=str)


def unpack_generic_fields(
    model: type[Document | Entity | ReifiedRelation],
) -> dict[str, TypeVar | type[list[TypeVar]]]:
    generic_fields = {}
    for f, fi in model.model_fields.items():
        if isinstance(fi.annotation, TypeVar):
            generic_fields[f] = fi.annotation

    return generic_fields


def can_have_view_model(model: type[_DeclaredClass]) -> bool:
    return issubclass(
        model,
        (
            Document,
            Entity,
            ReifiedRelation,
            ReifiedRelationDocument,
            Conjunction,
            SemanticSpace,
            Embedded,
        ),
    )


def get_view_base_model_type(
    model: type[
        Document
        | Embedded
        | Entity
        | ReifiedRelation
        | ReifiedRelationDocument
        | Conjunction
        | SemanticSpace
    ],
) -> type[_ViewBase] | None:
    if issubclass(model, Document):
        return _DocumentViewBase
    elif issubclass(model, Entity):
        return _EntityViewBase
    elif issubclass(model, ReifiedRelation):
        return _ReifiedRelationViewBase
    elif issubclass(model, ReifiedRelationDocument):
        return _ReifiedRelationDocumentViewBase
    elif issubclass(model, Conjunction):
        return _ConjunctionViewBase
    elif issubclass(model, SemanticSpace):
        return _SemanticSpaceViewBase
    elif issubclass(model, Embedded):
        return _EmbeddedViewBase
    return None


def initialise_view_model(
    model: type[
        Document
        | Embedded
        | Entity
        | ReifiedRelation
        | ReifiedRelationDocument
        | Conjunction
        | SemanticSpace
    ],
) -> None:

    if not can_have_view_model(model):
        return

    # Checks if View model has already been created; do not duplicate as we depend
    # on model reference!
    if "View" in model.__dict__:
        return

    # Extracts from the _DeclaredClass definition the annotation for .Create
    view_base_type = get_view_base_model_type(model)
    if not view_base_type:
        return

    model.View = pydantic_create_model(  # ty:ignore[invalid-assignment]
        f"{model.__name__}View",
        __base__=view_base_type,
        __module__=model.__module__,
        _owner=(ClassVar[model], model),
        __doc__=model._meta.description if model._meta.description else "",
        __config__=ConfigDict(alias_generator=to_camel),
        type=(Literal[model.__name__], model.__name__),  # type: ignore
    )  # pyright: ignore[reportAttributeAccessIssue]

    build_label_field_on_view_model(model.View)

    model.View.model_rebuild(force=True)


def recursively_get_generic_naming(
    parameter_type_options: frozendict[str, ParameterTypeOptions],
):
    names = []
    for pto in parameter_type_options.values():
        for to in pto.type_options:
            if isinstance(to, RelationToGeneric):
                names.append(
                    f"{to.base_type.__name__}[{recursively_get_generic_naming(to.parameter_type_options)}]"
                )
            elif isinstance(to, (RelationToEntity, RelationToDocument)):
                names.append(to.annotated_type.__name__)
    return f"{', '.join(names)}"


def build_generic_view_model_from_type_option(
    type_option: RelationToGeneric, field_bindings
):
    """Taking a type option, build a Model.Create for each type option with the type options
    bound to the appropriate fields"""

    # Get the generic base type
    generic_relation_type = type_option.base_type

    # Assure that Create is initalised on this model
    initialise_view_model(generic_relation_type)

    # Add the non-TypeVar fields to the base model
    add_fields_to_view_model(generic_relation_type.View, frozenset())

    # Rebuild
    generic_relation_type.View.model_rebuild(force=True)

    # We need to name our class with the bound fields, in the form Generic[type_names],
    # so extract the type names (recursing down)
    type_names = recursively_get_generic_naming(type_option.parameter_type_options)

    # Create a bound model
    bound_view_model = pydantic_create_model(
        f"{generic_relation_type.__name__}[{type_names}]View",
        __base__=generic_relation_type.View,
        __module__=generic_relation_type.__module__,
        _owner=(ClassVar[generic_relation_type], generic_relation_type),
        __config__=ConfigDict(alias_generator=to_camel),
        type=(Literal[generic_relation_type.__name__], generic_relation_type.__name__),  # ty:ignore[invalid-type-form]
    )

    if field_bindings:
        bound_view_model = build_bound_field_view_model(
            bound_view_model, field_bindings
        )

    # For some reason, we need to manually add all the fields from the Generic unbound type
    # (you would have thought inheriting as __base__ above would have done this, but no)
    for field_name, field_info in generic_relation_type.View.model_fields.items():
        bound_view_model.model_fields[field_name] = field_info

    # Now, go through all the relation fields on the Generic type
    for (
        field_name,
        field_definition,
    ) in generic_relation_type._meta.fields.relation_fields.items():
        # Initialise a list of possible annotations for this field

        annotations = []

        # Iterate the type_options for this field
        for generic_type_option in field_definition.type_options:
            if isinstance(generic_type_option, RelationToTypeVar):
                # Look up the actual type options based on the typevar name
                for to in (
                    type_option.parameter_type_options[
                        generic_type_option.type_var_name
                    ]
                ).type_options:
                    # For relation to entity we want to use ReferenceSet
                    if isinstance(to, RelationToEntity):
                        # ... if there is an edge model, add the applied_edge_model
                        # version of annotated_type.ReferenceSet to annotation

                        if to.edge_model:
                            annotations.append(
                                to.annotated_type.ReferenceView.apply_edge_model(
                                    to.edge_model
                                )
                            )

                        else:
                            # ... otherwise, just add the annotated_type.ReferenceSet
                            annotations.append(to.annotated_type.ReferenceView)

                    # If relation to Document...
                    elif isinstance(to, RelationToDocument):
                        # Add edge to Document.Create and use

                        initialise_view_model(to.annotated_type)
                        view_type = to.annotated_type.View

                        if field_bindings:
                            view_type = build_bound_field_view_model(
                                view_type, field_bindings
                            )

                        if to.edge_model:
                            annotations.append(
                                view_type.apply_edge_model(to.edge_model)
                            )
                        else:
                            # Add or use Document.View
                            annotations.append(view_type)

                    # Otherwise, if it is anything that can be generic,
                    # pass the type option back to the this function to get the
                    # internal bound generic at the next level
                    elif isinstance(to, RelationToGeneric):
                        if to.edge_model:
                            annotations.append(
                                build_generic_view_model_from_type_option(
                                    to, field_bindings
                                ).apply_edge_model(to.edge_model)
                            )
                        annotations.append(
                            build_generic_view_model_from_type_option(
                                to, field_bindings
                            )
                        )
            if isinstance(generic_type_option, RelationToEntity):
                # ... if there is an edge model, add the applied_edge_model
                # version of annotated_type.ReferenceSet to annotation
                if generic_type_option.edge_model:
                    annotations.append(
                        generic_type_option.annotated_type.ReferenceView.apply_edge_model(
                            generic_type_option.edge_model
                        )
                    )
                    if generic_type_option.annotated_type._meta.create_inline:
                        annotations.append(
                            generic_type_option.annotated_type.View.apply_edge_model(
                                generic_type_option.edge_model
                            )
                        )
                else:
                    # ... otherwise, just add the annotated_type.ReferenceSet
                    annotations.append(generic_type_option.annotated_type.ReferenceView)

            # If relation to Document...
            elif isinstance(generic_type_option, RelationToDocument):
                # Add edge to Document.Create and use

                view_type = generic_type_option.annotated_type.View

                if field_bindings:
                    view_type = build_bound_field_view_model(view_type, field_bindings)

                if generic_type_option.edge_model:
                    annotations.append(
                        view_type.apply_edge_model(generic_type_option.edge_model)
                    )
                else:
                    # Add or use Document.Create
                    annotations.append(view_type)
        if field_definition.wrapper:
            annotation = field_definition.wrapper[  # type: ignore
                Annotated[Union[*annotations], Field(discriminator="type")]  # ty:ignore[invalid-type-form]
            ]
        else:
            annotation = Union[*annotations]  # ty:ignore[invalid-type-form]

        bound_view_model.model_fields[field_name] = FieldInfo(
            annotation=annotation,  # type: ignore
            validation_alias=to_camel(field_name),
            metadata=field_definition.validators,  # type: ignore
            discriminator="type" if not field_definition.wrapper else None,
            description=field_definition.description,
        )

        bound_view_model.model_rebuild(force=True)

    return bound_view_model


bound_models_built = {}


def build_bound_field_view_model[
    TModel: type[
        _DocumentViewBase
        | _EmbeddedViewBase
        | _EntityViewBase
        | _ReifiedRelationViewBase
        | _ReifiedRelationDocumentViewBase
        | _ConjunctionViewBase
        | _SemanticSpaceViewBase
    ]
](
    view_model: TModel,
    field_bindings: frozenset[FieldBinding],
) -> TModel:

    assert issubclass(
        view_model,
        (
            _DocumentViewBase,
            _EmbeddedViewBase,
            _EntityViewBase,
            _ReifiedRelationViewBase,
            _ReifiedRelationDocumentViewBase,
            _ConjunctionViewBase,
            _SemanticSpaceViewBase,
        ),
    )

    args_hash = hash(hash(view_model) + hash(frozenset((field_bindings))))

    if args_hash in bound_models_built:
        return bound_models_built[args_hash]

    model = view_model._owner

    bound_fields_view_model = pydantic_create_model(
        f"{view_model.__name__}[bound=({','.join(str(fb) for fb in field_bindings)})]View",
        __base__=view_model,
        __module__=model.__module__,
        _owner=(ClassVar[model], model),
        __config__=ConfigDict(alias_generator=to_camel),
        type=(Literal[model.__name__], model.__name__),  # type: ignore
    )

    bound_models_built[args_hash] = bound_fields_view_model

    build_label_field_on_view_model(bound_fields_view_model)

    add_fields_to_view_model(bound_fields_view_model, fields_to_bind=field_bindings)
    bound_fields_view_model.model_rebuild(force=True)
    return cast(TModel, bound_fields_view_model)


def get_relation_annotation_types(
    field_definition: RelationFieldDefinition, field_bindings: list[FieldBinding]
) -> UnionType | type[list[UnionType]] | tuple[list[UnionType]] | None:
    types = []
    for type_option in field_definition.type_options:
        if isinstance(type_option, RelationToEntity):
            if type_option.edge_model:
                types.append(
                    type_option.annotated_type.ReferenceView.apply_edge_model(
                        type_option.edge_model
                    )
                )
            else:
                types.append(type_option.annotated_type.ReferenceView)

        elif isinstance(type_option, RelationToDocument):
            initialise_view_model(type_option.annotated_type)

            if field_bindings:
                view_model = build_bound_field_view_model(
                    type_option.annotated_type.View, frozenset(field_bindings)
                )
            else:
                view_model = type_option.annotated_type.View

            if type_option.edge_model:
                types.append(view_model.apply_edge_model(type_option.edge_model))
            else:
                types.append(view_model)

        elif isinstance(
            type_option,
            (RelationToGeneric),
        ):
            bound_reified_view_type = build_generic_view_model_from_type_option(
                type_option, frozenset(field_bindings)
            )

            if type_option.edge_model:
                types.append(
                    bound_reified_view_type.apply_edge_model(type_option.edge_model)
                )
            else:
                types.append(bound_reified_view_type)

    if not types:
        return None

    if field_definition.wrapper:
        return field_definition.wrapper[  # type: ignore
            Annotated[Union[*types], Field(discriminator="type")]
        ]

    return Union[*types]


def get_embedded_annotation_types(
    field_definition: EmbeddedFieldDefinition,
) -> UnionType:
    types = []
    for type_option in field_definition.type_options:
        types.append(type_option.annotated_type.View)
    return Union[*types]  # type: ignore


def add_fields_to_view_model(
    model: type[
        _DocumentViewBase
        | _EmbeddedViewBase
        | _EntityViewBase
        | _ReifiedRelationViewBase
        | _ReifiedRelationDocumentViewBase
        | _ConjunctionViewBase
        | _SemanticSpaceViewBase
    ],
    fields_to_bind: frozenset[FieldBinding],
) -> None:

    # Literal fields
    for field_name, field_definition in model._meta.fields.literal_fields.items():
        optional = field_definition.field_required_to_fulfil
        has_inherited_bindings = field_has_inherited_field_bindings(
            fields_to_bind, field_name, field_definition.field_on_model
        )
        if has_inherited_bindings or optional:
            annotation = field_definition.annotated_type | None
        else:
            annotation = field_definition.annotated_type

        if field_definition.db_field:
            continue
        model.model_fields[field_name] = FieldInfo(
            annotation=annotation,
            validation_alias=to_camel(field_name),
            description=field_definition.description,
            **map_validators_to_kwargs(field_definition.validators),
        )
        if has_inherited_bindings or optional:
            model.model_fields[field_name].default = None

    # Embedded fields
    for field_name, field_definition in model._meta.fields.embedded_fields.items():
        if field_definition.db_field:
            continue

        annotation = get_embedded_annotation_types(field_definition)

        has_inherited_bindings = field_has_inherited_field_bindings(
            fields_to_bind, field_name, field_definition.field_on_model
        )
        if has_inherited_bindings:
            annotation = annotation | None

        if annotation:
            model.model_fields[field_name] = FieldInfo(
                annotation=annotation,  # type: ignore
                validation_alias=to_camel(field_name),
                discriminator="type",
                description=field_definition.description,
            )
        if has_inherited_bindings:
            model.model_fields[field_name].default = None

    # Relation fields
    for (
        field_name,
        field_definition,
    ) in model._meta.fields.relation_fields.items():
        if field_definition.db_field:
            continue

        annotation = get_relation_annotation_types(
            field_definition,
            field_bindings=[
                *field_definition.bind_to_child_field,
                *fields_to_bind,
            ],
        )

        field_optional = False
        if (
            field_definition.field_required_to_fulfil
            and not field_definition.subclasses_parent_fields
        ) or field_has_inherited_field_bindings(
            fields_to_bind, field_name, field_definition.field_on_model
        ):
            field_optional = True
            annotation = Union[annotation, None]  # type: ignore

        if annotation:
            model.model_fields[field_name] = FieldInfo(
                annotation=annotation,  # type: ignore
                validation_alias=to_camel(field_name),
                discriminator="type" if not field_definition.wrapper else None,
                description=field_definition.description,
                **map_validators_to_kwargs(field_definition.validators),
            )

            if field_optional:
                model.model_fields[field_name].default = None

    # Annotated values
    for (
        field_name,
        field_definition,
    ) in model._meta.fields.annotated_value_fields.items():
        if field_definition.db_field:
            continue

        annotation = field_definition.annotated_type
        has_inherited_bindings = field_has_inherited_field_bindings(
            fields_to_bind, field_name, field_definition.field_on_model
        )
        if has_inherited_bindings:
            annotation = annotation | None

        model.model_fields[field_name] = FieldInfo(
            annotation=annotation,
            description=field_definition.description,
        )
        if has_inherited_bindings:
            model.model_fields[field_name].default = None

    model.model_rebuild(force=True)
