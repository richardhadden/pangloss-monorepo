from functools import cache
from types import UnionType
from typing import Annotated, ClassVar, Literal, Union, cast

from frozendict import frozendict
from pydantic import ConfigDict, Field, model_validator
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
from pangloss_models.initialise_models.initialise_create_model import (
    build_bound_field_create_model,
    build_generic_create_model_from_type_option,
    check_create_and_id_present,
)
from pangloss_models.model_bases.base_models import _DeclaredClass, _UpdateBase
from pangloss_models.model_bases.conjunction import Conjunction, _ConjunctionUpdateBase
from pangloss_models.model_bases.document import Document, _DocumentUpdateBase
from pangloss_models.model_bases.embedded import Embedded, _EmbeddedUpdateBase
from pangloss_models.model_bases.entity import Entity, _EntityUpdateBase
from pangloss_models.model_bases.reified_relation import (
    ReifiedRelation,
    ReifiedRelationDocument,
    _ReifiedRelationDocumentUpdateBase,
    _ReifiedRelationUpdateBase,
)
from pangloss_models.model_bases.semantic_space import (
    SemanticSpace,
    _SemanticSpaceUpdateBase,
)
from pangloss_models.utils import (
    field_has_inherited_field_bindings,
    map_validators_to_kwargs,
)


def can_have_update_model(model: type[_DeclaredClass]) -> bool:
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


def get_update_base_model_type(
    model: type[
        Document
        | Embedded
        | Entity
        | ReifiedRelation
        | ReifiedRelationDocument
        | Conjunction
        | SemanticSpace
    ],
) -> type[_UpdateBase] | None:
    if issubclass(model, Document):
        return _DocumentUpdateBase
    elif issubclass(model, Entity):
        return _EntityUpdateBase
    elif issubclass(model, ReifiedRelation):
        return _ReifiedRelationUpdateBase
    elif issubclass(model, ReifiedRelationDocument):
        return _ReifiedRelationDocumentUpdateBase
    elif issubclass(model, Conjunction):
        return _ConjunctionUpdateBase
    elif issubclass(model, SemanticSpace):
        return _SemanticSpaceUpdateBase
    elif issubclass(model, Embedded):
        return _EmbeddedUpdateBase
    return None


