"""Optional RDF export for Pangloss. See docs/rdf-export-plan.md

A project's models import this package, so it has to import on an SDK client: no server package, and no RDF library,
at module level."""

lazy from pangloss_rdf.context import Context
lazy from pangloss_rdf.convert import convert, register_rdf_converter
lazy from pangloss_rdf.fields import OntologyProperty, RDFField
lazy from pangloss_rdf.literals import register_datatype, to_literal
lazy from pangloss_rdf.meta import RDFMeta
lazy from pangloss_rdf.terms import IRI, Lit, Quad
lazy from pangloss_rdf.uris import (
    check_models,
    class_uri,
    edge_uri,
    item_uri,
    property_uri,
    reverse_property_uri,
    value_uri,
)

__all__ = [
    "check_models",
    "class_uri",
    "Context",
    "convert",
    "edge_uri",
    "IRI",
    "item_uri",
    "Lit",
    "OntologyProperty",
    "property_uri",
    "Quad",
    "RDFField",
    "RDFMeta",
    "register_datatype",
    "register_rdf_converter",
    "reverse_property_uri",
    "to_literal",
    "value_uri",
]
