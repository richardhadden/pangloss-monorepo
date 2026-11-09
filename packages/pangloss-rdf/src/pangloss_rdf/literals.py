"""A Python value as an RDF literal. The types are `pangloss_models.literals`' own, each with its datatype here once.

A package with a type of its own says its datatype with `register_datatype`."""

import datetime
import enum
import math
from collections.abc import Callable
from decimal import Decimal
import typing
from typing import Annotated, Any, get_args, get_origin

from pangloss_models.literals import (
    codec_for,
    codec_for_value,
    to_storage,
    without_none,
)

from pangloss_rdf.terms import RDF_LANG_STRING, IRI, Lit, xsd

# By what a value is stored as, and its format if that says more; a format not here is its storage
_DATATYPES: dict[tuple[str, str], IRI] = {
    ("str", ""): xsd("string"),
    ("str", "url"): xsd("anyURI"),
    ("int", ""): xsd("integer"),
    ("float", ""): xsd("double"),
    ("bool", ""): xsd("boolean"),
    ("decimal", ""): xsd("decimal"),
    ("date", ""): xsd("date"),
    ("datetime", ""): xsd("dateTime"),
    ("time", ""): xsd("time"),
    ("duration", ""): xsd("duration"),
}


def _double(value: float) -> str:
    if math.isnan(value):
        return "NaN"
    if math.isinf(value):
        return "INF" if value > 0 else "-INF"
    return repr(value)


def _decimal(value: Any) -> str:
    number = Decimal(value)
    if not number.is_finite():
        raise ValueError(f"xsd:decimal has no way of writing {value}")
    # (not `str`, which may give an exponent: xsd:decimal has none)
    return format(number, "f")


def _duration(value: datetime.timedelta) -> str:
    micros = abs(value) // datetime.timedelta(microseconds=1)
    seconds, micros = divmod(micros, 1_000_000)
    days, seconds = divmod(seconds, 86_400)
    hours, seconds = divmod(seconds, 3_600)
    minutes, seconds = divmod(seconds, 60)
    fraction = f".{micros:06d}".rstrip("0") if micros else ""
    date_part = f"{days}D" if days else ""
    time_part = "".join(
        (
            f"{hours}H" if hours else "",
            f"{minutes}M" if minutes else "",
            f"{seconds}{fraction}S" if seconds or fraction else "",
        )
    )
    if not date_part and not time_part:
        time_part = "0S"
    sign = "-" if value < datetime.timedelta(0) else ""
    return f"{sign}P{date_part}{'T' + time_part if time_part else ''}"


_LEXICAL: dict[str, Callable[[Any], str]] = {
    "str": str,
    "int": str,
    "float": _double,
    "bool": lambda value: "true" if value else "false",
    "decimal": _decimal,
    "date": lambda value: value.isoformat(),
    "datetime": lambda value: value.isoformat(),
    "time": lambda value: value.isoformat(),
    "duration": _duration,
}

_registered: list[tuple[type, IRI, Callable[[Any], str]]] = []


def register_datatype(
    python_type: type, datatype: IRI, to_lexical: Callable[[Any], str] = str
) -> None:
    """Say how values of a type are written. Asked before the table above, so a package may also change a type's"""
    _registered.insert(0, (python_type, datatype, to_lexical))


def datatype_of_type(annotation: Any) -> IRI | None:
    """The datatype of a scalar type, for the ontology; None for what is not one (a `TypedDict`, a type variable)"""
    annotation = without_none(annotation)
    while get_origin(annotation) is Annotated:
        annotation = get_args(annotation)[0]
    sample: Any = None
    if get_origin(annotation) is typing.Literal:
        sample = get_args(annotation)[0]
    elif isinstance(annotation, type) and issubclass(annotation, enum.Enum):
        sample = next(iter(annotation)).value
    if sample is not None:
        return to_literal(sample).datatype
    if isinstance(annotation, type):
        for python_type, datatype, _ in _registered:
            if issubclass(annotation, python_type):
                return datatype
    codec = codec_for(annotation)
    if codec is None:
        return None
    return (
        _DATATYPES.get((codec.storage, codec.format)) or _DATATYPES[(codec.storage, "")]
    )


def to_literal(value: Any, language: str | None = None) -> Lit:
    """`language` is for text only (`RDFField(language="la")`)"""
    if isinstance(value, enum.Enum):
        value = value.value
    if language is not None:
        if not isinstance(value, str):
            raise TypeError(f"{value!r} is not text: it cannot have a language")
        return Lit(value, RDF_LANG_STRING, language)
    for python_type, datatype, to_lexical in _registered:
        if isinstance(value, python_type):
            return Lit(to_lexical(value), datatype)
    codec = codec_for_value(value)
    if codec is None:
        raise TypeError(f"{value!r} ({type(value).__name__}) has no RDF datatype")
    datatype = (
        _DATATYPES.get((codec.storage, codec.format)) or _DATATYPES[(codec.storage, "")]
    )
    return Lit(_LEXICAL[codec.storage](to_storage(value)), datatype)
