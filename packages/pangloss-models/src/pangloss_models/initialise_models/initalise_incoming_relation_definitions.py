from typing import TYPE_CHECKING, NamedTuple

from frozendict import frozendict

from pangloss_models.field_definitions import (
    EmbeddedFieldDefinition,
    IncomingRelationDefinition,
    ParameterTypeOptions,
    RelationFieldDefinition,
    RelationToEntity,
    RelationToReifiedRelation,
    RelationToReifiedRelationDocument,
)

if TYPE_CHECKING:
    from pangloss_models.model_bases.base_models import _DeclaredClass


def recursive_get_target_of_reified(
    parameter_type_dict: frozendict[str, ParameterTypeOptions],
    accumulated_targets: list[type[_DeclaredClass]],
) -> list[type[_DeclaredClass]]:
    for type_param_string, parameter_type_options in parameter_type_dict.items():
        for type_option in parameter_type_options.type_options:
            match type_option:
                case RelationToEntity(annotated_type=target_type):
                    accumulated_targets.append(target_type)
                case (
                    RelationToReifiedRelation(
                        parameter_type_options=parameter_type_options
                    )
                    | RelationToReifiedRelationDocument(
                        parameter_type_options=parameter_type_options
                    )
                ):
                    recursive_get_target_of_reified(
                        parameter_type_options, accumulated_targets
                    )

    return accumulated_targets


def initialise_incoming_relation_definitions(model: type[_DeclaredClass]):

    for relation_field_definition in model._meta.fields.relation_fields.values():
        for type_option in relation_field_definition.type_options:
            match type_option:
                case RelationToEntity(annotated_type=target_type):
                    target_type._meta.field_definitions.incoming_fields[
                        relation_field_definition.reverse_name
                    ].append(
                        IncomingRelationDefinition(
                            field_definition=relation_field_definition,
                            source=model,
                            via_reified=False,
                        )
                    )
                case (
                    RelationToReifiedRelation(
                        parameter_type_options=parameter_type_options
                    )
                    | RelationToReifiedRelationDocument(
                        parameter_type_options=parameter_type_options
                    )
                ):
                    for target_type in recursive_get_target_of_reified(
                        parameter_type_options, []
                    ):
                        target_type._meta.field_definitions.incoming_fields[
                            relation_field_definition.reverse_name
                        ].append(
                            IncomingRelationDefinition(
                                field_definition=relation_field_definition,
                                source=model,
                                via_reified=True,
                            )
                        )
    for embedded_field_definition in model._meta.fields.embedded_fields.values():
        for incoming_def in recurse_embedded_for_incoming(
            embedded_field_definition, []
        ):
            incoming_def.target._meta.field_definitions.incoming_fields[
                incoming_def.field_definition.reverse_name
            ].append(
                IncomingRelationDefinition(
                    field_definition=incoming_def.field_definition,
                    source=model,
                    via_reified=incoming_def.relation_via_reified,
                )
            )


class IncomingRelationTargetDef(NamedTuple):
    target: type[_DeclaredClass]
    field_definition: RelationFieldDefinition
    relation_via_reified: bool


def recurse_embedded_for_incoming(
    embedded_field_definition: EmbeddedFieldDefinition,
    accumulated_targets: list[IncomingRelationTargetDef],
):
    for type_option in embedded_field_definition.type_options:
        for (
            relation_field_definition
        ) in type_option.annotated_type._meta.fields.relation_fields.values():
            for type_option in relation_field_definition.type_options:
                match type_option:
                    case RelationToEntity():
                        accumulated_targets.append(
                            IncomingRelationTargetDef(
                                type_option.annotated_type,
                                relation_field_definition,
                                False,
                            )
                        )
                    case (
                        RelationToReifiedRelation(
                            parameter_type_options=parameter_type_options
                        )
                        | RelationToReifiedRelationDocument(
                            parameter_type_options=parameter_type_options
                        )
                    ):
                        for target_type in recursive_get_target_of_reified(
                            parameter_type_options, []
                        ):
                            accumulated_targets.append(
                                IncomingRelationTargetDef(
                                    target_type,
                                    relation_field_definition,
                                    True,
                                )
                            )

    for (
        nested_embedded
    ) in embedded_field_definition.annotated_type._meta.fields.embedded_fields.values():
        recurse_embedded_for_incoming(nested_embedded, accumulated_targets)

    return accumulated_targets
