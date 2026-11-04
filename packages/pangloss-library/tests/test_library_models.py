"""The library's models: alternatives weighted by how likely each is"""

from uuid import uuid7

import pytest
from pangloss_core import settings as core_settings
from pangloss_core.settings import ClientSettings
from pangloss_models import initialise
from pangloss_models.export import export_models
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_registry import ModelRegistry
from pydantic import ValidationError


@pytest.fixture(autouse=True)
def clear_registry():
    # (models initialised with a database module that needs no database)
    saved = core_settings.__dict__.get("SETTINGS")
    ClientSettings(INSTALLED_APPS=[], STORAGE="pangloss_sdk.storage:api")
    ModelRegistry._reset()
    yield
    ModelRegistry._reset()
    if saved is None:
        core_settings.__dict__.pop("SETTINGS", None)
    else:
        core_settings.SETTINGS = saved


def make_models():
    # (imported here: the registry was reset, and a module is only run once)
    import importlib

    import pangloss_library.models

    importlib.reload(pangloss_library.models)
    WeightedAlternative = pangloss_library.models.WeightedAlternative

    class Person(Entity):
        pass

    class Statement(Document):
        suspect: WeightedAlternative[Person]  # ty: ignore[invalid-type-form]

    initialise()
    return Statement


def suspects(*percents: int) -> dict:
    return {
        "type": "WeightedAlternative",
        "alternatives": [
            {"type": "Person", "id": uuid7(), "edge_properties": {"percent": n}}
            for n in percents
        ],
    }


def test_a_weighted_alternative_adds_up_to_100():
    Statement = make_models()
    Statement.Create(label="S", suspect=suspects(70, 30))
    with pytest.raises(ValidationError, match="add up to 90, not 100"):
        Statement.Create(label="S", suspect=suspects(60, 30))
    with pytest.raises(ValidationError, match="greater than or equal to 1"):
        Statement.Create(label="S", suspect=suspects(100, 0))
    # (at least one alternative)
    with pytest.raises(ValidationError, match="at least 1 item"):
        Statement.Create(label="S", suspect=suspects())


def test_the_percentages_are_edited_with_sliders():
    make_models()
    models = export_models()["models"]
    (percent,) = models["Likelihood"]["fields"]
    assert percent["markers"] == [{"name": "Slider", "unit": "%"}]
    (alternatives,) = models["WeightedAlternative"]["fields"]
    assert {"name": "SumsTo", "field": "percent", "total": 100} in alternatives[
        "validators"
    ]
    assert alternatives["options"][0]["edgeModel"] == "Likelihood"
