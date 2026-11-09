"""The terms of RDF, as plain values: what a conversion gives, whichever serialiser writes it"""

import re
from dataclasses import dataclass

# (what an IRI may not hold: a serialiser would write something that cannot be read back)
_IRI = re.compile(r"[a-zA-Z][a-zA-Z0-9+.-]*:[^\x00-\x20<>\"{}|\\^`]*")


@dataclass(frozen=True, slots=True)
class IRI:
    value: str

    def __post_init__(self) -> None:
        if not _IRI.fullmatch(self.value):
            raise ValueError(f"{self.value!r} is not an absolute IRI")

    def __str__(self) -> str:
        return self.value


RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
XSD_NS = "http://www.w3.org/2001/XMLSchema#"

RDF_LANG_STRING = IRI(f"{RDF_NS}langString")


def xsd(name: str) -> IRI:
    return IRI(f"{XSD_NS}{name}")


@dataclass(frozen=True, slots=True)
class Lit:
    lexical: str
    datatype: IRI
    language: str | None = None


@dataclass(frozen=True, slots=True)
class Quad:
    subject: IRI
    predicate: IRI
    object: IRI | Lit
    graph: IRI | None = None
