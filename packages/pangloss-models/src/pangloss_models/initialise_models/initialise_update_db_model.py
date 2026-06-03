from types import UnionType
from typing import Annotated, ClassVar, Literal, TypeVar, Union
from uuid import UUID

from frozendict import frozendict
from pydantic import AnyHttpUrl, ConfigDict, Field
from pydantic import create_model as pydantic_create_model
from pydantic.alias_generators import to_camel
from pydantic.fields import FieldInfo

from pangloss_models.field_definitions import (
    EmbeddedFieldDefinition,
    ParameterTypeOptions,
    RelationFieldDefinition,
    RelationToDocument,
    RelationToEntity,
    RelationToGeneric,
    RelationToTypeVar,
)
from pangloss_models.initialise_models.initialise_create_db_model import (
    build_generic_create_db_model_from_type_option,
)
from pangloss_models.model_bases.base_models import (
    _DeclaredClass,
    _UpdateDBBase,
)
from pangloss_models.model_bases.conjunction import (
    Conjunction,
    _ConjunctionUpdateDBBase,
)
from pangloss_models.model_bases.document import (
    Document,
    _DocumentUpdateDBBase,
)
from pangloss_models.model_bases.embedded import (
    Embedded,
    _EmbeddedUpdateDBBAse,
)
from pangloss_models.model_bases.entity import (
    Entity,
    _EntityUpdateDBBase,
)
from pangloss_models.model_bases.reified_relation import (
    ReifiedRelation,
    ReifiedRelationDocument,
    _ReifiedRelationDocumentUpdateDBBase,
    _ReifiedRelationUpdateDBBase,
)
from pangloss_models.model_bases.semantic_space import (
    SemanticSpace,
    _SemanticSpaceUpdateDBBase,
)
from pangloss_models.utils import map_validators_to_kwargs


def build_id_field_on_update_db_model(model) -> None:
    assert model.UpdateDB
    if getattr(model._meta, "create_with_id", False):
        annotation = UUID | None
        if getattr(model._meta, "accept_url_as_id", False):
            annotation = UUID | AnyHttpUrl | None
        model.UpdateDB.model_fields["id"] = FieldInfo(
            annotation=annotation,  # type: ignore
            default=None,  # type: ignore
        )
        model.UpdateDB.model_fields["create_new"] = FieldInfo(
            annotation=Literal[True] | None,  # ty: ignore # type: ignore
            default=None,  # pyright: ignore[reportArgumentType]
        )
        model.UpdateDB.model_rebuild()


def build_label_field_on_update_db_model(
    model: type[
        Document
        | Embedded
        | Entity
        | ReifiedRelation
        | ReifiedRelationDocument
        | Conjunction
        | SemanticSpace
    ],
):
    assert model.UpdateDB

    if getattr(model._meta, "require_label", True):
        model.UpdateDB.model_fields["label"] = FieldInfo(annotation=str)


def unpack_generic_fields(
    model: type[Document | Entity | ReifiedRelation],
) -> dict[str, TypeVar | type[list[TypeVar]]]:
    generic_fields = {}
    for f, fi in model.model_fields.items():
        if isinstance(fi.annotation, TypeVar):
            generic_fields[f] = fi.annotation

    return generic_fields


def can_have_update_db_model(model: type[_DeclaredClass]) -> bool:
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


def get_update_db_base_model_type(
    model: type[
        Document
        | Embedded
        | Entity
        | ReifiedRelation
        | ReifiedRelationDocument
        | Conjunction
        | SemanticSpace
    ],
) -> type[_UpdateDBBase] | None:
    if issubclass(model, Document):
        return _DocumentUpdateDBBase
    elif issubclass(model, Entity):
        return _EntityUpdateDBBase
    elif issubclass(model, ReifiedRelation):
        return _ReifiedRelationUpdateDBBase
    elif issubclass(model, ReifiedRelationDocument):
        return _ReifiedRelationDocumentUpdateDBBase
    elif issubclass(model, Conjunction):
        return _ConjunctionUpdateDBBase
    elif issubclass(model, SemanticSpace):
        return _SemanticSpaceUpdateDBBase
    elif issubclass(model, Embedded):
        return _EmbeddedUpdateDBBAse
    return None


