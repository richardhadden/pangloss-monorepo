"""InterfaceConfig: the links of the navigation bar, merged over the installed apps"""

import sys

import pytest
from pangloss_interface.config import (
    InterfaceConfig,
    NavLink,
    NavModel,
    load_configs,
    merge,
)
from pangloss_models.exceptions import PanglossMetaError


def test_without_any_config_the_bar_is_as_it_was():
    assert merge([]) == {
        "sections": ["Entities", "Documents"],
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
    assert nav["sections"] == ["Entities", "Documents", "Maps", "Sources"]


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
