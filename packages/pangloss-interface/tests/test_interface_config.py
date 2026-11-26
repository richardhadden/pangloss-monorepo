"""InterfaceConfig: the links of the navigation bar, merged over the installed apps"""

import sys

import pytest
from pangloss_interface import InterfaceConfig, NavLink, NavModel
from pangloss_interface.config import (
    load_configs,
    merge,
    merge_disabled,
    merge_space_bands,
)
from pangloss_models import PanglossMetaError


def test_without_any_config_the_bar_is_as_it_was():
    assert merge([]) == {
        "sections": ["Documents", "Entities"],
        "models": {},
        "links": [],
    }


def test_sections_come_in_the_order_they_are_met_after_the_two_defaults():
    nav = merge(
        [
            ("a", InterfaceConfig(nav=[NavLink("x", "/x", section="Maps")])),
            (
                "b",
                InterfaceConfig(
                    sections=["Sources"], nav=[NavModel("P", section="Maps")]
                ),
            ),
        ]
    )
    assert nav["sections"] == ["Documents", "Entities", "Maps", "Sources"]


def test_the_later_app_wins_for_a_type_and_can_hide_it():
    nav = merge(
        [
            (
                "library",
                InterfaceConfig(nav=[NavModel("Folio", label="Folios", order=3)]),
            ),
            ("project", InterfaceConfig(nav=[NavModel("Folio", hidden=True)])),
        ]
    )
    assert nav["models"]["Folio"] == {
        "label": None,
        "labelSlot": "nav_project_folio",
        "section": None,
        "order": None,
        "hidden": True,
    }


def test_a_link_is_exported_with_its_keys_and_a_repeat_replaces():
    nav = merge(
        [
            ("a", InterfaceConfig(nav=[NavLink("Chart", "/chart", order=2)])),
            (
                "b",
                InterfaceConfig(
                    nav=[NavLink("Chart", "/chart", order=1, requires_login=True)]
                ),
            ),
        ]
    )
    assert nav["links"] == [
        {
            "label": "Chart",
            "labelSlot": "nav_b_chart",
            "href": "/chart",
            "section": None,
            "order": 1,
            "external": False,
            "requiresLogin": True,
        }
    ]


def test_an_unknown_type_is_refused_naming_the_app():
    config = InterfaceConfig(nav=[NavModel("Nope")])
    with pytest.raises(PanglossMetaError, match="a.interface_config.*Nope"):
        merge([("a", config)], models=["Person"])
    merge([("a", config)], models=["Nope"])


def test_a_citation_is_kept_out_of_the_bar_unless_an_app_places_it():
    assert merge([], models=["Person", "PGCitation"])["models"]["PGCitation"]["hidden"]
    assert "PGCitation" not in merge([], models=["Person"])["models"]
    placed = merge(
        [("a", InterfaceConfig(nav=[NavModel("PGCitation", section="Notes")]))],
        models=["PGCitation"],
    )
    assert placed["models"]["PGCitation"]["hidden"] is False


def test_a_link_inside_the_interface_starts_with_a_slash():
    with pytest.raises(PanglossMetaError):
        NavLink("Chart", "chart")
    assert NavLink("Library", "https://example.org", external=True).external


@pytest.fixture
def app(tmp_path, monkeypatch):
    package = tmp_path / "cfgapp"
    package.mkdir()
    (package / "__init__.py").write_text("")
    monkeypatch.syspath_prepend(str(tmp_path))
    yield package
    for name in [n for n in sys.modules if n.split(".")[0] == "cfgapp"]:
        del sys.modules[name]


def test_an_app_is_read_for_its_interface_config_module(app):
    assert load_configs(["cfgapp", "not_an_app_at_all"]) == []
    (app / "interface_config.py").write_text(
        "from pangloss_interface.config import InterfaceConfig, NavModel\n"
        "config = InterfaceConfig(nav=[NavModel('Person', hidden=True)])\n"
    )
    [(name, config)] = load_configs(["cfgapp"])
    assert name == "cfgapp" and config.nav[0].hidden


