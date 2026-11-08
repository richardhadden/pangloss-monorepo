"""What a field may be typed with, and what each type comes to: the table of docs/modelling-dx.md, kept true.

One case per type: the kind of definition it is given and what the export says of it, or the error it raises
(with the alternative the message names). A type here that is accepted is also stored and read back in
`pangloss_testing/conformance/test_literal_types.py`."""

import datetime
import ipaddress
import pathlib
import re
import uuid
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum, IntEnum, IntFlag, StrEnum
from fractions import Fraction
from typing import Annotated, Any, Literal, NamedTuple, NotRequired, TypedDict

import pytest
from pangloss_models import (
    AnnotatedValue,
    Document,
    Embedded,
    Entity,
    ModelRegistry,
    PanglossModelError,
    export_models,
    initialise,
)
from pangloss_models.field_definitions import (
    ListFieldDefinition,
    LiteralFieldDefinition,
)
from pydantic import (
    AnyUrl,
    BaseModel,
    ByteSize,
    EmailStr,
    HttpUrl,
    NameEmail,
    PositiveInt,
    SecretStr,
    StrictStr,
    conint,
    constr,
)


class Colour(Enum):
    RED = "red"
    BLUE = "blue"


class Size(IntEnum):
    SMALL = 1
    LARGE = 2


class Tone(StrEnum):
    LOUD = "loud"
    SOFT = "soft"


class Permission(IntFlag):
    READ = 1
    WRITE = 2


class Dimensions(TypedDict):
    width: int
    note: NotRequired[str]


class Point(NamedTuple):
    x: float
    y: float


class Extra(BaseModel):
    a: int


@dataclass
class Plain:
    a: int


def declare(annotation: Any, default: Any = ...):
    """A document with one field of the type, initialised (alone); the definition and the export of the field"""
    ModelRegistry._reset()
    namespace: dict[str, Any] = {"__annotations__": {"value": annotation}}
    if default is not ...:
        namespace["value"] = default
    Statement = type("Statement", (Document,), namespace)
    initialise()
    exported = next(
        f
        for f in export_models()["models"]["Statement"]["fields"]
        if f["name"] == "value"
    )
    return Statement, Statement._meta.fields["value"], exported


SCALARS = [
    (str, {"type": "str"}, "text"),
    (int, {"type": "int"}, "number"),
    (float, {"type": "float"}, "number"),
    (bool, {"type": "bool"}, "simple"),
    (Decimal, {"type": "decimal"}, "decimal"),
    (datetime.date, {"type": "date"}, "temporal"),
    (datetime.datetime, {"type": "datetime"}, "temporal"),
    (datetime.time, {"type": "time"}, "temporal"),
    (datetime.timedelta, {"type": "duration"}, "simple"),
    (uuid.UUID, {"type": "str", "format": "uuid"}, "text"),
    (AnyUrl, {"type": "str", "format": "url"}, "text"),
    (HttpUrl, {"type": "str", "format": "url"}, "text"),
    (EmailStr, {"type": "str", "format": "email"}, "text"),
    (NameEmail, {"type": "str", "format": "email"}, "text"),
    (ipaddress.IPv4Address, {"type": "str", "format": "ip"}, "text"),
    (ipaddress.IPv6Network, {"type": "str", "format": "ip-network"}, "text"),
    (pathlib.Path, {"type": "str", "format": "path"}, "text"),
    (re.Pattern, {"type": "str", "format": "regex"}, "simple"),
    (Fraction, {"type": "str", "format": "fraction"}, "simple"),
    (ByteSize, {"type": "int", "format": "bytes"}, "number"),
    (Colour, {"type": "enum", "enum": "Colour"}, "simple"),
    (Size, {"type": "enum", "enum": "Size"}, "simple"),
    (Tone, {"type": "enum", "enum": "Tone"}, "simple"),
    (Literal["a", "b"], {"type": "literal", "values": ["a", "b"]}, "simple"),
    (Literal[1, 2], {"type": "literal", "values": [1, 2]}, "simple"),
    (
        Dimensions,
        {
            "type": "typedDict",
            "fields": {"width": {"type": "int"}, "note": {"type": "str"}},
        },
        None,
    ),
]


@pytest.mark.parametrize(
    "annotation, described, kind", SCALARS, ids=lambda a: repr(a)[:40]
)
def test_a_scalar_literal_is_a_literal_field_described_by_its_storage(
    annotation, described, kind
):
    from pangloss_models.search import kind_of

    Statement, definition, exported = declare(annotation)
    assert isinstance(definition, LiteralFieldDefinition)
    assert exported["kind"] == "literal"
    assert exported["type"] == described
    assert exported["required"] is True and exported["nullable"] is False
    assert exported["default"] is None
    assert kind_of(annotation) == kind
    # (and `X | None` of it is the same type, optional, and may be left out of a payload)
    Optional, optional, exported = declare(annotation | None)
    assert isinstance(optional, LiteralFieldDefinition)
    assert exported["type"] == described
    assert exported["nullable"] is True
    assert Optional.Create(label="x").value is None


