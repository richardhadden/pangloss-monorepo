from typing import no_type_check

import pytest
from pangloss_interface import Collapse, InterfaceMeta
from pangloss_interface.meta import export_definitions
from pangloss_core import settings as core_settings
from pangloss_core.settings import ClientSettings
from pangloss_models import initialise
from pangloss_models.exceptions import PanglossMetaError
from pangloss_models.model_bases.conjunction import Conjunction
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.reified_relation import ReifiedRelation
from pangloss_models.model_bases.semantic_space import SemanticSpace
from pangloss_models.model_registry import ModelRegistry


def none(**given):
    """The exported meta with only what is given set"""
    return {
        "colour": None,
        "navSection": None,
        "listPage": None,
        "itemPage": None,
        "viewCard": None,
        "editCard": None,
        "collapse": None,
        "headless": None,
        "hideOnForms": None,
        **given,
    }


@pytest.fixture
def clear_registry():
    # (models are initialised with a database module that needs no database, as in
    # test_models_match_typescript)
    saved = core_settings.__dict__.get("SETTINGS")
    ClientSettings(INSTALLED_APPS=[], STORAGE="pangloss_sdk.storage:api")
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


@no_type_check
def test_the_nav_section_of_a_model_is_inherited_and_exported(clear_registry):
    class Vocabulary(Entity):
        _interface_meta = InterfaceMeta(nav_section="Vocabularies")

    class Colours(Vocabulary):
        pass

    class Place(Entity):
        pass

    initialise()
    models = export_definitions()["models"]
    assert models["Vocabulary"]["interfaceMeta"] == none(navSection="Vocabularies")
    assert models["Colours"]["interfaceMeta"] == none(navSection="Vocabularies")
    assert models["Place"]["interfaceMeta"] is None


def test_a_nav_section_cannot_be_empty():
    with pytest.raises(PanglossMetaError, match="nav_section"):
        InterfaceMeta(nav_section="  ")


def test_collapse_is_true_false_or_a_rule_named_app_colon_name():
    assert InterfaceMeta(collapse=True).collapse is True
    assert InterfaceMeta(collapse="my_app:oneLikely").collapse == "my_app:oneLikely"
    for wrong in ("oneLikely", "my_app:", "a:b:c", 3):
        with pytest.raises(PanglossMetaError, match="collapse"):
            InterfaceMeta(collapse=wrong)  # ty: ignore[invalid-argument-type]


@no_type_check
def test_collapse_is_inherited_exported_and_false_turns_it_off(clear_registry):
    class Person(Entity):
        pass

    class Alternative[T](Conjunction):
        _interface_meta = InterfaceMeta(collapse=True)

        alternatives: list[T]

    class Identification[T](ReifiedRelation[T]):
        _interface_meta = InterfaceMeta(collapse="my_app:oneLikely")

        identified_by: str

    class CloseIdentification[T](Identification[T]):
        pass

    class LooseIdentification[T](Identification[T]):
        _interface_meta = InterfaceMeta(collapse=False)

    class Statement(Entity):
        about: Identification[Alternative[Person]]
        close: CloseIdentification[Person]
        loose: LooseIdentification[Person]

    initialise()
    models = export_definitions()["models"]
    rule = {"module": "my_app", "name": "oneLikely"}
    assert models["Alternative"]["interfaceMeta"] == none(collapse=True)
    assert models["Identification"]["interfaceMeta"] == none(collapse=rule)
    assert models["CloseIdentification"]["interfaceMeta"] == none(collapse=rule)
    assert models["LooseIdentification"]["interfaceMeta"] == none(collapse=None)


@no_type_check
def test_only_a_reified_relation_or_a_conjunction_can_collapse(clear_registry):
    class Person(Entity):
        _interface_meta = InterfaceMeta(collapse=True)

    initialise()
    with pytest.raises(PanglossMetaError, match="Person.*collapse"):
        export_definitions()


def test_collapse_conditions_are_field_names_and_values():
    rule = Collapse(blocking=["certainty"], hidden=("note",), when={"role": "author"})
    assert rule.blocking == ("certainty",) and rule.hidden == ("note",)
    # (a single value is a list of one)
    assert rule.when == {"role": ("author",)}
    assert InterfaceMeta(collapse=rule).collapse is rule
    for wrong in (
        {"blocking": ["two words"]},
        {"hidden": "note"},
        {"when": {"role": []}},
        {"when": {"role": [object()]}},
    ):
        with pytest.raises(PanglossMetaError, match="Collapse"):
            Collapse(**wrong)  # ty: ignore[invalid-argument-type]


@no_type_check
def test_collapse_conditions_are_exported_by_key_and_enum_values_by_value(
    clear_registry,
):
    from enum import Enum

    class Person(Entity):
        pass

    class Kind(Enum):
        AUTHOR = "author"
        SCRIBE = "scribe"

    class InRole[T](ReifiedRelation[T]):
        _interface_meta = InterfaceMeta(
            collapse=Collapse(
                blocking=["sure_of_it"],
                hidden=["long_note"],
                when={"kind": [Kind.AUTHOR, "scribe"], "level": 3},
            )
        )

        kind: Kind
        sure_of_it: str | None = None
        long_note: str | None = None
        level: int | None = None

    class Statement(Entity):
        by: InRole[Person]

    initialise()
    models = export_definitions()["models"]
    assert models["InRole"]["interfaceMeta"]["collapse"] == {
        "blocking": ["sureOfIt"],
        "hidden": ["longNote"],
        "when": {"kind": ["author", "scribe"], "level": [3]},
    }


