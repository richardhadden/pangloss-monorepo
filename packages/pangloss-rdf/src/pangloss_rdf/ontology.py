"""The ontology of a project, from its models: implementation_docs/rdf-export-plan.md, §8. Needs no database."""

import typing
from collections import defaultdict
from collections.abc import Iterator
from typing import Any, is_typeddict

from pangloss_core.settings import get_settings
from pangloss_models.field_definitions import (
    AnnotatedValueFieldDefinition,
    EmbeddedFieldDefinition,
    FieldDefinition,
    FieldSubclassing,
    ListFieldDefinition,
    LiteralFieldDefinition,
    LiteralTypeVarFieldDefinition,
    RelationFieldDefinition,
    RelationToTypeVar,
)
from pangloss_models.literals import without_none
from pangloss_models.migrations.snapshot import build_snapshot, snapshot_hash
from pangloss_models.model_bases.annotated_value import AnnotatedValue
from pydantic.alias_generators import to_camel

from pangloss_rdf.convert import MIXIN_URI
from pangloss_rdf.fields import rdf_field
from pangloss_rdf.literals import datatype_of_type, to_literal
from pangloss_rdf.meta import declared_class, is_excluded
from pangloss_rdf.serialise import prefixes
from pangloss_rdf.terms import IRI, Quad
from pangloss_rdf.uris import (
    _fields,
    _registered,
    class_name,
    class_uri,
    ontology_url,
    property_name,
    property_owner,
    property_uri,
    reverse_property_uri,
)
from pangloss_rdf.vocabulary import (
    RDF_STATEMENT,
    RDF_TYPE,
    RDFS_COMMENT,
    RDFS_LABEL,
    RDFS_SUBCLASS,
    RDFS_SUBPROPERTY,
    owl,
    pgo,
    pgo_namespace,
    schema,
)


def own_fields(model: type) -> Iterator[tuple[str, FieldDefinition]]:
    """The fields a class is the owner of (the others have the property of a parent), that are exported"""
    for name, definition in _fields(model).items():
        marker = rdf_field(definition)
        if definition.db_field or (marker and marker.exclude):
            continue
        if issubclass(model, AnnotatedValue) and name == "value":
            continue
        if property_owner(model, name) is model:
            yield name, definition


def exported_models() -> list[type]:
    return [model for model in _registered() if not is_excluded(model)]


def _option_class(option: Any) -> Any:
    return getattr(option, "base_type", None) or option.annotated_type


def _uses_of_generics() -> dict[tuple[type, str], set[type]]:
    """For each type variable of a generic, what it stands for wherever the generic is used"""
    uses: dict[tuple[type, str], set[type]] = defaultdict(set)

    def visit(options: Any) -> None:
        for option in options:
            for name, parameter in (
                getattr(option, "parameter_type_options", None) or {}
            ).items():
                base = declared_class(option.base_type)
                for inner in parameter.type_options:
                    if not isinstance(inner, RelationToTypeVar):
                        uses[(base, name)].add(declared_class(_option_class(inner)))
                visit(parameter.type_options)

    for model in _registered():
        for definition in _fields(model).values():
            if isinstance(definition, RelationFieldDefinition):
                visit(definition.type_options)
    return uses


def _ranges(definition: RelationFieldDefinition, uses: dict) -> set[type]:
    found: set[type] = set()
    for option in definition.type_options:
        if isinstance(option, RelationToTypeVar):
            found |= uses.get(
                (declared_class(definition.field_on_model), option.type_var_name), set()
            )
        else:
            found.add(declared_class(_option_class(option)))
    return found


def _hints(annotation: Any) -> Any:
    annotation = without_none(annotation)
    args = typing.get_args(annotation)
    if typing.get_origin(annotation) in (list, set, frozenset, tuple) and args:
        return _hints(args[0])
    return annotation


def _map_keys(uri: IRI, annotation: Any) -> Iterator[Quad]:
    """The properties of a `TypedDict`"""
    for key, hint in typing.get_type_hints(annotation).items():
        predicate = IRI(f"{uri}.{to_camel(key)}")
        inner = _hints(hint)
        if is_typeddict(inner):
            yield Quad(predicate, RDF_TYPE, owl("ObjectProperty"))
            yield from _map_keys(predicate, inner)
            continue
        yield Quad(predicate, RDF_TYPE, owl("DatatypeProperty"))
        datatype = datatype_of_type(inner)
        if datatype is not None:
            yield Quad(predicate, schema("rangeIncludes"), datatype)


