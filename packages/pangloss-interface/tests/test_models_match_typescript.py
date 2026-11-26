"""What `export_models()` writes has the shape the interface's TypeScript types say
(`interface-core/src/types/models.ts`). Python makes the data and TypeScript reads it, and
nothing else compares them: a key added on one side only is a type error in `pangloss interface
check`, or a value the interface never reads. Every kind of model and field is in the kitchen-sink
models of `pangloss-models`' tests."""

import re
import sys
from pathlib import Path
from typing import get_args, get_type_hints

import pangloss_interface
import pytest
from pangloss_core import ClientSettings
from pangloss_core import settings as core_settings
from pangloss_models import ModelRegistry, initialise
from pangloss_interface import BAND_KINDS, BAND_PATTERNS, COLOURS
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


def test_a_semantic_space_alone_says_what_it_does_to_its_contents(exported, typescript):
    from pangloss_models import Modal
    from pangloss_models.export import export_logical
    from pangloss_models.model_bases.semantic_space import (
        DEGREE_STEPS,
        SemanticSpaceMeta,
    )

    source, types = typescript
    keys = {"veridical", "fit", "logical", "unary", "degree"}
    # (optional on `ModelDefinition`: only a space has them)
    assert keys <= optional_keys(source)["ModelDefinition"]
    spaces = [m for m in exported["models"].values() if m["kind"] == "SemanticSpace"]
    assert spaces
    for model in exported["models"].values():
        if model["kind"] == "SemanticSpace":
            assert keys <= set(model), model["name"]
        else:
            assert not keys & set(model), model["name"]
    # (the values each may have, as Python's types and TypeScript's say them)
    match = re.search(r"export type Veridical = ([^;]*);", source)
    assert match
    # (what holds, `veridicality`: never null)
    veridicality = get_type_hints(SemanticSpaceMeta.veridicality.fget)["return"]
    assert {int(v) for v in re.findall(r"-?\d+", match.group(1))} == set(
        get_args(veridicality)
    )
    assert literals_of(source, "SpaceFit") == set(
        get_args(SemanticSpaceMeta.model_fields["fit"].annotation)
    )
    assert literals_of(source, "DegreeStep") == set(DEGREE_STEPS)
    assert re.search(r"export type SpaceLogical = SpaceNot \| SpaceModal;", source)
    assert set(export_logical("not") or {}) == types["SpaceNot"]
    assert (
        set(export_logical(Modal("necessity", "command", of_not=True)) or {})
        == types["SpaceModal"]
    )
    force = re.search(r"export interface SpaceModal \{\n  force: ([^;]*);", source)
    assert force
    assert set(re.findall(r'"(\w+)"', force.group(1))) == set(
        get_args(Modal.__dataclass_fields__["force"].type)
    )
    for model in spaces:
        assert model["veridical"] in (1, 0, -1)
        assert model["fit"] in literals_of(source, "SpaceFit")
        assert model["degree"] is None or model["degree"] in DEGREE_STEPS
        assert isinstance(model["unary"], bool)
        assert model["logical"] is None or set(model["logical"]) in (
            types["SpaceNot"],
            types["SpaceModal"],
        )


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


def test_companions_have_the_keys_of_their_types(exported, typescript):
    _, types = typescript
    companions = [
        c for m in exported["models"].values() for c in m.get("companions", ())
    ]
    # (the kitchen sink's `Group` has one, with a part, a copy, and both kinds of offer)
    assert companions
    offers = {"within": "CompanionWithin", "standalone": "CompanionStandalone"}
    for companion in companions:
        assert set(companion) == types["CompanionDefinition"]
        for part in companion["parts"]:
            assert set(part) == types["CompanionPartDefinition"]
            assert set(part["entityField"]) == types["CompanionField"]
        for copy in companion["copies"]:
            assert set(copy) == types["CompanionCopy"]
        assert {o["kind"] for o in companion["offered"]} == set(offers)
        for offer in companion["offered"]:
            assert set(offer) == types[offers[offer["kind"]]]


def test_enums_have_the_keys_of_enum_definition(exported, typescript):
    _, types = typescript
    assert exported["enums"]
    for enum in exported["enums"].values():
        assert set(enum) == types["EnumDefinition"]


def test_the_colours_are_the_same_in_python_and_typescript(typescript):
    source, _ = typescript
    assert literals_of(source, "Colour") == set(COLOURS)