@no_type_check
def test_collapse_conditions_name_fields_the_model_has_but_not_what_it_holds(
    clear_registry,
):
    class Person(Entity):
        pass

    class Identification[T](ReifiedRelation[T]):
        _interface_meta = InterfaceMeta(collapse=Collapse(hidden=["identifed_by"]))

        identified_by: str

    class Statement(Entity):
        by: Identification[Person]

    initialise()
    with pytest.raises(PanglossMetaError, match="Identification.*identifed_by"):
        export_definitions()


@no_type_check
def test_collapse_conditions_cannot_name_the_field_that_is_held(clear_registry):
    class Person(Entity):
        pass

    class Alternative[T](Conjunction):
        _interface_meta = InterfaceMeta(collapse=Collapse(blocking=["alternatives"]))

        alternatives: list[T]

    class Statement(Entity):
        by: Alternative[Person]

    initialise()
    with pytest.raises(PanglossMetaError, match="Alternative.*alternatives"):
        export_definitions()


def test_headless_is_true_or_false():
    assert InterfaceMeta(headless=True).headless is True
    with pytest.raises(PanglossMetaError, match="headless"):
        InterfaceMeta(headless="yes")  # ty: ignore[invalid-argument-type]


@no_type_check
def test_headless_is_inherited_exported_and_false_turns_it_off(clear_registry):
    class Source(Entity):
        pass

    class AtPage[T](ReifiedRelation[T]):
        _interface_meta = InterfaceMeta(headless=True)

        page: str

    class AtFolio[T](AtPage[T]):
        pass

    class AtLine[T](AtPage[T]):
        _interface_meta = InterfaceMeta(headless=False)

    class Statement(Entity):
        page: AtPage[Source]
        folio: AtFolio[Source]
        line: AtLine[Source]

    initialise()
    models = export_definitions()["models"]
    assert models["AtPage"]["interfaceMeta"] == none(headless=True)
    assert models["AtFolio"]["interfaceMeta"] == none(headless=True)
    assert models["AtLine"]["interfaceMeta"] == none()


@no_type_check
def test_only_a_reified_relation_can_be_headless(clear_registry):
    class Person(Entity):
        _interface_meta = InterfaceMeta(headless=True)

    initialise()
    with pytest.raises(PanglossMetaError, match="Person.*headless"):
        export_definitions()


def test_a_field_something_else_keeps_up_to_date_is_read_only_in_the_models_built_on_it(
    clear_registry,
):
    from pangloss_models.export import export_models
    from pangloss_models.protection import Protection

    class Text(Entity):
        _meta = Entity.Meta(abstract=True)
        _protect_meta = Protection(read_only=("key",))
        key: str | None = None
        note: str | None = None

    class PhysicalObject(Entity):
        pass

    # (protected by its second parent: see test_meta_slots)
    class Book(PhysicalObject, Text):
        pages: int | None = None

    initialise()
    fields = {f["name"]: f for f in export_definitions()["models"]["Book"]["fields"]}

    assert fields["key"]["readOnly"] is True
    assert fields["note"]["readOnly"] is False
    assert fields["pages"]["readOnly"] is False
    # (not a part of the models, which the migrations' snapshots are made from)
    assert all("readOnly" not in f for f in export_models()["models"]["Book"]["fields"])


def test_fields_hidden_on_forms_are_exported_by_key_through_the_parents(
    clear_registry,
):
    class Text(Entity):
        _meta = Entity.Meta(abstract=True)
        _interface_meta = InterfaceMeta(hide_on_forms=("inner_note",))
        inner_note: str | None = None

    class Letter(Text):
        pass

    class Charter(Text):
        # (a function of the class exported: here, of its name)
        _interface_meta = InterfaceMeta(
            hide_on_forms=lambda cls: ("inner_note",) if cls.__name__ == "Copy" else ()
        )

    class Copy(Charter):
        pass

    initialise()
    models = export_definitions()["models"]

    assert models["Letter"]["interfaceMeta"]["hideOnForms"] == ["innerNote"]
    assert models["Charter"]["interfaceMeta"]["hideOnForms"] is None
    assert models["Copy"]["interfaceMeta"]["hideOnForms"] == ["innerNote"]


def test_a_field_hidden_on_forms_must_be_one_of_the_models(clear_registry):
    with pytest.raises(PanglossMetaError, match="hide_on_forms"):
        InterfaceMeta(hide_on_forms="label")  # ty: ignore[invalid-argument-type]

    class Place(Entity):
        _interface_meta = InterfaceMeta(hide_on_forms=("nowhere",))

    initialise()
    with pytest.raises(PanglossMetaError, match="Place.*nowhere"):
        export_definitions()