def initialise_update_model(
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

    if not can_have_update_model(model):
        return

    # Checks if Update model has already been created; do not duplicate as we depend
    # on model reference!
    if "Update" in model.__dict__:
        return

    update_base_type = get_update_base_model_type(model)
    if not update_base_type:
        return

    model.Update = pydantic_create_model(  # ty:ignore[invalid-assignment]
        f"{model.__name__}Update",
        __base__=update_base_type,
        __module__=model.__module__,
        _owner=(ClassVar[model], model),
        __doc__=model._meta.description if model._meta.description else "",
        __config__=ConfigDict(alias_generator=to_camel),
        type=(Literal[model.__name__], Field(default=model.__name__)),  # type: ignore
    )  # pyright: ignore[reportAttributeAccessIssue]

    build_label_field_on_update_model(model.Update)

    model.Update.model_rebuild(force=True)


def build_label_field_on_update_model(
    create_model: type[_UpdateBase],
):

    if getattr(create_model._meta, "require_label", True):
        create_model.model_fields["label"] = FieldInfo(annotation=str)


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


@cache
def build_generic_update_model_from_type_option(
    type_option: RelationToGeneric, field_bindings
):
    """Taking a type option, build a Model.Create for each type option with the type options
    bound to the appropriate fields"""

    # Get the generic base type
    generic_relation_type = type_option.base_type

    # Assure that Create is initalised on this model
    initialise_update_model(generic_relation_type)

    # Add the non-TypeVar fields to the base model
    add_fields_to_update_model(generic_relation_type.Update, frozenset())

    # Rebuild
    generic_relation_type.Update.model_rebuild(force=True)

    # We need to name our class with the bound fields, in the form Generic[type_names],
    # so extract the type names (recursing down)
    type_names = recursively_get_generic_naming(type_option.parameter_type_options)

    # Create a bound model
    bound_update_model = pydantic_create_model(
        f"{generic_relation_type.__name__}[{type_names}]Update",
        __base__=generic_relation_type.Update,
        __validators__=get_model_validators(generic_relation_type),
        __module__=generic_relation_type.__module__,
        _owner=(ClassVar[generic_relation_type], generic_relation_type),
        __config__=ConfigDict(alias_generator=to_camel),
        type=(Literal[generic_relation_type.__name__], generic_relation_type.__name__),  # ty:ignore[invalid-type-form]
    )

    if field_bindings:
        bound_create_model = build_bound_field_update_model(
            bound_update_model, field_bindings
        )

    # For some reason, we need to manually add all the fields from the Generic unbound type
    # (you would have thought inheriting as __base__ above would have done this, but no)
    for field_name, field_info in generic_relation_type.Create.model_fields.items():
        bound_update_model.model_fields[field_name] = field_info

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
                                to.annotated_type.ReferenceSet.apply_edge_model(
                                    to.edge_model
                                )
                            )
                            if to.annotated_type._meta.create_inline:
                                annotations.append(
                                    to.annotated_type.Create.apply_edge_model(
                                        to.edge_model
                                    )
                                )
                        else:
                            # ... otherwise, just add the annotated_type.ReferenceSet
                            annotations.append(to.annotated_type.ReferenceSet)
                            if to.annotated_type._meta.create_inline:
                                annotations.append(to.annotated_type.Create)

                    # If relation to Document...
                    elif isinstance(to, RelationToDocument):
                        # Add edge to Document.Create and use

                        initialise_update_model(to.annotated_type)
                        create_type = to.annotated_type.Create
                        update_type = to.annotated_type.Update

                        if field_bindings:
                            create_type = build_bound_field_create_model(
                                create_type, field_bindings
                            )
                            update_type = build_bound_field_update_model(
                                update_type, field_bindings
                            )

                        if to.edge_model:
                            annotations.append(
                                create_type.apply_edge_model(to.edge_model)
                            )
                            annotations.append(
                                update_type.apply_edge_model(to.edge_model)
                            )
                        else:
                            # Add or use Document.Create
                            annotations.append(create_type)
                            annotations.append(update_type)

                    # Otherwise, if it is anything that can be generic,
                    # pass the type option back to the this function to get the
                    # internal bound generic at the next level
                    elif isinstance(to, RelationToGeneric):
                        if to.edge_model:
                            annotations.append(
                                build_generic_update_model_from_type_option(
                                    to, field_bindings
                                ).apply_edge_model(to.edge_model)
                            )
                            annotations.append(
                                build_generic_create_model_from_type_option(
                                    to, field_bindings
                                ).apply_edge_model(to.edge_model)
                            )
                        annotations.append(
                            build_generic_update_model_from_type_option(
                                to, field_bindings
                            )
                        )
                        annotations.append(
                            build_generic_create_model_from_type_option(
                                to, field_bindings
                            )
                        )
            if isinstance(generic_type_option, RelationToEntity):
                # ... if there is an edge model, add the applied_edge_model
                # version of annotated_type.ReferenceSet to annotation
                if generic_type_option.edge_model:
                    annotations.append(
                        generic_type_option.annotated_type.ReferenceSet.apply_edge_model(
                            generic_type_option.edge_model
                        )
                    )
                    if generic_type_option.annotated_type._meta.create_inline:
                        annotations.append(
                            generic_type_option.annotated_type.Create.apply_edge_model(
                                generic_type_option.edge_model
                            )
                        )
                else:
                    # ... otherwise, just add the annotated_type.ReferenceSet
                    annotations.append(generic_type_option.annotated_type.ReferenceSet)
                    if generic_type_option.annotated_type._meta.create_inline:
                        annotations.append(generic_type_option.annotated_type.Create)

            # If relation to Document...
            elif isinstance(generic_type_option, RelationToDocument):
                # Add edge to Document.Create and use

                create_type = generic_type_option.annotated_type.Create

                if field_bindings:
                    create_type = build_bound_field_create_model(
                        create_type, field_bindings
                    )

                if generic_type_option.edge_model:
                    annotations.append(
                        create_type.apply_edge_model(generic_type_option.edge_model)
                    )
                else:
                    # Add or use Document.Create
                    annotations.append(create_type)
        if field_definition.wrapper:
            annotation = field_definition.wrapper[  # type: ignore
                Annotated[Union[*annotations], Field()]  # ty:ignore[invalid-type-form]
            ]
        else:
            annotation = Union[*annotations]  # ty:ignore[invalid-type-form]

        bound_update_model.model_fields[field_name] = FieldInfo(
            annotation=annotation,  # type: ignore
            validation_alias=to_camel(field_name),
            metadata=field_definition.validators,  # type: ignore
            # discriminator="type" if not field_definition.wrapper else None,
            description=field_definition.description,
        )

        bound_update_model.model_rebuild(force=True)

    return bound_update_model


