"""The literal types: what a field may be typed with that is stored as a property, and how.

Every place that needs to know what a literal is asks here, once: the analysis of the fields (`is_literal`), what
is written to the database (`to_storage`), what the interface is told of a type (`export_type`), how a search
compares it (`search_kind_of`), and what a migration sees as a change of storage (`storage_descriptor`).

A type is one of:

- a **codec** (`LiteralCodec`): a Python type and how it is stored. The natives (`str`, `int`, `float`, `bool`,
  `Decimal`, `date`, `datetime`, `time`, `timedelta`) are stored as themselves (a `Decimal` as text, to keep its
  value exact), and the rest as one of them with a *format* that says what the text means: a `UUID`, a URL, an
  email address, an IP address, a path, a regular expression, a fraction. The export says
  `{"type": "str", "format": "uuid"}`, so the interface and the migrations see the storage, and the format tells
  them what else they can know;
- an `Enum` (stored as the member's value);
- a `Literal["a", "b"]` (stored as the value; the values must be of one native type);
- a `TypedDict` of these (a map);
- a list, set, frozenset or tuple of these (a list).

A package may add a codec (`register_codec`): the core knows the shapes, the packages the types.
"""

import datetime
import enum
import ipaddress
import pathlib
import re
import typing
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from types import NoneType, UnionType
from typing import Annotated, Any, Literal, get_args, get_origin, is_typeddict

import pydantic
from pydantic import networks
from pydantic_core import MultiHostUrl, Url

from pangloss_models.exceptions import PanglossModelError

# How a value is kept in the database: the types a graph property can be
Storage = Literal[
    "str", "int", "float", "bool", "decimal", "date", "datetime", "time", "duration"
]
STORAGES: tuple[str, ...] = typing.get_args(Storage)

# How a search compares a value (see `pangloss_models.search.Kind`)
SearchKind = Literal["text", "number", "decimal", "temporal", "simple"]

# The Python type a value of each storage is given back as (what a migration's default is parsed to)
PYTHON_TYPE_OF_STORAGE: dict[str, type] = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "decimal": Decimal,
    "date": datetime.date,
    "datetime": datetime.datetime,
    "time": datetime.time,
    "duration": datetime.timedelta,
}


@dataclass(frozen=True)
class LiteralCodec:
    """A Python type that is a literal, and how it is stored"""

    types: tuple[Any, ...]
    """The Python types this codec is for (a value is one of them, or of a subclass). (`Any`: pydantic's
    `IPvAnyAddress` and the like are classes at run time that a type checker is told are `str`)"""
    storage: Storage
    """What a value is kept as in the database"""
    format: str = ""
    """What the stored value means, if it is not just its storage type: `uuid`, `url`, ... (exported with the type)"""
    search_kind: SearchKind | None = "text"
    """How a search compares the field; None if it cannot be searched"""
    to_storage: Callable[[Any], Any] | None = None
    """From a Python value to what is stored (nothing: the value as it is; the driver takes the natives)"""
    exact: bool = False
    """Whether only the types themselves match, not their subclasses (`bool` is a subclass of `int`)"""

    def matches(self, tp: Any) -> bool:
        if not isinstance(tp, type):
            return False
        if self.exact:
            return tp in self.types
        return issubclass(tp, self.types)

    def describe(self) -> dict[str, Any]:
        """The type as the export says it: its storage, and its format if it has one"""
        if self.format:
            return {"type": self.storage, "format": self.format}
        return {"type": self.storage}


def _text(value: Any) -> str:
    return str(value)


# The natives first, each exact (a `bool` is an `int`, an `IntEnum` is an `int`, a `ByteSize` is an `int`), then the
# types stored as one of them. The order matters where types are related: the first that matches is the codec.
NATIVE_CODECS: tuple[LiteralCodec, ...] = (
    LiteralCodec((bool,), "bool", search_kind="simple", exact=True),
    LiteralCodec((int,), "int", search_kind="number", exact=True),
    LiteralCodec((float,), "float", search_kind="number", exact=True),
    LiteralCodec((str,), "str", search_kind="text", exact=True),
    LiteralCodec((Decimal,), "decimal", search_kind="decimal", to_storage=_text),
    LiteralCodec((datetime.datetime,), "datetime", search_kind="temporal"),
    LiteralCodec((datetime.date,), "date", search_kind="temporal"),
    LiteralCodec((datetime.time,), "time", search_kind="temporal"),
    # (a duration can be compared for equality on both databases; Neo4j does not order them)
    LiteralCodec((datetime.timedelta,), "duration", search_kind="simple"),
)