@pytest.mark.parametrize(
    "annotation, item, validators",
    [
        (list[str], {"type": "str"}, []),
        (list[uuid.UUID], {"type": "str", "format": "uuid"}, []),
        (set[str], {"type": "str"}, [{"name": "Unique"}]),
        (frozenset[int], {"type": "int"}, [{"name": "Unique"}]),
        (
            tuple[float, float],
            {"type": "float"},
            [{"name": "MinLen", "min_length": 2}, {"name": "MaxLen", "max_length": 2}],
        ),
        (tuple[str, ...], {"type": "str"}, []),
        (list[Colour], {"type": "enum", "enum": "Colour"}, []),
    ],
    ids=lambda a: repr(a)[:40],
)
def test_a_collection_of_literals_is_a_list_field(annotation, item, validators):
    Statement, definition, exported = declare(annotation)
    assert isinstance(definition, ListFieldDefinition)
    assert exported["kind"] == "list"
    assert exported["item"] == item
    # (what the collection says beyond being a list is told as validators, which the interface checks)
    assert exported["validators"] == validators
    assert exported["required"] is True
    # (and `X | None` of it may be left out: no list, as against an empty one)
    Optional, optional, exported = declare(annotation | None)
    assert isinstance(optional, ListFieldDefinition)
    assert exported["nullable"] is True
    assert Optional.Create(label="x").value is None


def test_a_set_is_a_set_and_a_tuple_has_its_length():
    from pydantic import ValidationError

    Statement, _, _ = declare(set[str])
    assert Statement.Create(label="x", value=["a", "a", "b"]).value == {"a", "b"}
    Pair, _, _ = declare(tuple[float, float])
    assert Pair.Create(label="x", value=[1, 2]).value == (1.0, 2.0)
    with pytest.raises(ValidationError):
        Pair.Create(label="x", value=[1, 2, 3])


REFUSED = [
    (dict, "TypedDict"),
    (dict[str, str], "TypedDict"),
    (bytes, "base64"),
    (complex, "two parts"),
    (Any, "give it a type"),
    (object, "give it a type"),
    (SecretStr, "secret"),
    (Point, "NamedTuple"),
    (Extra, "Embedded"),
    (Plain, "dataclass"),
    (Permission, "Flag"),
    (int | str, "union of literal types"),
    (Literal["a", 1], "all be of one type"),
    (Literal[Colour.RED], "the enum itself"),
    (list[str | None], "cannot hold None"),
    (tuple[str, int], "items of a tuple must all be of one type"),
    (list[Permission], "Flag"),
]


@pytest.mark.parametrize("annotation, names", REFUSED, ids=lambda a: repr(a)[:40])
def test_what_is_not_supported_is_refused_and_the_message_names_the_alternative(
    annotation, names
):
    with pytest.raises(PanglossModelError, match=names):
        declare(annotation)


def test_an_optional_relation_is_refused_naming_the_alternative():
    class Person(Entity):
        pass

    class Marriage(Document):
        spouse: Person | None

    with pytest.raises(PanglossModelError, match=r"optional relation.*list\[\.\.\.\]"):
        initialise()


def test_an_optional_embedded_object_is_refused_naming_the_alternative():
    class Date(Embedded):
        when: datetime.date

    class Event(Document):
        date: Date | None

    with pytest.raises(PanglossModelError, match="optional embedded object"):
        initialise()


def test_pydantic_constrained_types_are_literal_fields_with_their_constraints():
    from annotated_types import Ge, Gt, MaxLen, MinLen
    from pydantic import ValidationError

    class Statement(Document):
        count: PositiveInt
        code: constr(max_length=3)  # type: ignore[valid-type]
        rank: conint(ge=0)  # type: ignore[valid-type]
        name: StrictStr
        tags: Annotated[list[str], MinLen(1), MaxLen(2)]

    initialise()
    fields = Statement._meta.fields
    assert fields["count"].validators == [Gt(0)]
    assert MaxLen(3) in fields["code"].validators
    assert Ge(0) in fields["rank"].validators
    assert [type(v).__name__ for v in fields["name"].validators] == ["Strict"]
    assert fields["tags"].validators == [MinLen(1), MaxLen(2)]

    exported = {f["name"]: f for f in export_models()["models"]["Statement"]["fields"]}
    assert exported["count"]["validators"] == [{"name": "Gt", "gt": 0}]
    assert {"name": "MaxLen", "max_length": 3} in exported["code"]["validators"]
    assert exported["name"]["validators"] == [{"name": "Strict", "strict": True}]

    good = dict(label="x", count=1, code="abc", rank=0, name="n", tags=["a"])
    Statement.Create(**good)
    for wrong in (
        {"count": 0},
        {"code": "abcd"},
        {"rank": -1},
        {"name": 1},
        {"tags": []},
        {"tags": ["a", "b", "c"]},
    ):
        with pytest.raises(ValidationError):
            Statement.Create(**{**good, **wrong})


def test_an_annotated_value_of_a_new_type_is_allowed():
    class WithCertainty[T](AnnotatedValue[T]):
        certainty: int

    class Statement(Document):
        identifier: WithCertainty[uuid.UUID]

    initialise()
    made = Statement.Create(
        label="x",
        identifier={"value": "0193a2b4-0000-7000-8000-000000000001", "certainty": 2},
    )
    assert isinstance(made.identifier.value, uuid.UUID)
