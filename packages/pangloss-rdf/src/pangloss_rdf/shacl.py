"""SHACL shapes, from the same definitions as the ontology: what generated data must conform to.

A relation or an embedded object has no `sh:minCount`: inside a semantic space its direct triple is withheld."""

from collections.abc import Iterator
from typing import is_typeddict

from pangloss_models.field_definitions import (
    AnnotatedValueFieldDefinition,
    EmbeddedFieldDefinition,
    FieldDefinition,
    ListFieldDefinition,
    LiteralFieldDefinition,
    RelationFieldDefinition,
)
from pangloss_models.literals import is_optional

from pangloss_rdf.fields import rdf_field
from pangloss_rdf.literals import datatype_of_type, to_literal
from pangloss_rdf.ontology import _hints, exported_models, own_fields
from pangloss_rdf.terms import IRI, Quad
from pangloss_rdf.uris import class_name, class_uri, ontology_url, property_uri
from pangloss_rdf.vocabulary import RDF_TYPE, sh


def _bounds(definition: FieldDefinition) -> tuple[int, int | None]:
    """(sh:minCount, sh:maxCount)"""
    match definition:
        case RelationFieldDefinition():
            return 0, None if definition.wrapper is not None else 1
        case EmbeddedFieldDefinition():
            return 0, 1
        case AnnotatedValueFieldDefinition():
            return 0, None if definition.many else 1
        case ListFieldDefinition():
            return 0, None
        case LiteralFieldDefinition():
            required = not (
                definition.has_default or is_optional(definition.annotated_type)
            )
            return (1 if required else 0), 1
    return 0, None


def _datatype(definition: FieldDefinition) -> IRI | None:
    marker = rdf_field(definition)
    if marker and (marker.language or marker.ordered):
        return None
    if isinstance(definition, ListFieldDefinition):
        annotation = _hints(definition.inner_type)
    elif isinstance(definition, LiteralFieldDefinition):
        annotation = _hints(definition.annotated_type)
    else:
        return None
    return None if is_typeddict(annotation) else datatype_of_type(annotation)


def shape_quads() -> Iterator[Quad]:
    for model in exported_models():
        fields = list(own_fields(model))
        if not fields:
            continue
        shape = IRI(f"{ontology_url()}shape/{class_name(model)}")
        yield Quad(shape, RDF_TYPE, sh("NodeShape"))
        yield Quad(shape, sh("targetClass"), class_uri(model))
        for name, definition in fields:
            part = IRI(f"{shape}/{name}")
            yield Quad(shape, sh("property"), part)
            yield Quad(part, sh("path"), property_uri(model, name))
            minimum, maximum = _bounds(definition)
            if minimum:
                yield Quad(part, sh("minCount"), to_literal(minimum))
            if maximum is not None:
                yield Quad(part, sh("maxCount"), to_literal(maximum))
            datatype = _datatype(definition)
            if datatype is not None:
                yield Quad(part, sh("datatype"), datatype)