def initialise_update_db_model(
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

    if not can_have_update_db_model(model):
        return

    # Checks if Create model has already been created; do not duplicate as we depend
    # on model reference!
    if "UpdateDB" in model.__dict__:
        return

    # Extracts from the _DeclaredClass definition the annotation for .CreateDB
    update_db_base_type = get_update_db_base_model_type(model)
    if not update_db_base_type:
        return

    model.UpdateDB = pydantic_create_model(  # ty:ignore[invalid-assignment]
        f"{model.__name__}UpdateDB",
        __base__=update_db_base_type,
        __module__=model.__module__,
        _owner=(ClassVar[model], model),
        __doc__=model._meta.description if model._meta.description else "",
        __config__=ConfigDict(alias_generator=to_camel),
        type=(Literal[model.__name__], model.__name__),  # type: ignore
    )  # pyright: ignore[reportAttributeAccessIssue]

    build_id_field_on_update_db_model(model)
    build_label_field_on_update_db_model(model)

    model.UpdateDB.model_rebuild(force=True)


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


def build_generic_update_db_model_from_type_option(
    type_option: RelationToGeneric,
):
    """Taking a type option, build a Model.CreateDB for each type option with the type options
    bound to the appropriate fields"""

    # Get the generic base type
    generic_relation_type = type_option.base_type

    # Assure that Create is initalised on this model
    initialise_update_db_model(generic_relation_type)

    # Add the non-TypeVar fields to the base model
    add_fields_to_update_db_model(generic_relation_type)

    # Rebuild
    generic_relation_type.UpdateDB.model_rebuild(force=True)

    # We need to name our class with the bound fields, in the form Generic[type_names],
    # so extract the type names (recursing down)
    type_names = recursively_get_generic_naming(type_option.parameter_type_options)

    # Create a bound model
    bound_update_db_model = pydantic_create_model(
        f"{generic_relation_type.__name__}[{type_names}]UpdateDB",
        __base__=generic_relation_type.UpdateDB,
        __module__=generic_relation_type.__module__,
        _owner=(ClassVar[generic_relation_type], generic_relation_type),
        __config__=ConfigDict(alias_generator=to_camel),
        type=(Literal[generic_relation_type.__name__], generic_relation_type.__name__),  # ty:ignore[invalid-type-form]
    )

    # For some reason, we need to manually add all the fields from the Generic unbound type
    # (you would have thought inheriting as __base__ above would have done this, but no)
    for field_name, field_info in generic_relation_type.UpdateDB.model_fields.items():
        bound_update_db_model.model_fields[field_name] = field_info

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
                                    to.annotated_type.CreateDB.apply_edge_model(
                                        to.edge_model
                                    )
                                )

                        else:
                            # ... otherwise, just add the annotated_type.ReferenceSet
                            annotations.append(to.annotated_type.ReferenceSet)

                            if to.annotated_type._meta.create_inline:
                                initialise_update_db_model(to.annotated_type)
                                annotations.append(to.annotated_type.CreateDB)

                    # If relation to Document...
                    elif isinstance(to, RelationToDocument):
                        # Add edge to Document.UpdateDB and use
                        initialise_update_db_model(to.annotated_type)
                        if to.edge_model:
                            annotations.append(
                                to.annotated_type.UpdateDB.apply_edge_model(
                                    to.edge_model
                                )
                            )
                            annotations.append(
                                to.annotated_type.CreateDB.apply_edge_model(
                                    to.edge_model
                                )
                            )

                        else:
                            # Add or use Document.UpdateDB
                            annotations.append(to.annotated_type.UpdateDB)
                            annotations.append(to.annotated_type.CreateDB)

                    # Otherwise, if it is anything that can be generic,
                    # pass the type option back to the this function to get the
                    # internal bound generic at the next level
                    elif isinstance(to, RelationToGeneric):
                        if to.edge_model:
                            annotations.append(
                                build_generic_update_db_model_from_type_option(
                                    to
                                ).apply_edge_model(to.edge_model)
                            )
                            annotations.append(
                                build_generic_create_db_model_from_type_option(
                                    to
                                ).apply_edge_model(to.edge_model)
                            )
                        annotations.append(
                            build_generic_update_db_model_from_type_option(to)
                        )
                        annotations.append(
                            build_generic_create_db_model_from_type_option(to)
                        )
            if isinstance(generic_type_option, RelationToEntity):
                # ... if there is an edge model, add the applied_edge_model
                # version of annotated_type.ReferenceSet to annotation
                initialise_update_db_model(generic_type_option.annotated_type)
                if generic_type_option.edge_model:
                    annotations.append(
                        generic_type_option.annotated_type.ReferenceSet.apply_edge_model(
                            generic_type_option.edge_model
                        )
                    )
                    if generic_type_option.annotated_type._meta.create_inline:
                        annotations.append(
                            generic_type_option.annotated_type.CreateDB.apply_edge_model(
                                generic_type_option.edge_model
                            )
                        )

                else:
                    initialise_update_db_model(generic_type_option.annotated_type)
                    # ... otherwise, just add the annotated_type.ReferenceSet
                    annotations.append(generic_type_option.annotated_type.ReferenceSet)
                    if generic_type_option.annotated_type._meta.create_inline:
                        annotations.append(generic_type_option.annotated_type.CreateDB)

            # If relation to Document...
            elif isinstance(generic_type_option, RelationToDocument):
                initialise_update_db_model(generic_type_option.annotated_type)
                # Add edge to Document.CreateDB and use
                if generic_type_option.edge_model:
                    annotations.append(
                        generic_type_option.annotated_type.UpdateDB.apply_edge_model(
                            generic_type_option.edge_model
                        )
                    )
                    annotations.append(
                        generic_type_option.annotated_type.CreateDB.apply_edge_model(
                            generic_type_option.edge_model
                        )
                    )

                else:
                    # Add or use Document.CreateDB
                    annotations.append(generic_type_option.annotated_type.UpdateDB)
                    annotations.append(generic_type_option.annotated_type.CreateDB)

        if field_definition.wrapper:
            annotation = field_definition.wrapper[  # type: ignore
                Annotated[Union[*annotations], Field()]  # ty:ignore[invalid-type-form]
            ]
        else:
            annotation = Union[*annotations]  # ty:ignore[invalid-type-form]

        bound_update_db_model.model_fields[field_name] = FieldInfo(
            annotation=annotation,  # type: ignore
            validation_alias=to_camel(field_name),
            metadata=field_definition.validators,  # type: ignore
            # discriminator="type" if not field_definition.wrapper else None,
            description=field_definition.description,
        )

        bound_update_db_model.model_rebuild(force=True)

    return bound_update_db_model