def test_a_config_module_without_config_is_refused(app):
    (app / "interface_config.py").write_text("x = 1\n")
    with pytest.raises(PanglossMetaError, match="config = InterfaceConfig"):
        load_configs(["cfgapp"])


def test_a_label_is_a_ui_slot_with_the_label_as_its_default_text():
    from pangloss_interface.config import label_slot, nav_defaults

    assert (
        label_slot("pangloss_manuscripts", "Collation chart")
        == "nav_pangloss_manuscripts_collation_chart"
    )
    configs = [
        (
            "ms",
            InterfaceConfig(
                nav=[
                    NavModel("Folio"),
                    NavModel("Codex", label="Codices"),
                    NavLink("The chart", "/c"),
                ]
            ),
        )
    ]
    assert nav_defaults(configs) == {
        "nav_ms_folio": "Folio",
        "nav_ms_codices": "Codices",
        "nav_ms_the_chart": "The chart",
    }


def test_what_the_apps_disable_is_merged_in_their_order_once_each():
    configs = [
        ("one", InterfaceConfig(disabled=["pangloss_derived:Derived"])),
        ("two", InterfaceConfig()),
        (
            "three",
            InterfaceConfig(
                disabled=["pangloss_dates:ByDate", "pangloss_derived:Derived"]
            ),
        ),
    ]
    assert merge_disabled(configs) == [
        "pangloss_derived:Derived",
        "pangloss_dates:ByDate",
    ]
    assert merge_disabled([]) == []


def test_the_bands_of_kinds_of_space_are_checked():
    config = InterfaceConfig(space_bands={"denies": "cross", "possibility": "none"})
    assert config.space_bands == {"denies": "cross", "possibility": "none"}
    assert InterfaceConfig().space_bands == {}
    with pytest.raises(
        PanglossMetaError,
        match="'doubts' is not a kind of space; the kinds are denies, forbids, prescribes, necessity, "
        "possibility, asserts, plain",
    ):
        InterfaceConfig(space_bands={"doubts": "dots"})  # ty: ignore[invalid-argument-type]
    with pytest.raises(
        PanglossMetaError,
        match="the pattern of a band is one of none, hatch, cross, lines, bars, dots, grid",
    ):
        InterfaceConfig(space_bands={"denies": "stripes"})  # ty: ignore[invalid-argument-type]
    with pytest.raises(PanglossMetaError, match="a dict of kinds of space to patterns"):
        InterfaceConfig(space_bands="dots")  # ty: ignore[invalid-argument-type]


def test_the_bands_of_the_apps_are_merged_the_later_winning_kind_by_kind():
    configs = [
        ("one", InterfaceConfig(space_bands={"denies": "cross", "plain": "dots"})),
        ("two", InterfaceConfig()),
        ("three", InterfaceConfig(space_bands={"denies": "none", "asserts": "grid"})),
    ]
    assert merge_space_bands(configs) == {
        "denies": "none",
        "plain": "dots",
        "asserts": "grid",
    }
    assert merge_space_bands([]) == {}


def test_the_bands_the_apps_give_are_exported(app):
    from pangloss_core import ClientSettings
    from pangloss_core import settings as core_settings
    from pangloss_interface.meta import export_definitions
    from pangloss_models import ModelRegistry, initialise

    (app / "interface_config.py").write_text(
        "from pangloss_interface import InterfaceConfig\n"
        "config = InterfaceConfig(space_bands={'denies': 'cross'})\n"
    )
    saved = core_settings.__dict__.get("SETTINGS")
    ClientSettings(INSTALLED_APPS=["cfgapp"], STORAGE="pangloss_sdk.storage:api")
    ModelRegistry._reset()
    try:
        initialise()
        assert export_definitions()["spaceBands"] == {"denies": "cross"}
    finally:
        ModelRegistry._reset()
        if saved is None:
            core_settings.__dict__.pop("SETTINGS", None)
        else:
            core_settings.SETTINGS = saved