def get_model_validators(model):
    validators = {}
    if getattr(model._meta, "create_with_id", False):
        validators["check_create_and_id_present"] = model_validator(mode="after")(
            check_create_and_id_present
        )

    return validators


bound_models_built = {}


def build_bound_field_update_model[
    TModel: type[
        _DocumentUpdateBase
        | _EmbeddedUpdateBase
        | _EntityUpdateBase
        | _ReifiedRelationUpdateBase
        | _ReifiedRelationDocumentUpdateBase
        | _ConjunctionUpdateBase
        | _SemanticSpaceUpdateBase
    ]
](
    update_model: TModel,
    field_bindings: frozenset[FieldBinding],
) -> TModel:

    assert issubclass(
        update_model,
        (
            _DocumentUpdateBase,
            _EmbeddedUpdateBase,
            _EntityUpdateBase,
            _ReifiedRelationUpdateBase,
            _ReifiedRelationDocumentUpdateBase,
            _ConjunctionUpdateBase,
            _SemanticSpaceUpdateBase,
        ),
    )

    args_hash = hash(hash(update_model) + hash(frozenset((field_bindings))))

    if args_hash in bound_models_built:
        return bound_models_built[args_hash]

    model = update_model._owner

    bound_fields_create_model: TModel = cast(
        TModel,
        pydantic_create_model(
            f"{update_model.__name__}[bound=({','.join(str(fb) for fb in field_bindings)})]",
            __base__=update_model,
            __validators__=get_model_validators(model),
            __module__=model.__module__,
            _owner=(ClassVar[model], model),
            __config__=ConfigDict(alias_generator=to_camel),
            type=(Literal[model.__name__], model.__name__),  # type: ignore
        ),
    )

    bound_models_built[args_hash] = bound_fields_create_model

    build_label_field_on_update_model(bound_fields_create_model)

    add_fields_to_update_model(bound_fields_create_model, fields_to_bind=field_bindings)
    bound_fields_create_model.model_rebuild(force=True)  # type: ignore
    return bound_fields_create_model