def get_relation_annotation_types(
    field_definition: RelationFieldDefinition,
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
                    types.append(type_option.annotated_type.CreateDB)

        elif isinstance(type_option, RelationToDocument):
            initialise_update_db_model(type_option.annotated_type)
            if type_option.edge_model:
                types.append(
                    type_option.annotated_type.UpdateDB.apply_edge_model(
                        type_option.edge_model
                    )
                )
                types.append(
                    type_option.annotated_type.CreateDB.apply_edge_model(
                        type_option.edge_model
                    )
                )

            else:
                types.append(type_option.annotated_type.UpdateDB)
                types.append(type_option.annotated_type.CreateDB)

        elif isinstance(
            type_option,
            (RelationToGeneric),
        ):
            bound_reified_update_type = build_generic_update_db_model_from_type_option(
                type_option
            )

            bound_reified_create_type = build_generic_create_db_model_from_type_option(
                type_option
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
        types.append(type_option.annotated_type.UpdateDB)
        types.append(type_option.annotated_type.CreateDB)

    return Union[*types]  # type: ignore


def add_fields_to_update_db_model(
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
    if not can_have_update_db_model(model):
        return

    # Literal fields
    for field_name, field_definition in model._meta.fields.literal_fields.items():
        model.UpdateDB.model_fields[field_name] = FieldInfo(
            annotation=field_definition.annotated_type,
            validation_alias=to_camel(field_name),
            **map_validators_to_kwargs(field_definition.validators),
        )

    # Embedded fields
    for field_name, field_definition in model._meta.fields.embedded_fields.items():
        annotation = get_embedded_annotation_types(field_definition)

        if annotation:
            model.UpdateDB.model_fields[field_name] = FieldInfo(
                annotation=annotation,  # type: ignore
                validation_alias=to_camel(field_name),
            )

    # Relation fields
    for field_name, field_definition in model._meta.fields.relation_fields.items():
        optional = (
            field_definition.field_required_to_fulfil
            and not field_definition.subclasses_parent_fields
        )

        annotation = get_relation_annotation_types(field_definition)

        if annotation:
            model.UpdateDB.model_fields[field_name] = FieldInfo(
                annotation=(annotation | None) if optional else annotation,  # type: ignore
                validation_alias=to_camel(field_name),
                # discriminator="type" if not field_definition.wrapper else None,
                **map_validators_to_kwargs(field_definition.validators),
            )

            if optional:
                model.UpdateDB.model_fields[field_name].default = None

    # Annotated values
    for (
        field_name,
        field_definition,
    ) in model._meta.fields.annotated_value_fields.items():
        model.UpdateDB.model_fields[field_name] = FieldInfo(
            annotation=field_definition.annotated_type,
        )

    model.UpdateDB.model_rebuild(force=True)
