"""`Update`: what a client sends to replace a document or an entity, with whatever is nested in it.

The models are made by `builder.py`, from the description of this kind in `kinds.py`."""

from pangloss_models.initialise_models.builder import add_fields, initialise_model
from pangloss_models.initialise_models.common import (
    can_have_action_models,
    recursively_get_generic_naming,  # noqa: F401 (the name of a generic model; tested here)
)
from pangloss_models.initialise_models.kinds import UPDATE

can_have_update_model = can_have_action_models


def initialise_update_model(model) -> None:
    initialise_model(UPDATE, model)


def add_fields_to_update_model(model, fields_to_bind: frozenset) -> None:
    add_fields(UPDATE, model, fields_to_bind)
