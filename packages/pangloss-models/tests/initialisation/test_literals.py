"""What a literal type is and how it is stored, asked of `pangloss_models.literals` directly (the gaps mutation testing
found: the other tests reach it through `initialise()` and the export)"""

import datetime
import enum
import ipaddress
import re
from decimal import Decimal
from fractions import Fraction
from typing import Annotated, Literal, NamedTuple, TypedDict

import pydantic
import pytest
from pangloss_models import PanglossModelError, literals
from pangloss_models.literals import LiteralCodec


class Colour(enum.Enum):
    RED = "red"


def test_a_value_is_stored_by_the_codec_of_its_own_type():
    assert literals.codec_for_value(True).storage == "bool"
    assert literals.codec_for_value(1).storage == "int"
    # (a `ByteSize` is an `int`, but not just any int: the natives are exact)
    size = pydantic.ByteSize(5)
    assert literals.codec_for_value(size).format == "bytes"
    assert type(literals.to_storage(size)) is int
    # (a date is not a decimal, though the decimal's codec takes subclasses)
    day = datetime.date(1500, 1, 1)
    assert literals.codec_for_value(day).storage == "date"
    assert literals.to_storage(day) is day
    assert literals.to_storage(Decimal("1.50")) == "1.50"
    assert literals.to_storage(re.compile("a+")) == "a+"
    assert literals.to_storage(Fraction(1, 3)) == "1/3"
    assert literals.to_storage(ipaddress.IPv4Address("10.0.0.1")) == "10.0.0.1"
    assert literals.codec_for_value(object()) is None


def test_a_package_codec_is_asked_first_and_must_store_a_native():
    class Shelfmark(str):
        pass

    codec = LiteralCodec((Shelfmark,), "str", "shelfmark", "text", lambda v: v.upper())
    with pytest.raises(
        PanglossModelError,
        match=r"store its values as one of str, int, .*, not 'blob'$",
    ):
        literals.register_codec(LiteralCodec((Shelfmark,), "blob"))  # ty: ignore[invalid-argument-type]
    earlier = LiteralCodec((Shelfmark,), "str", "earlier", "text")
    literals.register_codec(earlier)
    literals.register_codec(codec)
    try:
        # (the one registered last is asked first)
        assert literals.codecs()[:2] == (codec, earlier)
        assert literals.codec_for(Shelfmark) is codec
        assert literals.to_storage(Shelfmark("ms 1")) == "MS 1"
        assert literals.export_type(Shelfmark) == {"type": "str", "format": "shelfmark"}
    finally:
        literals._registered.remove(codec)
        literals._registered.remove(earlier)
    assert literals.codec_for(Shelfmark) is None


def test_a_codec_matches_only_types():
    assert not literals.NATIVE_CODECS[3].matches("str")


def test_a_literal_choice_is_of_one_native_type():
    assert literals.literal_choice_storage(Literal["a", "b"]) == "str"
    assert literals.literal_choice_storage(Annotated[Literal[1, 2], "x"]) == "int"
    with pytest.raises(
        PanglossModelError,
        match=r"^Literal\[1\.5\]: the values of a Literal must be strings, whole numbers or booleans$",
    ):
        literals.literal_choice_storage(Literal[1.5])
    with pytest.raises(
        PanglossModelError,
        match=r"^Literal\[1, 'a'\]: the values of a Literal must all be of one type$",
    ):
        literals.literal_choice_storage(Literal[1, "a"])


def test_a_list_cannot_hold_none_and_the_error_says_the_list_to_write():
    for given, wanted in (
        (list[str | None], "list[str] | None"),
        (list[str | None] | None, "list[str] | None"),
        (tuple[int | None, ...], "tuple[int, ...] | None"),
        (set[Colour | None], "set[Colour] | None"),
    ):
        with pytest.raises(PanglossModelError) as refused:
            literals.is_list_of_literal_type(given)
        assert f"make the whole list optional (`{wanted}`)" in str(refused.value)
        assert refused.value.fix == ("drop_none_in_items", "optional_list")


