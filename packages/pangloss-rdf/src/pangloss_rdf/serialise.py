"""Quads as text. The line formats are written here; the others by rdflib, imported only when one is asked for, so that
a project's models can be shipped in the SDK without it."""

from collections.abc import Iterable
from dataclasses import dataclass

from pangloss_rdf.fields import ontology_prefixes
from pangloss_rdf.terms import IRI, Lit, Quad, xsd
from pangloss_rdf.uris import ontology_url
from pangloss_rdf.vocabulary import (
    DCTERMS_NS,
    OWL_NS,
    RDFS_NS,
    SCHEMA_NS,
    SH_NS,
    SKOS_NS,
    VOID_NS,
    core_prefix,
    ontology_prefix,
    pgo_namespace,
)


@dataclass(frozen=True)
class Format:
    name: str
    media_type: str
    rdflib: str | None = None
    extension: str = ""


FORMATS: dict[str, Format] = {
    "ttl": Format("ttl", "text/turtle", "turtle", "ttl"),
    "trig": Format("trig", "application/trig", "trig", "trig"),
    "jsonld": Format("jsonld", "application/ld+json", "json-ld", "jsonld"),
    "nt": Format("nt", "application/n-triples", None, "nt"),
    "nq": Format("nq", "application/n-quads", None, "nq"),
}

_XSD_STRING = xsd("string")

_ESCAPES = {
    "\\": "\\\\",
    '"': '\\"',
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
    "\b": "\\b",
    "\f": "\\f",
}


def _escape(text: str) -> str:
    out = []
    for char in text:
        if char in _ESCAPES:
            out.append(_ESCAPES[char])
        elif ord(char) < 0x20 or ord(char) == 0x7F:
            out.append(f"\\u{ord(char):04X}")
        else:
            out.append(char)
    return "".join(out)


def _term(term: IRI | Lit) -> str:
    if isinstance(term, IRI):
        return f"<{term.value}>"
    text = f'"{_escape(term.lexical)}"'
    if term.language:
        return f"{text}@{term.language}"
    if term.datatype == _XSD_STRING:
        return text
    return f"{text}^^<{term.datatype.value}>"


def line(quad: Quad, with_graph: bool = True) -> str:
    parts = [_term(quad.subject), _term(quad.predicate), _term(quad.object)]
    if with_graph and quad.graph is not None:
        parts.append(_term(quad.graph))
    return " ".join(parts) + " .\n"


def prefixes() -> dict[str, str]:
    """(an outside ontology's own prefix gives way to one of these)"""
    return ontology_prefixes() | {
        ontology_prefix(): ontology_url(),
        core_prefix(): pgo_namespace(),
        "rdfs": RDFS_NS,
        "owl": OWL_NS,
        "dcterms": DCTERMS_NS,
        "skos": SKOS_NS,
        "schema": SCHEMA_NS,
        "sh": SH_NS,
        "void": VOID_NS,
    }


def _rdflib_term(term: IRI | Lit):
    from rdflib import Literal, URIRef

    if isinstance(term, IRI):
        return URIRef(term.value)
    if term.language:
        return Literal(term.lexical, lang=term.language)
    if term.datatype == _XSD_STRING:
        return Literal(term.lexical)
    # (as written: rdflib would otherwise put a value in its own canonical form)
    return Literal(term.lexical, datatype=URIRef(term.datatype.value), normalize=False)


def serialise(quads: Iterable[Quad], format: str, context: dict | None = None) -> str:
    """`context`: of a JSON-LD document, for which the terms are compacted"""
    chosen = FORMATS[format]
    if chosen.rdflib is None:
        with_graph = format == "nq"
        return "".join(sorted({line(quad, with_graph) for quad in quads}))

    from rdflib import Dataset, Graph, URIRef

    if format == "ttl":
        # (Turtle has no graphs: everything in one)
        target = Graph()
        for quad in quads:
            target.add(
                (
                    _rdflib_term(quad.subject),
                    _rdflib_term(quad.predicate),
                    _rdflib_term(quad.object),
                )
            )
    else:
        target = Dataset(default_union=False)
        for quad in quads:
            graph = (
                target.graph(URIRef(quad.graph.value))
                if quad.graph is not None
                else target.default_graph
            )
            graph.add(
                (
                    _rdflib_term(quad.subject),
                    _rdflib_term(quad.predicate),
                    _rdflib_term(quad.object),
                )
            )
    for prefix, namespace in prefixes().items():
        target.bind(prefix, namespace)
    if format == "jsonld":
        return target.serialize(
            format="json-ld", context=context or prefixes(), auto_compact=True
        )
    return target.serialize(format=chosen.rdflib)
