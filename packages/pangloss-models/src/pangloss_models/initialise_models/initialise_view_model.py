"""`View`: a document, an entity or something nested, as it is read.

The models are made by `builder.py`, from the description of this kind in `kinds.py`."""

from pangloss_models.field_definitions import RelationFieldDefinition
from pangloss_models.initialise_models.builder import (
    add_fields,
    initialise_model,
    relation_annotation,
)
from pangloss_models.initialise_models.common import (
    can_have_action_models,
    recursively_get_generic_naming,  # noqa: F401 (the name of a generic model; tested here)
)
from pangloss_models.initialise_models.kinds import VIEW

can_have_view_model = can_have_action_models


def initialise_view_model(model) -> None:
    initialise_model(VIEW, model)


def add_fields_to_view_model(model, fields_to_bind: frozenset) -> None:
    add_fields(VIEW, model, fields_to_bind)


def get_relation_annotation_types(
    field_definition: RelationFieldDefinition, field_bindings=()
):
    """What may be read for a relation (used by the head view for what points at an entity)"""
    return relation_annotation(VIEW, field_definition, frozenset(field_bindings))
