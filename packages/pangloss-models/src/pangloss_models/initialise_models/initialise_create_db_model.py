"""`CreateDB`: what is written to the database to make a document, an entity, or something nested.

The models are made by `builder.py`, from the description of this kind in `kinds.py`."""

from pangloss_models.initialise_models.builder import add_fields, initialise_model
from pangloss_models.initialise_models.common import (
    can_have_action_models,
    recursively_get_generic_naming,  # noqa: F401 (the name of a generic model; tested here)
)
from pangloss_models.initialise_models.kinds import CREATE_DB

can_have_create_db_model = can_have_action_models


def initialise_create_db_model(model) -> None:
    initialise_model(CREATE_DB, model)


def add_fields_to_create_db_model(model) -> None:
    """(`model` is the declared model; the others take the model that is made)"""
    if can_have_create_db_model(model):
        add_fields(CREATE_DB, model.CreateDB, frozenset())
