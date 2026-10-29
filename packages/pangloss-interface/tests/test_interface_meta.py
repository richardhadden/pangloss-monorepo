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


def none(**given):
    """The exported meta with only what is given set"""
    return {
        "colour": None,
        "listPage": None,
        "itemPage": None,
        "viewCard": None,
        "editCard": None,
        **given,
    }


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
    assert models["Person"]["interfaceMeta"] == none(colour="indigo")
    assert models["Poet"]["interfaceMeta"] == none(colour="indigo")
    assert models["Place"]["interfaceMeta"] is None
    assert models["Negative"]["interfaceMeta"] == none(colour="rose")


def test_a_component_is_named_app_colon_name_or_false():
    meta = InterfaceMeta(item_page="my_app:ItemPage", view_card=False)
    assert meta.item_page == "my_app:ItemPage" and meta.view_card is False
    for wrong in ("ItemPage", "my_app:", ":Page", "a:b:c", "my-app:Page", 3):
        with pytest.raises(PanglossMetaError):
            InterfaceMeta(list_page=wrong)  # ty: ignore[invalid-argument-type]


@no_type_check
def test_a_child_inherits_each_field_it_does_not_set_and_false_turns_one_off(
    clear_registry,
):
    class Manuscript(Entity):
        _interface_meta = InterfaceMeta(
            colour="amber", item_page="ms:Page", view_card="ms:Card"
        )

    class Codex(Manuscript):
        _interface_meta = InterfaceMeta(colour="red")  # (the page and card stay)

    class Scroll(Manuscript):
        _interface_meta = InterfaceMeta(item_page=False, list_page="ms:Scrolls")

    class Roll(Scroll):
        pass

    class Plain(Entity):
        pass

    initialise()
    models = export_definitions()["models"]
    page = {"module": "ms", "name": "Page"}
    card = {"module": "ms", "name": "Card"}
    assert models["Manuscript"]["interfaceMeta"] == none(
        colour="amber", itemPage=page, viewCard=card
    )
    assert models["Codex"]["interfaceMeta"] == none(
        colour="red", itemPage=page, viewCard=card
    )
    assert models["Scroll"]["interfaceMeta"] == none(
        colour="amber",
        itemPage=None,
        viewCard=card,
        listPage={"module": "ms", "name": "Scrolls"},
    )
    assert models["Roll"]["interfaceMeta"] == models["Scroll"]["interfaceMeta"]
    assert models["Plain"]["interfaceMeta"] is None
