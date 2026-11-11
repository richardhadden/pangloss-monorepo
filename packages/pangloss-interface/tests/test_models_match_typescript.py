"""What `export_models()` writes has the shape the interface's TypeScript types say
(`interface-core/src/types/models.ts`). Python makes the data and TypeScript reads it, and
nothing else compares them: a key added on one side only is a type error in `pangloss interface
check`, or a value the interface never reads. Every kind of model and field is in the kitchen-sink
models of `pangloss-models`' tests."""

import re
import sys
from pathlib import Path

import pangloss_interface
import pytest
from pangloss_core import ClientSettings
from pangloss_core import settings as core_settings
from pangloss_models import ModelRegistry, initialise
from pangloss_interface import COLOURS
from pangloss_interface.meta import export_definitions

MODELS_TS = (
    Path(pangloss_interface.__file__).parent / "js/interface-core/src/types/models.ts"
)
SUPPORT = Path(__file__).parents[2] / "pangloss-models/tests/support"

FIELD_INTERFACES = {
    "literal": "LiteralField",
    "list": "ListField",
    "typeVar": "TypeVarField",
    "annotatedValue": "AnnotatedValueField",
    "embedded": "EmbeddedField",
    "relation": "RelationField",
    "unknown": "UnknownField",
}


def optional_keys(source: str) -> dict[str, set[str]]:
    """The keys an `export interface` marks optional (`many?: boolean`): the export may leave them out"""
    pattern = re.compile(
        r"export interface (\w+)(?: extends \w+)? \{\n(.*?)\n\}", re.DOTALL
    )
    return {
        name: set(re.findall(r"^  (\w+)\?:", body, re.MULTILINE))
        for name, body in pattern.findall(source)
    }


def interfaces(source: str) -> dict[str, set[str]]:
    """The keys of each `export interface` (with those of what it extends)"""
    found: dict[str, tuple[str | None, set[str]]] = {}
    pattern = re.compile(
        r"export interface (\w+)(?: extends (\w+))? \{\n(.*?)\n\}", re.DOTALL
    )
    for name, parent, body in pattern.findall(source):
        keys = set(re.findall(r"^  (\w+)\??:", body, re.MULTILINE))
        found[name] = (parent or None, keys)

    def all_keys(name: str) -> set[str]:
        parent, keys = found[name]
        return keys | (all_keys(parent) if parent else set())

    return {name: all_keys(name) for name in found}


def literals_of(source: str, type_name: str) -> set[str]:
    """The string literals in `export type NAME = ...;`"""
    # (to the `;` that ends the statement: one at the start of a line, or before a blank line)
    match = re.search(
        rf"export type {type_name} =(.*?);\n(?=\n|\S|\Z)", source, re.DOTALL
    )
    assert match, type_name
    return set(re.findall(r'"(\w+)"', match.group(1)))


@pytest.fixture(scope="module")
def exported():
    # (models are initialised with a database module that needs no database, as the tests of
    # `pangloss-models` do; the global settings are put back after)
    saved = core_settings.__dict__.get("SETTINGS")
    ClientSettings(INSTALLED_APPS=[], STORAGE="pangloss_sdk.storage:api")
    ModelRegistry._reset()
    sys.path.insert(0, str(SUPPORT))
    try:
        import kitchen_sink

        kitchen_sink.declare()
        initialise()
        yield export_definitions()
    finally:
        sys.path.remove(str(SUPPORT))
        sys.modules.pop("kitchen_sink", None)
        ModelRegistry._reset()
        if saved is None:
            core_settings.__dict__.pop("SETTINGS", None)
        else:
            core_settings.SETTINGS = saved


@pytest.fixture(scope="module")
def typescript():
    source = MODELS_TS.read_text()
    return source, interfaces(source)


def test_every_model_has_the_keys_of_model_definition(exported, typescript):
    source, types = typescript
    kinds = literals_of(source, "ModelKind")
    # (every key of the type, but those it marks optional, which are written only when they say something:
    # `labelTemplate`)
    optional = optional_keys(source)["ModelDefinition"]
    for name, model in exported["models"].items():
        assert set(model) <= types["ModelDefinition"], name
        assert types["ModelDefinition"] - optional <= set(model), name
        assert model["kind"] in kinds, (name, model["kind"])