def get_relation_annotation_types(
    field_definition: RelationFieldDefinition, field_bindings: frozenset[FieldBinding]
) -> UnionType | type[list[UnionType]] | tuple[list[UnionType]] | None:
    types = []
    for type_option in field_definition.type_options:
        if isinstance(type_option, RelationToEntity):
            if type_option.edge_model:
                types.append(
                    type_option.annotated_type.ReferenceSet.apply_edge_model(
                        type_option.edge_model
                    )
                )
            else:
                types.append(type_option.annotated_type.ReferenceSet)
                if type_option.annotated_type._meta.create_inline:
                    types.append(type_option.annotated_type.Create)

        elif isinstance(type_option, RelationToDocument):
            initialise_update_model(type_option.annotated_type)
            if field_bindings:
                update_model = build_bound_field_update_model(
                    type_option.annotated_type.Update, field_bindings
                )
                create_model = build_bound_field_create_model(
                    type_option.annotated_type.Create, field_bindings
                )
            else:
                update_model = type_option.annotated_type.Update
                create_model = type_option.annotated_type.Create

            if type_option.edge_model:
                types.append(update_model.apply_edge_model(type_option.edge_model))
                types.append(create_model.apply_edge_model(type_option.edge_model))
            else:
                types.append(update_model)
                types.append(create_model)

        elif isinstance(
            type_option,
            (RelationToGeneric),
        ):
            bound_reified_update_type = build_generic_update_model_from_type_option(
                type_option, frozenset(field_bindings)
            )
            bound_reified_create_type = build_generic_create_model_from_type_option(
                type_option, frozenset(field_bindings)
            )

            if type_option.edge_model:
                types.append(
                    bound_reified_update_type.apply_edge_model(type_option.edge_model)
                )
                types.append(
                    bound_reified_create_type.apply_edge_model(type_option.edge_model)
                )
            else:
                types.append(bound_reified_update_type)
                types.append(bound_reified_create_type)

    if not types:
        return None

    if field_definition.wrapper:
        return field_definition.wrapper[  # type: ignore
            Annotated[Union[*types], Field()]
        ]

    return Union[*types]


def get_embedded_annotation_types(
    field_definition: EmbeddedFieldDefinition,
) -> UnionType:
    types = []
    for type_option in field_definition.type_options:
        types.append(type_option.annotated_type.Update)
        types.append(type_option.annotated_type.Create)

    return Union[*types]  # type: ignore


def add_fields_to_update_model(
    model: type[
        _DocumentUpdateBase
        | _EmbeddedUpdateBase
        | _EntityUpdateBase
        | _ReifiedRelationUpdateBase
        | _ReifiedRelationDocumentUpdateBase
        | _ConjunctionUpdateBase
        | _SemanticSpaceUpdateBase
    ],
    fields_to_bind: frozenset,
) -> None:
    pass

    # Literal fields
    for field_name, field_definition in model._meta.fields.literal_fields.items():
        has_inherited_bindings = field_has_inherited_field_bindings(
            fields_to_bind, field_name, field_definition.field_on_model
        )
        optional = field_definition.field_required_to_fulfil
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
        optional = field_definition.field_required_to_fulfil
        if field_definition.db_field:
            continue

        annotation = get_embedded_annotation_types(field_definition)

        has_inherited_bindings = field_has_inherited_field_bindings(
            fields_to_bind, field_name, field_definition.field_on_model
        )
        if has_inherited_bindings or optional:
            annotation = annotation | None

        if annotation:
            model.model_fields[field_name] = FieldInfo(
                annotation=annotation,  # type: ignore
                validation_alias=to_camel(field_name),
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
            field_bindings=frozenset(
                [
                    *field_definition.bind_to_child_field,
                    *fields_to_bind,
                ]
            ),
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
                # discriminator="type" if not field_definition.wrapper else None,
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
        optional = field_definition.field_required_to_fulfil
        if field_definition.db_field:
            continue

        annotation = field_definition.annotated_type
        has_inherited_bindings = field_has_inherited_field_bindings(
            fields_to_bind, field_name, field_definition.field_on_model
        )
        if has_inherited_bindings or optional:
            annotation = annotation | None

        model.model_fields[field_name] = FieldInfo(
            annotation=annotation,
            description=field_definition.description,
        )
        if has_inherited_bindings:
            model.model_fields[field_name].default = None
    model.model_rebuild(force=True)