def _property(
    model: type, name: str, definition: FieldDefinition, uses: dict
) -> Iterator[Quad]:
    uri = property_uri(model, name)
    marker = rdf_field(definition)
    yield Quad(uri, RDFS_LABEL, to_literal(name))
    yield Quad(uri, schema("domainIncludes"), class_uri(model))
    if definition.description:
        yield Quad(uri, RDFS_COMMENT, to_literal(definition.description))
    for parent in marker.parent if marker else ():
        yield Quad(uri, RDFS_SUBPROPERTY, IRI(parent.uri))
    match definition:
        case RelationFieldDefinition():
            yield Quad(uri, RDF_TYPE, owl("ObjectProperty"))
            for target in _ranges(definition, uses):
                if not is_excluded(target):
                    yield Quad(uri, schema("rangeIncludes"), class_uri(target))
            for narrowed in definition.subclasses_parent_fields:
                yield Quad(uri, RDFS_SUBPROPERTY, _narrowed(model, narrowed))
            reverse = reverse_property_uri(model, name)
            yield Quad(reverse, RDF_TYPE, owl("ObjectProperty"))
            yield Quad(reverse, RDFS_LABEL, to_literal(definition.reverse_name))
            yield Quad(reverse, owl("inverseOf"), uri)
        case EmbeddedFieldDefinition():
            yield Quad(uri, RDF_TYPE, owl("ObjectProperty"))
            for option in definition.type_options:
                yield Quad(
                    uri, schema("rangeIncludes"), class_uri(option.annotated_type)
                )
        case AnnotatedValueFieldDefinition():
            yield Quad(uri, RDF_TYPE, owl("ObjectProperty"))
            yield Quad(
                uri, schema("rangeIncludes"), class_uri(definition.annotated_type)
            )
        case LiteralFieldDefinition() | ListFieldDefinition():
            annotation = _hints(
                definition.inner_type
                if isinstance(definition, ListFieldDefinition)
                else definition.annotated_type
            )
            if is_typeddict(annotation):
                yield Quad(uri, RDF_TYPE, owl("ObjectProperty"))
                yield Quad(uri, schema("rangeIncludes"), pgo("Map"))
                yield from _map_keys(uri, annotation)
                return
            yield Quad(uri, RDF_TYPE, owl("DatatypeProperty"))
            datatype = datatype_of_type(annotation)
            if datatype is not None:
                yield Quad(uri, schema("rangeIncludes"), datatype)
        case LiteralTypeVarFieldDefinition():
            yield Quad(uri, RDF_TYPE, owl("DatatypeProperty"))


def _narrowed(model: type, narrowed: str | FieldSubclassing) -> IRI:
    if isinstance(narrowed, str):
        return property_uri(model, narrowed)
    return property_uri(narrowed.field_on_model, narrowed.field_name)


def _class(model: type, registered: set[type], uses: dict) -> Iterator[Quad]:
    uri = class_uri(model)
    yield Quad(uri, RDF_TYPE, owl("Class"))
    yield Quad(uri, RDFS_LABEL, to_literal(model.__name__))
    if model.__doc__:
        yield Quad(uri, RDFS_COMMENT, to_literal(model.__doc__.strip()))
    kind = getattr(model, "__metatype__", None)
    if kind is not None:
        yield Quad(uri, RDFS_SUBCLASS, pgo(kind))
    for base in model.__bases__:
        declared = declared_class(base)
        if declared in registered and not is_excluded(declared):
            yield Quad(uri, RDFS_SUBCLASS, class_uri(declared))
        elif MIXIN_URI in base.__dict__:
            yield Quad(uri, RDFS_SUBCLASS, IRI(base.__dict__[MIXIN_URI]))
    for name, definition in own_fields(model):
        yield from _property(model, name, definition, uses)


CORE_CLASSES = (
    "AnnotatedValue",
    "Conjunction",
    "Document",
    "EdgeModel",
    "Embedded",
    "Entity",
    "Map",
    "ReifiedRelation",
    "ReifiedRelationDocument",
    "SemanticSpace",
)
CORE_OBJECT_PROPERTIES = ("edge", "partOf", "inSpace", "referencedBy")
CORE_DATA_PROPERTIES = (
    "position",
    "version",
    "referenceCount",
    "reviewStatus",
    "earliest",
    "earliestStrict",
    "latestStrict",
    "latest",
)


def core_quads() -> Iterator[Quad]:
    """The terms every export uses, whatever the models: defined here, as they are the project's own"""
    yield Quad(pgo("Edge"), RDF_TYPE, owl("Class"))
    yield Quad(pgo("Edge"), RDFS_SUBCLASS, RDF_STATEMENT)
    for name in CORE_CLASSES:
        yield Quad(pgo(name), RDF_TYPE, owl("Class"))
    for name in CORE_OBJECT_PROPERTIES:
        yield Quad(pgo(name), RDF_TYPE, owl("ObjectProperty"))
    for name in CORE_DATA_PROPERTIES:
        yield Quad(pgo(name), RDF_TYPE, owl("DatatypeProperty"))


def ontology_address() -> IRI:
    return IRI(ontology_url().rstrip("/#"))


def ontology_quads() -> Iterator[Quad]:
    address = ontology_address()
    settings = get_settings()
    yield Quad(address, RDF_TYPE, owl("Ontology"))
    yield Quad(address, RDFS_LABEL, to_literal(settings.PROJECT_NAME))
    yield Quad(address, owl("versionInfo"), to_literal(snapshot_hash(build_snapshot())))
    if getattr(settings, "RDF_CORE_URL", None) is None:
        yield from core_quads()
    else:
        # (given elsewhere, and shared: what is at that address defines the terms)
        yield Quad(address, owl("imports"), IRI(pgo_namespace().rstrip("#/")))
    uses = _uses_of_generics()
    models = exported_models()
    registered = set(models)
    for model in models:
        yield from _class(model, registered, uses)


def jsonld_context() -> dict[str, Any]:
    context: dict[str, Any] = dict(prefixes())
    for model in exported_models():
        context[class_name(model)] = class_uri(model).value
        for name, definition in own_fields(model):
            term = property_name(model, name)
            entry: dict[str, str] = {"@id": property_uri(model, name).value}
            if isinstance(
                definition,
                (
                    RelationFieldDefinition,
                    EmbeddedFieldDefinition,
                    AnnotatedValueFieldDefinition,
                ),
            ):
                entry["@type"] = "@id"
            elif isinstance(definition, LiteralFieldDefinition):
                datatype = datatype_of_type(definition.annotated_type)
                marker = rdf_field(definition)
                if datatype is not None and not (marker and marker.language):
                    entry["@type"] = datatype.value
            context[term] = entry
    return context
