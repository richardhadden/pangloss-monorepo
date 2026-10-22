"""Which relations point at an entity, for the reverse fields of its `HeadView`.

A relation reaches an entity directly (`about: Person`), through embedded objects, or through
generic wrappers: reified relations (`InRole[Person]`), semantic spaces (`Negative[Person]`) and
conjunctions (`Causes[Person, Place]`), which may hold each other. For each, the entity gets a field
named after the reverse of the document's relation (`about_reverse`)."""

from typing import TYPE_CHECKING, NamedTuple

from frozendict import frozendict

from pangloss_models.field_definitions import (
    EmbeddedFieldDefinition,
    IncomingRelationDefinition,
    ParameterTypeOptions,
    RelationFieldDefinition,
    RelationToConjunction,
    RelationToEntity,
    RelationToReifiedRelation,
    RelationToReifiedRelationDocument,
    RelationToSemanticSpace,
)

if TYPE_CHECKING:
    from pangloss_models.model_bases.base_models import _DeclaredClass

# The relations to a generic wrapper, that has the types it is made for in `parameter_type_options`
RELATIONS_TO_WRAPPERS = (
    RelationToReifiedRelation,
    RelationToReifiedRelationDocument,
    RelationToSemanticSpace,
    RelationToConjunction,
)


def recursive_get_target_of_wrappers(
    parameter_type_dict: frozendict[str, ParameterTypeOptions],
    accumulated_targets: list[type[_DeclaredClass]],
) -> list[type[_DeclaredClass]]:
    """The entities a generic wrapper is made for, through any wrappers inside it"""
    for parameter_type_options in parameter_type_dict.values():
        for type_option in parameter_type_options.type_options:
            if isinstance(type_option, RelationToEntity):
                accumulated_targets.append(type_option.annotated_type)
            elif isinstance(type_option, RELATIONS_TO_WRAPPERS):
                recursive_get_target_of_wrappers(
                    type_option.parameter_type_options, accumulated_targets
                )

    return accumulated_targets


def entities_reached(relation_field_definition: RelationFieldDefinition) -> list[tuple[type, bool]]:
    """The entities that a relation field leads to, and whether through a wrapper"""
    reached: list[tuple[type, bool]] = []
    for type_option in relation_field_definition.type_options:
        if isinstance(type_option, RelationToEntity):
            reached.append((type_option.annotated_type, False))
        elif isinstance(type_option, RELATIONS_TO_WRAPPERS):
            for target in recursive_get_target_of_wrappers(type_option.parameter_type_options, []):
                reached.append((target, True))
    return reached


def initialise_incoming_relation_definitions(model: type[_DeclaredClass]):

    for relation_field_definition in model._meta.fields.relation_fields.values():
        for target_type, via_wrapper in entities_reached(relation_field_definition):
            target_type._meta.field_definitions.incoming_fields[
                relation_field_definition.reverse_name
            ].append(
                IncomingRelationDefinition(
                    field_definition=relation_field_definition,
                    source=model,
                    via_reified=via_wrapper,
                )
            )

    for embedded_field_definition in model._meta.fields.embedded_fields.values():
        for incoming_def in recurse_embedded_for_incoming(embedded_field_definition, []):
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
    for embedded_option in embedded_field_definition.type_options:
        for relation_field_definition in embedded_option.annotated_type._meta.fields.relation_fields.values():
            for target_type, via_wrapper in entities_reached(relation_field_definition):
                accumulated_targets.append(
                    IncomingRelationTargetDef(target_type, relation_field_definition, via_wrapper)
                )

    for embedded_type_option in embedded_field_definition.type_options:
        for nested_embedded in embedded_type_option.annotated_type._meta.fields.embedded_fields.values():
            recurse_embedded_for_incoming(nested_embedded, accumulated_targets)

    return accumulated_targets