def test_the_bands_of_spaces_are_the_same_in_python_and_typescript(
    exported, typescript
):
    source, types = typescript
    assert literals_of(source, "BandPattern") == set(BAND_PATTERNS)
    assert literals_of(source, "BandKind") == set(BAND_KINDS)
    # (nothing given by the project: none of its own)
    assert exported["spaceBands"] == {}
    assert "band" in types["InterfaceMeta"]


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
    assert found["RelationCondition"] == OPERATORS["relation"] | {
        "through",
        "edge",
        "via",
    }


def test_the_search_patterns_have_the_keys_of_their_types(exported, typescript):
    _, types = typescript
    assert exported["searchPatterns"]
    for pattern in exported["searchPatterns"].values():
        # (`flags` is there only for a class that an installed app offers a yes-or-no filter for)
        assert set(pattern) | {"flags"} == types["SearchPatternDefinition"]
        for field in pattern["fields"].values():
            assert set(field) <= types["SearchFieldDefinition"]


def test_a_path_entry_has_the_same_keys_and_kinds_in_python_and_typescript():
    from pangloss_models.context import KINDS, PathEntry

    source = (MODELS_TS.parent.parent / "api/types.ts").read_text()
    assert interfaces(source)["PathEntry"] == set(PathEntry.__annotations__)
    # (the degree entered on a space is the one key that may be absent, in both)
    body = re.search(r"export interface PathEntry \{\n(.*?)\n\}", source, re.DOTALL)
    assert body
    optional = set(re.findall(r"^  (\w+)\?:", body.group(1), re.MULTILINE))
    assert optional == set(PathEntry.__optional_keys__) == {"degree"}
    assert re.search(r"^  degree\?: DegreeStep;", body.group(1), re.MULTILINE)
    match = re.search(r"export interface PathEntry \{\n  kind: ([^;]*);", source)
    assert match
    assert set(re.findall(r'"(\w+)"', match.group(1))) == set(KINDS)


def test_the_label_templates_walk_the_same_keys_in_python_and_typescript():
    from pangloss_models import label_templates

    source = (MODELS_TS.parent.parent / "schema/labelTemplate.ts").read_text()

    def constant(name: str) -> set[str]:
        match = re.search(rf"const {name} = (?:new Set\()?\[([^\]]*)\]", source)
        assert match, name
        return set(re.findall(r'"(\w+)"', match.group(1)))

    for name in ("WRAPPERS", "NOT_CONTENTS", "NOT_WALKED"):
        assert constant(name) == set(getattr(label_templates, name)), name


def test_an_attribution_has_the_keys_of_its_type(exported, typescript):
    """`Attribution(by=..., to=...)`: the kitchen sink has none (it would change the stored snapshot of its generated
    models), so a few models of its own are declared, and the kitchen sink is put back after"""
    from typing import Annotated

    from pangloss_models import Attribution, Document, Entity, SemanticSpace

    source, types = typescript
    # (optional on a relation: written only where there is one)
    assert "attribution" in optional_keys(source)["RelationField"]
    assert re.search(r"  attribution\?: FieldAttribution;", source)
    assert types["FieldAttribution"] == {"by", "to"}
    for key in ("by", "to"):
        assert re.search(rf"  {key}: CompanionField \| null;", source), key
    ModelRegistry._reset()
    try:

        class Person(Entity):
            pass

        class Ordered[T](SemanticSpace[T]):
            pass

        class Statement(Document):
            pass

        class Order(Document):
            ordered_by: Person
            ordered_to: list[Person]
            thing_ordered: Annotated[
                Ordered[Statement], Attribution(by="ordered_by", to="ordered_to")
            ]
            believed: Annotated[Ordered[Statement], Attribution(by="ordered_by")]

        initialise()
        fields = {
            f["name"]: f for f in export_definitions()["models"]["Order"]["fields"]
        }
    finally:
        import kitchen_sink

        ModelRegistry._reset()
        kitchen_sink.declare()
        initialise()
    optional = optional_keys(source)["RelationField"]
    for field in fields.values():
        if field["kind"] == "relation":
            assert set(field) <= types["RelationField"], field["name"]
            assert types["RelationField"] - optional <= set(field), field["name"]
    for name in ("thing_ordered", "believed"):
        attribution = fields[name]["attribution"]
        assert set(attribution) == types["FieldAttribution"]
        for named in attribution.values():
            assert named is None or set(named) == types["CompanionField"]
    assert fields["believed"]["attribution"]["to"] is None
    assert "attribution" not in fields["ordered_by"]