FORMAT_CODECS: tuple[LiteralCodec, ...] = (
    LiteralCodec((uuid.UUID,), "str", "uuid", "text", _text),
    # (`HttpUrl`, `AnyHttpUrl`, `FileUrl`, `FtpUrl`, ... are all `AnyUrl`s; a value is a `pydantic_core.Url`)
    LiteralCodec(
        (networks._BaseUrl, networks._BaseMultiHostUrl, Url, MultiHostUrl),
        "str",
        "url",
        "text",
        _text,
    ),
    # (an `EmailStr` is a `str` at run time: validated, not a type of its own; a `NameEmail` is "Name <address>")
    LiteralCodec((networks.EmailStr,), "str", "email", "text"),
    LiteralCodec((networks.NameEmail,), "str", "email", "text", _text),
    LiteralCodec(
        (ipaddress.IPv4Address, ipaddress.IPv6Address, networks.IPvAnyAddress),
        "str",
        "ip",
        "text",
        _text,
    ),
    LiteralCodec(
        (ipaddress.IPv4Network, ipaddress.IPv6Network, networks.IPvAnyNetwork),
        "str",
        "ip-network",
        "text",
        _text,
    ),
    LiteralCodec(
        (ipaddress.IPv4Interface, ipaddress.IPv6Interface, networks.IPvAnyInterface),
        "str",
        "ip-interface",
        "text",
        _text,
    ),
    LiteralCodec((pathlib.PurePath,), "str", "path", "text", _text),
    LiteralCodec((re.Pattern,), "str", "regex", "simple", lambda value: value.pattern),
    LiteralCodec((Fraction,), "str", "fraction", "simple", _text),
    # (`ByteSize` is an `int` with a meaning: stored as the number of bytes)
    LiteralCodec((pydantic.ByteSize,), "int", "bytes", "number", int),
)

_registered: list[LiteralCodec] = []


def register_codec(codec: LiteralCodec) -> None:
    """Add a codec for a type the core does not know (a package's own type, stored as one of the natives). It is
    asked before the core's own, so a package may also say more of a type the core knows"""
    if codec.storage not in STORAGES:
        raise PanglossModelError(
            f"A literal codec must store its values as one of {', '.join(STORAGES)}, not {codec.storage!r}"
        )
    _registered.insert(0, codec)


def codecs() -> tuple[LiteralCodec, ...]:
    return (*_registered, *NATIVE_CODECS, *FORMAT_CODECS)


def codec_for(tp: Any) -> LiteralCodec | None:
    """The codec of a scalar type (not an enum, a `Literal`, a `TypedDict` or a list), or None"""
    tp = _plain(tp)
    if not isinstance(tp, type) or issubclass(tp, enum.Enum):
        return None
    for codec in codecs():
        if codec.matches(tp):
            return codec
    return None


def codec_for_value(value: Any) -> LiteralCodec | None:
    for codec in codecs():
        if isinstance(value, codec.types) and (
            not codec.exact or type(value) in codec.types
        ):
            return codec
    return None


def to_storage(value: Any) -> Any:
    """A scalar value as it is written to the database (a container is the caller's to walk)"""
    codec = codec_for_value(value)
    if codec is not None and codec.to_storage is not None:
        return codec.to_storage(value)
    return value


# --- what a type is --------------------------------------------------------------------------------


# What wraps a type without changing what it is: `Annotated[X, ...]`, and in a `TypedDict` `Required[X]`,
# `NotRequired[X]` and `ReadOnly[X]`
_WRAPPERS = (Annotated, typing.Required, typing.NotRequired, typing.ReadOnly)


def _plain(tp: Any) -> Any:
    """An annotation without its `Annotated[...]` (or `NotRequired[...]`) wrapping"""
    while get_origin(tp) in _WRAPPERS:
        tp = get_args(tp)[0]
    return tp


def without_none(tp: Any) -> Any:
    """`X | None` as `X`; anything else as it is"""
    if is_optional(tp):
        return next(member for member in get_args(tp) if member is not NoneType)
    return tp


def is_optional(tp: Any) -> bool:
    """`X | None` with one `X`"""
    origin = get_origin(tp)
    if origin is typing.Union or origin is UnionType:
        members = get_args(tp)
        return NoneType in members and len(members) == 2
    return False


def is_literal_choice(tp: Any) -> bool:
    """`Literal["a", "b"]`"""
    return get_origin(_plain(tp)) is Literal


