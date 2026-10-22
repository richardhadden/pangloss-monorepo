"""`UpdateDB`: what is written to the database to replace a document or an entity.

The models are made by `builder.py`, from the description of this kind in `kinds.py`."""

from pangloss_models.initialise_models.builder import add_fields, initialise_model
from pangloss_models.initialise_models.common import (
    can_have_action_models,
    recursively_get_generic_naming,  # noqa: F401 (the name of a generic model; tested here)
)
from pangloss_models.initialise_models.kinds import UPDATE_DB

can_have_update_db_model = can_have_action_models


def initialise_update_db_model(model) -> None:
    initialise_model(UPDATE_DB, model)


def add_fields_to_update_db_model(model) -> None:
    """(`model` is the declared model; the others take the model that is made)"""
    if can_have_update_db_model(model):
        add_fields(UPDATE_DB, model.UpdateDB, frozenset())
