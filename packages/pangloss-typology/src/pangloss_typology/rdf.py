"""What `pangloss_rdf` writes for a type of a typology, beyond its fields: a SKOS concept. Found by name; only imported by that package."""

from collections.abc import Iterator
from typing import Any

from pangloss_models import Entity
from pangloss_rdf import (
    IRI,
    Quad,
    class_uri,
    item_uri,
    register_rdf_converter,
    to_literal,
)
from pangloss_rdf.context import Context
from pangloss_rdf.vocabulary import RDF_TYPE, skos

from pangloss_typology.typology import IS_SUBTYPE_OF


def convert_type(value: Any, uri: IRI, context: Context) -> Iterator[Quad]:
    owner = value._owner
    if IS_SUBTYPE_OF not in owner._meta.fields:
        return
    yield context.quad(uri, RDF_TYPE, skos("Concept"))
    yield context.quad(uri, skos("prefLabel"), to_literal(value.label))
    yield context.quad(uri, skos("inScheme"), class_uri(owner))
    supertype = getattr(value, IS_SUBTYPE_OF, None)
    for parent in (
        supertype if isinstance(supertype, list) else [supertype] if supertype else []
    ):
        yield context.quad(uri, skos("broader"), item_uri(parent._owner, parent.id))


register_rdf_converter(Entity, convert_type)