def literal_choice_storage(tp: Any) -> Storage:
    """The storage of the values of a `Literal[...]`: they must all be of one native type (an enum has its
    own stored values; `Literal[Colour.RED]` is refused)"""
    values = get_args(_plain(tp))
    if not values:
        raise PanglossModelError("A Literal[...] with no values has no type")
    storages: set[str] = set()
    for value in values:
        if isinstance(value, enum.Enum):
            raise PanglossModelError(
                f"Literal[{value!r}]: a choice from an enum is the enum itself; use the enum as the type"
            )
        codec = codec_for_value(value)
        if codec is None or codec.storage not in ("str", "int", "bool"):
            raise PanglossModelError(
                f"Literal[{value!r}]: the values of a Literal must be strings, whole numbers or booleans"
            )
        storages.add(codec.storage)
    if len(storages) > 1:
        raise PanglossModelError(
            f"Literal{list(values)!r}: the values of a Literal must all be of one type"
        )
    return typing.cast(Storage, storages.pop())


def is_scalar_literal(tp: Any) -> bool:
    """A single value that is a literal: one of the codecs' types, an enum, or a `Literal[...]` (not a `TypedDict`,
    which is a map, and not a list)"""
    tp = _plain(tp)
    if is_literal_choice(tp):
        literal_choice_storage(tp)
        return True
    if isinstance(tp, type) and issubclass(tp, enum.Enum):
        if issubclass(tp, enum.Flag):
            raise PanglossModelError(
                f"{tp.__name__} is a Flag: a combination of its members is a value no member has, which the "
                "migrations of an enum cannot follow. Use an Enum, or a list of one"
            )
        return True
    return codec_for(tp) is not None


LIST_ORIGINS: tuple[type, ...] = (list, set, frozenset, tuple)


def collection_item_type(tp: Any) -> Any:
    """For a `list[X]`, `set[X]`, `frozenset[X]`, `tuple[X, ...]` or `tuple[X, X]`, the `X` (with its
    `Annotated[...]`, if it has one); else None. The items of a tuple must all be of one type."""
    tp = _plain(tp)
    origin = get_origin(tp)
    if origin not in LIST_ORIGINS:
        return None
    args = get_args(tp)
    if not args:
        return None
    if origin is tuple:
        items = [arg for arg in args if arg is not Ellipsis]
        if len({_plain(item) for item in items}) > 1:
            raise PanglossModelError(
                f"{tp!r}: the items of a tuple must all be of one type (a list is stored); "
                "for several kinds of value together, use a TypedDict or an Embedded"
            )
        return items[0]
    return args[0]


def collection_rule(tp: Any) -> dict[str, Any]:
    """What a collection says beyond being a list: `{"unique": True}` for a set, `{"length": n}` for a tuple
    of a fixed length"""
    tp = _plain(tp)
    origin = get_origin(tp)
    if origin in (set, frozenset):
        return {"unique": True}
    if origin is tuple:
        args = get_args(tp)
        if Ellipsis not in args:
            return {"length": len(args)}
    return {}


def is_literal_type(tp: Any) -> bool:
    """Whether an annotation is a literal type: a scalar, a `TypedDict` of literals (or lists of them), or `X | None`
    of one. (Not a list: see `is_list_of_literal_type`.)"""
    tp = without_none(_plain(tp))
    tp = _plain(tp)
    if is_typeddict(tp):
        return all(
            is_literal_type(value) or is_list_of_literal_type(value)
            for value in typing.get_type_hints(tp, include_extras=True).values()
        )
    return is_scalar_literal(tp)


def is_list_of_literal_type(tp: Any) -> bool:
    """A list (or set, frozenset, tuple) of a literal type, or `X | None` of one. A list whose items may be `None`
    (`list[str | None]`) is refused: a list holds values."""
    tp = without_none(_plain(tp))
    item = collection_item_type(tp)
    if item is None:
        return False
    if is_optional(_plain(item)):
        raise PanglossModelError(
            f"{tp!r}: a list cannot hold None among its items; make the whole list optional "
            f"(`{_name(tp)} | None`) or give it a default (`= []`)"
        )
    return is_literal_type(item)


def _name(tp: Any) -> str:
    return getattr(tp, "__name__", None) or repr(tp)


# --- what is said of a type -------------------------------------------------------------------------


