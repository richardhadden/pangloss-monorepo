import datetime
import enum
import ipaddress
import pathlib
import re
import uuid
from decimal import Decimal
from fractions import Fraction

import pytest
from pangloss_rdf import IRI, Lit, register_datatype, to_literal
from pangloss_rdf import literals as module
from pangloss_rdf.terms import RDF_LANG_STRING, xsd
from pydantic import AnyHttpUrl


class Colour(enum.Enum):
    RED = "red"


class Rank(enum.IntEnum):
    HIGH = 3


UTC = datetime.timezone.utc


@pytest.mark.parametrize(
    ("value", "lexical", "datatype"),
    [
        ("text", "text", "string"),
        (3, "3", "integer"),
        (True, "true", "boolean"),
        (False, "false", "boolean"),
        (1.5, "1.5", "double"),
        (float("inf"), "INF", "double"),
        (float("-inf"), "-INF", "double"),
        (float("nan"), "NaN", "double"),
        (Decimal("1E+3"), "1000", "decimal"),
        (Decimal("12.50"), "12.50", "decimal"),
        (datetime.date(1500, 2, 3), "1500-02-03", "date"),
        (
            datetime.datetime(1500, 2, 3, 4, 5, tzinfo=UTC),
            "1500-02-03T04:05:00+00:00",
            "dateTime",
        ),
        (datetime.time(4, 5), "04:05:00", "time"),
        (AnyHttpUrl("https://a.org/b"), "https://a.org/b", "anyURI"),
        (uuid.UUID(int=1), "00000000-0000-0000-0000-000000000001", "string"),
        (ipaddress.ip_address("127.0.0.1"), "127.0.0.1", "string"),
        (pathlib.PurePosixPath("/a/b"), "/a/b", "string"),
        (re.compile("a+"), "a+", "string"),
        (Fraction(1, 3), "1/3", "string"),
        (Colour.RED, "red", "string"),
        (Rank.HIGH, "3", "integer"),
    ],
)
def test_a_value_has_its_datatype(value, lexical, datatype):
    assert to_literal(value) == Lit(lexical, xsd(datatype))


@pytest.mark.parametrize(
    ("value", "lexical"),
    [
        (datetime.timedelta(0), "PT0S"),
        (datetime.timedelta(days=1), "P1D"),
        (datetime.timedelta(days=1, hours=2, minutes=30), "P1DT2H30M"),
        (datetime.timedelta(seconds=1, microseconds=500000), "PT1.5S"),
        (datetime.timedelta(microseconds=1), "PT0.000001S"),
        (datetime.timedelta(hours=-1), "-PT1H"),
    ],
)
def test_a_duration_is_in_the_form_xsd_has(value, lexical):
    assert to_literal(value) == Lit(lexical, xsd("duration"))


def test_text_can_have_a_language():
    assert to_literal("rex", language="la") == Lit("rex", RDF_LANG_STRING, "la")


def test_only_text_can_have_a_language():
    with pytest.raises(TypeError, match="cannot have a language"):
        to_literal(3, language="la")


def test_a_decimal_with_no_value_is_refused():
    with pytest.raises(ValueError, match="xsd:decimal"):
        to_literal(Decimal("NaN"))


def test_a_value_with_no_datatype_is_refused():
    with pytest.raises(TypeError, match="no RDF datatype"):
        to_literal(object())


def test_a_package_can_say_the_datatype_of_its_type(monkeypatch):
    monkeypatch.setattr(module, "_registered", [])

    class Shelfmark:
        def __str__(self):
            return "MS 1"

    datatype = IRI("https://example.org/shelfmark")
    register_datatype(Shelfmark, datatype)
    assert to_literal(Shelfmark()) == Lit("MS 1", datatype)
