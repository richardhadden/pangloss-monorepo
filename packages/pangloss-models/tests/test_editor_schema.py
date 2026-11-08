import dataclasses
import enum
from typing import Literal

from pangloss_models.editor_schema import (
    _describe,
    choices_of,
    comments_above_fields,
    editor_schema,
)


class Shade(enum.Enum):
    LIGHT = "light"
    DARK = "dark"


@dataclasses.dataclass(frozen=True)
class Options:
    """What a thing is shown as. More text that is not the first paragraph.

    A second paragraph."""

    # How loud it is
    volume: Literal["low", "high"] | None = None
    # (an aside, in parentheses)
    loud: bool = False
    shade: Shade = Shade.LIGHT
    names: list[str] = dataclasses.field(default_factory=list)
    plain: int = 3

    # (not documented: the blank line above breaks the comment from the field)

    other: str = ""

    @staticmethod
    def editor_choices(option: str) -> list[str] | None:
        return ["a:One", "a:Two"] if option == "other" else None


def test_the_comment_above_a_field_is_its_documentation():
    comments = comments_above_fields(Options)
    assert comments["volume"] == "How loud it is"
    assert comments["loud"] == "an aside, in parentheses"
    assert "plain" not in comments


def test_a_comment_that_is_not_directly_above_a_field_belongs_to_no_field():
    assert "other" not in comments_above_fields(Options)


def test_an_option_has_its_type_default_and_choices():
    described = _describe(Options)
    assert (
        described["doc"]
        == "What a thing is shown as. More text that is not the first paragraph."
    )
    options = {p["name"]: p for p in described["parameters"]}
    assert options["volume"]["choices"] == [("low", True), ("high", True)]
    assert options["volume"]["doc"] == "How loud it is"
    assert options["loud"]["choices"] == [("True", False), ("False", False)]
    assert options["shade"]["choices"] == [("light", True), ("dark", True)]
    assert options["names"]["default"] == "[]"
    assert options["plain"]["default"] == "3"
    assert options["plain"]["choices"] == []


def test_a_class_can_say_what_an_option_takes_itself():
    options = {p["name"]: p for p in _describe(Options)["parameters"]}
    assert options["other"]["choices"] == [("a:One", True), ("a:Two", True)]


def test_choices_of_an_alias_and_a_union():
    type Colour = Literal["red", "blue"]

    assert choices_of(Colour | None) == [("red", True), ("blue", True)]
    assert choices_of(int) == []


def test_the_schema_of_no_models_still_has_the_options_of_the_metas():
    schema = editor_schema()
    assert "EntityMeta" in schema["calls"]
    assert schema["aliases"]["Entity.Meta"] == "EntityMeta"
    assert {slot["name"] for slot in schema["slots"]} >= {"_protect_meta"}


def test_a_model_lists_the_keywords_of_its_where():
    from pangloss_models import Entity, ModelRegistry, initialise

    ModelRegistry._reset()
    try:

        class Place(Entity):
            name: str

        class Person(Entity):
            name: str
            born_in: Place

        initialise(bind_database=False)
        models = editor_schema()["models"]
        keys = [key["name"] for key in models["Person"]["where"]]
        assert {"label", "name", "born_in", "all_", "any_of_", "not_"} <= set(keys)
        assert "name" in [key["name"] for key in models["Place"]["where"]]
    finally:
        ModelRegistry._reset()
