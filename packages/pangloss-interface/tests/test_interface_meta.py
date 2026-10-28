from typing import no_type_check

import pytest
from pangloss_interface import InterfaceMeta
from pangloss_interface.meta import export_definitions
from pangloss_core import settings as core_settings
from pangloss_core.settings import ClientSettings
from pangloss_models import initialise
from pangloss_models.exceptions import PanglossMetaError
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.semantic_space import SemanticSpace
from pangloss_models.model_registry import ModelRegistry


@pytest.fixture
def clear_registry():
    # (models are initialised with a database module that needs no database, as in
    # test_models_match_typescript)
    saved = core_settings.__dict__.get("SETTINGS")
    ClientSettings(INSTALLED_APPS=[], DATABASE_MODULE="pangloss_sdk.databases.api")
    ModelRegistry._reset()
    yield
    ModelRegistry._reset()
    if saved is None:
        core_settings.__dict__.pop("SETTINGS", None)
    else:
        core_settings.SETTINGS = saved


def test_a_colour_has_to_be_a_tailwind_colour_but_not_black_or_white():
    assert InterfaceMeta(colour="rose").colour == "rose"
    assert InterfaceMeta().colour is None
    for wrong in ("black", "white", "pink-500", "#fff"):
        with pytest.raises(PanglossMetaError):
            InterfaceMeta(colour=wrong)  # ty: ignore[invalid-argument-type]


@no_type_check
def test_the_colour_of_a_model_is_inherited_and_exported(clear_registry):
    class Person(Entity):
        _interface_meta = InterfaceMeta(colour="indigo")

    class Poet(Person):
        pass

    class Place(Entity):
        pass

    class Negative[T](SemanticSpace[T]):
        _interface_meta = InterfaceMeta(colour="rose")

    initialise()
    models = export_definitions()["models"]
    assert models["Person"]["interfaceMeta"] == {"colour": "indigo"}
    assert models["Poet"]["interfaceMeta"] == {"colour": "indigo"}
    assert models["Place"]["interfaceMeta"] is None
    assert models["Negative"]["interfaceMeta"] == {"colour": "rose"}
