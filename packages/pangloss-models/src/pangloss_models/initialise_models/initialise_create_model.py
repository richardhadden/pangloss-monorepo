"""`Create`: what a client sends to make a document, an entity, or something nested in one.

The models are made by `builder.py`, from the description of this kind in `kinds.py`."""

from pangloss_models.initialise_models.builder import add_fields, initialise_model
from pangloss_models.initialise_models.common import (
    can_have_action_models,
    recursively_get_generic_naming,  # noqa: F401 (the name of a generic model; tested here)
)
from pangloss_models.initialise_models.kinds import CREATE

can_have_create_model = can_have_action_models


def initialise_create_model(model) -> None:
    initialise_model(CREATE, model)


def add_fields_to_create_model(model, fields_to_bind: frozenset) -> None:
    add_fields(CREATE, model, fields_to_bind)