def test_every_field_has_the_keys_of_its_kind(exported, typescript):
    source, types = typescript
    optional = optional_keys(source)
    seen = set()
    for model in exported["models"].values():
        for field in model["fields"]:
            seen.add(field["kind"])
            interface = FIELD_INTERFACES[field["kind"]]
            # (every key of the type, but those it marks optional, which are written only when they say something)
            assert set(field) <= types[interface] and types[interface] - optional[
                interface
            ] <= set(field), (model["name"], field["name"], interface)
    # (the kitchen sink has every kind but "unknown", which is for what the export cannot say)
    assert seen == set(FIELD_INTERFACES) - {"unknown"}


def test_relation_options_and_incoming_relations_have_the_known_shapes(
    exported, typescript
):
    source, types = typescript
    option_kinds = literals_of(source, "RelationOption")
    for model in exported["models"].values():
        for field in model["fields"]:
            if field["kind"] == "relation":
                for option in field["options"]:
                    assert option["kind"] in option_kinds, option
        for incoming in model["incoming"]:
            assert set(incoming) == types["IncomingRelation"], model["name"]


def test_enums_have_the_keys_of_enum_definition(exported, typescript):
    _, types = typescript
    assert exported["enums"]
    for enum in exported["enums"].values():
        assert set(enum) == types["EnumDefinition"]


def test_the_colours_are_the_same_in_python_and_typescript(typescript):
    source, _ = typescript
    assert literals_of(source, "Colour") == set(COLOURS)


def test_the_interface_meta_and_the_nav_have_the_keys_of_their_types(
    exported, typescript
):
    _, types = typescript
    assert set(exported) == types["ModelDefinitions"]
    metas = [
        m["interfaceMeta"] for m in exported["models"].values() if m["interfaceMeta"]
    ]
    for meta in metas:
        assert set(meta) == types["InterfaceMeta"]
    assert set(exported["nav"]) == types["NavConfig"]
    # (the entries are made from the dataclasses of config.py)
    from pangloss_interface import InterfaceConfig, NavLink, NavModel
    from pangloss_interface.config import merge

    nav = merge([("a", InterfaceConfig(nav=[NavModel("X"), NavLink("L", "/l")]))])
    assert set(nav["models"]["X"]) == types["NavModelEntry"]
    assert set(nav["links"][0]) == types["NavLinkEntry"]


def test_the_search_keys_are_the_same_in_python_and_typescript():
    from pangloss_models.search import SearchKey

    source = (MODELS_TS.parent.parent / "api/types.ts").read_text()
    match = re.search(r"export type SearchKey =(.*?);\n", source, re.DOTALL)
    assert match
    assert set(re.findall(r'"(\$\w+)"', match.group(1))) == {k.value for k in SearchKey}


def test_the_conditions_of_a_search_have_the_operators_of_their_kind_in_typescript():
    from pangloss_models.search import OPERATORS

    # (without the parameters of the generic ones, `CompareCondition<T>`)
    source = (MODELS_TS.parent.parent / "api/types.ts").read_text()
    found = interfaces(re.sub(r"(export interface \w+)<[^>]*>", r"\1", source))
    assert found["TextCondition"] == OPERATORS["text"]
    assert found["CompareCondition"] == OPERATORS["number"] == OPERATORS["temporal"]
    assert found["ChoiceCondition"] == OPERATORS["simple"]
    assert found["ItemsCondition"] == OPERATORS["list"]
    assert found["RelationCondition"] == OPERATORS["relation"] | {"through"}


def test_the_search_patterns_have_the_keys_of_their_types(exported, typescript):
    _, types = typescript
    assert exported["searchPatterns"]
    for pattern in exported["searchPatterns"].values():
        assert set(pattern) == types["SearchPatternDefinition"]
        for field in pattern["fields"].values():
            assert set(field) <= types["SearchFieldDefinition"]
