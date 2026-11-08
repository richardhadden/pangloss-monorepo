from pangloss_interface.meta import InterfaceMeta
from pangloss_interface.modules import InterfaceModule, declared_names, keys_of

MODULE = """
import { defineModule } from "pangloss-interface-core";

export default defineModule({
  name: "dates",
  components: {
    DateCard: () => import("./components/DateCard"),
    "Date Editor": () => import("./components/DateEditor"),
    Plain: Plain,
    Method() { return 1 },
  },
  routes: [{ path: "/dates", component: "DateCard" }],
  collapseRules: { byDate: (item) => item.a, },
});
"""


def test_the_components_of_a_module_are_read_from_its_source():
    assert keys_of(MODULE, "components") == [
        "DateCard",
        "Date Editor",
        "Plain",
        "Method",
    ]


def test_a_block_that_is_not_there_has_no_keys():
    assert keys_of(MODULE, "itemSections") == []


def test_the_collapse_rules_are_read_the_same_way():
    assert keys_of(MODULE, "collapseRules") == ["byDate"]


def test_names_are_those_an_interface_option_takes(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "index.ts").write_text(MODULE)
    (tmp_path / "src" / "helper.ts").write_text("export const x = 1;")
    module = InterfaceModule("dates_app", tmp_path)

    assert declared_names(module, "components")[:2] == [
        "dates_app:DateCard",
        "dates_app:Date Editor",
    ]
    assert declared_names(module, "collapseRules") == ["dates_app:byDate"]


def test_only_the_options_that_take_a_component_or_rule_have_choices():
    assert InterfaceMeta.editor_choices("colour") is None
    assert InterfaceMeta.editor_choices("nav_section") is None
