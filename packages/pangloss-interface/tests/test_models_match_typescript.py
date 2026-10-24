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
from pangloss_core import settings as core_settings
from pangloss_core.settings import ClientSettings
from pangloss_models import initialise
from pangloss_models.export import export_models
from pangloss_models.model_registry import ModelRegistry

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
    match = re.search(rf"export type {type_name} =(.*?);\n", source, re.DOTALL)
    assert match, type_name
    return set(re.findall(r'"(\w+)"', match.group(1)))


@pytest.fixture(scope="module")
def exported():
    # (models are initialised with a database module that needs no database, as the tests of
    # `pangloss-models` do; the global settings are put back after)
    saved = core_settings.__dict__.get("SETTINGS")
    ClientSettings(INSTALLED_APPS=[], DATABASE_MODULE="pangloss_sdk.databases.api")
    ModelRegistry._reset()
    sys.path.insert(0, str(SUPPORT))
    try:
        import kitchen_sink

        kitchen_sink.declare()
        initialise()
        yield export_models()
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
    for name, model in exported["models"].items():
        assert set(model) == types["ModelDefinition"], name
        assert model["kind"] in kinds, (name, model["kind"])


def test_every_field_has_the_keys_of_its_kind(exported, typescript):
    _, types = typescript
    seen = set()
    for model in exported["models"].values():
        for field in model["fields"]:
            seen.add(field["kind"])
            interface = FIELD_INTERFACES[field["kind"]]
            assert set(field) == types[interface], (
                model["name"],
                field["name"],
                interface,
            )
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