def test_only_x_or_none_is_optional():
    assert literals.is_optional(int | None)
    assert not literals.is_optional(int)
    assert not literals.is_optional(int | str)
    assert not literals.is_optional(int | str | None)
    assert literals.without_none(int | None) is int
    assert literals.without_none(int | str) == int | str


def test_why_a_type_is_refused():
    class Pair(NamedTuple):
        a: int

    class Plain(tuple):
        pass

    assert literals.explain_unsupported(Pair).startswith("a NamedTuple is not stored")
    assert literals.explain_unsupported(Plain) is None
    assert literals.explain_unsupported(dict[str, int]).startswith("a plain dict")
    assert literals.explain_unsupported(int | str | None).startswith(
        "a union of literal types has no one storage type"
    )
    assert literals.explain_unsupported(int | list[str]).startswith(
        "a union of literal types"
    )
    assert literals.explain_unsupported(int | Plain) is None
    assert literals.explain_unsupported(list[Plain]) is None


def test_what_is_stored_of_a_type_drops_what_only_the_models_say():
    class Dimensions(TypedDict):
        width: int
        unit: Literal["cm", "in"]
        when: datetime.date | None

    assert literals.storage_descriptor(literals.export_type(Dimensions)) == {
        "type": "typedDict",
        "fields": {
            "width": {"type": "int"},
            "unit": {"type": "str"},
            "when": {"type": "date"},
        },
    }
    assert literals.storage_descriptor(literals.export_type(set[Colour])) == {
        "type": "list",
        "item": {"type": "enum", "enum": "Colour"},
    }
    assert literals.storage_descriptor({"type": "list"}) == {
        "type": "list",
        "item": {"type": None},
    }
    assert literals.storage_descriptor({"type": "typedDict"}) == {
        "type": "typedDict",
        "fields": {},
    }
    assert literals.storage_descriptor(
        {"type": "literal", "values": [True, False]}
    ) == {"type": "bool"}
    assert literals.storage_descriptor({"type": "literal", "values": [1, 2]}) == {
        "type": "int"
    }
    assert literals.python_type_of_storage({"type": "str", "format": "uuid"}) is str
    assert literals.python_type_of_storage({"type": "decimal"}) is Decimal
    assert literals.python_type_of_storage({"type": "duration"}) is datetime.timedelta
    assert literals.python_type_of_storage({"type": "enum", "enum": "Colour"}) is None


def test_the_export_of_a_type_and_the_enums_met_on_the_way():
    class Dimensions(TypedDict):
        colour: Colour
        tags: list[str]

    met = []
    assert literals.export_type(
        Annotated[list[Dimensions] | None, "x"], met.append
    ) == {
        "type": "list",
        "item": {
            "type": "typedDict",
            "fields": {
                "colour": {"type": "enum", "enum": "Colour"},
                "tags": {"type": "list", "item": {"type": "str"}},
            },
        },
    }
    assert met == [Colour]
    assert literals.export_type(tuple[int, int]) == {
        "type": "list",
        "item": {"type": "int"},
        "length": 2,
    }
    assert literals.export_type(frozenset[str]) == {
        "type": "list",
        "item": {"type": "str"},
        "unique": True,
    }
    assert literals.export_type(Literal[Colour.RED, "b"]) == {
        "type": "literal",
        "values": ["red", "b"],
    }
    assert literals.export_type(pydantic.AnyHttpUrl) == {"type": "str", "format": "url"}
    assert literals.export_type(object) is None
    assert literals.export_type_or_unknown(list[object]) == {
        "type": "list",
        "item": {"type": "unknown", "repr": "<class 'object'>"},
    }
    assert literals.export_type_or_unknown(Annotated[object, "x"]) == {
        "type": "unknown",
        "repr": "<class 'object'>",
    }
