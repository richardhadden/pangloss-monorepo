"""Markers of literal fields for the interface: `Slider()`"""

from typing import Annotated, no_type_check

import pytest
from annotated_types import Ge, Le, Lt
from pangloss_core import settings as core_settings
from pangloss_core.settings import ClientSettings
from pangloss_interface import Slider
from pangloss_models import initialise
from pangloss_models.exceptions import PanglossModelError
from pangloss_models.export import export_models
from pangloss_models.model_bases.document import Document
from pangloss_models.model_registry import ModelRegistry


@pytest.fixture(autouse=True)
def clear_registry():
    # (as in test_interface_meta: models initialised with a database module that needs no database)
    saved = core_settings.__dict__.get("SETTINGS")
    ClientSettings(INSTALLED_APPS=[], STORAGE="pangloss_sdk.storage:api")
    ModelRegistry._reset()
    yield
    ModelRegistry._reset()
    if saved is None:
        core_settings.__dict__.pop("SETTINGS", None)
    else:
        core_settings.SETTINGS = saved


def field_of(model: str, name: str) -> dict:
    return next(
        f for f in export_models()["models"][model]["fields"] if f["name"] == name
    )


@no_type_check
def test_a_slider_is_exported_as_a_marker_of_the_field():
    class Reading(Document):
        percent: Annotated[int, Ge(1), Le(100), Slider()]
        weight: Annotated[float, Ge(0), Lt(1), Slider(step=0.05)]
        plain: int

    initialise()
    assert field_of("Reading", "percent")["markers"] == [{"name": "Slider"}]
    assert field_of("Reading", "weight")["markers"] == [
        {"name": "Slider", "step": 0.05}
    ]
    assert field_of("Reading", "plain")["markers"] == []


@no_type_check
def test_a_slider_on_a_field_that_is_not_a_number_is_refused():
    class Reading(Document):
        name: Annotated[str, Slider()]

    initialise()
    with pytest.raises(PanglossModelError, match="only for an int or a float"):
        export_models()


@no_type_check
def test_a_slider_without_both_bounds_is_refused():
    class Reading(Document):
        percent: Annotated[int, Ge(1), Slider()]

    initialise()
    with pytest.raises(PanglossModelError, match="a lower and an upper bound"):
        export_models()