def export_type(tp: Any) -> dict[str, Any] | None:
    """A literal type as the export writes it, or None if it is not one. An enum is described by its caller (which
    keeps the enums it met): here it is `{"type": "enum", "enum": name}`."""
    tp = _plain(tp)
    if is_optional(tp):
        return export_type(without_none(tp))
    if is_literal_choice(tp):
        return {
            "type": "literal",
            "values": [
                v.value if isinstance(v, enum.Enum) else v for v in get_args(tp)
            ],
        }
    item = collection_item_type(tp) if get_origin(tp) in LIST_ORIGINS else None
    if item is not None:
        inner = export_type(item)
        return {
            "type": "list",
            "item": inner
            if inner is not None
            else {"type": "unknown", "repr": repr(item)},
            **collection_rule(tp),
        }
    if isinstance(tp, type) and issubclass(tp, enum.Enum):
        return {"type": "enum", "enum": tp.__name__}
    if is_typeddict(tp):
        return {
            "type": "typedDict",
            "fields": {
                name: export_type(annotation)
                or {"type": "unknown", "repr": repr(annotation)}
                for name, annotation in typing.get_type_hints(
                    tp, include_extras=True
                ).items()
            },
        }
    codec = codec_for(tp)
    return codec.describe() if codec else None


def search_kind_of(tp: Any) -> SearchKind | None:
    """How a search compares a scalar literal type; None for one that cannot be compared"""
    tp = without_none(_plain(tp))
    if is_literal_choice(tp):
        return "simple"
    if isinstance(tp, type) and issubclass(tp, enum.Enum):
        return "simple"
    codec = codec_for(tp)
    return codec.search_kind if codec else None


def storage_descriptor(descriptor: dict[str, Any]) -> dict[str, Any]:
    """A type as the export writes it, reduced to what is stored: the format of a text is dropped (`{"type": "str",
    "format": "uuid"}` is a `str`), a `Literal[...]` is the type of its values, the rule of a collection
    (`unique`, `length`) is dropped. Two types that reduce to the same are stored the same, so a change
    between them is a change to the models only."""
    kind = descriptor.get("type")
    if kind == "literal":
        values = descriptor.get("values") or []
        if all(isinstance(v, bool) for v in values):
            return {"type": "bool"}
        if all(isinstance(v, int) for v in values):
            return {"type": "int"}
        return {"type": "str"}
    if kind == "list":
        return {
            "type": "list",
            "item": storage_descriptor(descriptor.get("item") or {}),
        }
    if kind == "typedDict":
        return {
            "type": "typedDict",
            "fields": {
                name: storage_descriptor(inner)
                for name, inner in (descriptor.get("fields") or {}).items()
            },
        }
    if kind == "enum":
        return {"type": "enum", "enum": descriptor.get("enum")}
    return {"type": kind}


def python_type_of_storage(descriptor: dict[str, Any]) -> type | None:
    """The Python type a stored value of a (reduced) descriptor is parsed to, for a value written in a migration
    file (`"2020-01-01"` for a date); None for a type with no single Python type (an enum, a map)"""
    return PYTHON_TYPE_OF_STORAGE.get(storage_descriptor(descriptor).get("type") or "")


# --- why a type is refused --------------------------------------------------------------------------

REFUSED: dict[type, str] = {
    dict: "a plain dict has keys the models cannot see, so a migration or a search could not follow it: "
    "use a TypedDict (a map with known keys), or an Embedded (a node of its own)",
    bytes: "the databases have no bytes type: store a base64 `str` if it is wanted",
    complex: "a complex number has no storage type: store its two parts",
    object: "a value of any type cannot be stored, searched or migrated: give it a type",
}


def explain_unsupported(tp: Any) -> str | None:
    """Why an annotation is not a literal type, where the reason can be told: a sentence to put after the
    field's name, or None for the general message"""
    tp = _plain(without_none(_plain(tp)))
    if tp is Any:
        return REFUSED[object]
    if isinstance(tp, type):
        for refused, reason in REFUSED.items():
            if tp is refused:
                return reason
        if issubclass(tp, (pydantic.SecretStr, pydantic.SecretBytes)):
            return "a secret is not something a research database stores, and serialising it hides the value"
        if hasattr(tp, "_fields") and issubclass(tp, tuple):
            return "a NamedTuple is not stored: use a TypedDict (a map), or an Embedded (a node of its own)"
        if issubclass(tp, pydantic.BaseModel) or hasattr(tp, "__dataclass_fields__"):
            return (
                "a pydantic model or a dataclass is not stored as a value: make it an Embedded (a node of its own, "
                "that can be searched into), or a TypedDict (a map on the node)"
            )
    origin = get_origin(tp)
    if origin is dict:
        return REFUSED[dict]
    if origin is typing.Union or origin is UnionType:
        members = [m for m in get_args(tp) if m is not NoneType]
        if members and all(
            is_literal_type(m) or is_list_of_literal_type(m) for m in members
        ):
            return "a union of literal types has no one storage type: pick one, or use an Embedded for each"
    return None
