"""A read document or entity as RDF: docs/rdf-export-plan.md, §4.

Walks a `HeadView` by the field definitions of its model, and gives `Quad`s. Knows no database.
"""

import importlib
from collections.abc import Callable, Iterable, Iterator
from typing import Any

from pangloss_core.settings import get_settings
from pangloss_models import ModelRegistry
from pangloss_models.field_definitions import (
    AnnotatedValueFieldDefinition,
    EmbeddedFieldDefinition,
    FieldDefinition,
    ListFieldDefinition,
    LiteralFieldDefinition,
    LiteralTypeVarFieldDefinition,
    RelationFieldDefinition,
)
from pangloss_models.model_bases.labels import labels_for_model
from pydantic.alias_generators import to_camel

from pangloss_rdf.context import Context
from pangloss_rdf.fields import RDFField, rdf_field
from pangloss_rdf.literals import to_literal
from pangloss_rdf.meta import declared_class, is_excluded
from pangloss_rdf.terms import IRI, Quad
from pangloss_rdf.uris import (
    class_uri,
    edge_uri,
    item_uri,
    property_name,
    property_uri,
    value_uri,
)
from pangloss_rdf.vocabulary import (
    OWL_SAME_AS,
    RDF_FIRST,
    RDF_NIL,
    RDF_OBJECT,
    RDF_PREDICATE,
    RDF_REST,
    RDF_SUBJECT,
    RDF_TYPE,
    RDF_VALUE,
    RDFS_LABEL,
    dcterms,
    pgo,
)

# The attribute of an outside class that says what it is (the classes in `pangloss_rdf.ontologies`)
MIXIN_URI = "_rdf_uri"

Converter = Callable[[Any, IRI, Context], Iterable[Quad]]

_converters: list[tuple[type, Converter, bool]] = []
_apps_loaded: set[str] = set()


def register_rdf_converter(
    model: type, converter: Converter, replace: bool = False
) -> None:
    """Add to what is written for nodes of a class and its subclasses, or with `replace`, write that instead of their
    fields. A package does this in an `rdf.py` module, found by name in `INSTALLED_APPS`, so it need not depend on this one"""
    _converters.insert(0, (model, converter, replace))


def load_app_converters() -> None:
    """Import each installed app's `rdf.py`, once"""
    for app in getattr(get_settings(), "INSTALLED_APPS", ()):
        if app in _apps_loaded:
            continue
        _apps_loaded.add(app)
        try:
            importlib.import_module(f"{app}.rdf")
        except ModuleNotFoundError as error:
            if error.name not in (app, f"{app}.rdf"):
                raise


def outside_classes(model: type) -> list[IRI]:
    """The classes of other ontologies a model has mixed in: the nearest only, as that ontology knows their parents"""
    found = [c for c in model.__mro__ if MIXIN_URI in c.__dict__]
    nearest = [
        c for c in found if not any(o is not c and issubclass(o, c) for o in found)
    ]
    return [IRI(c.__dict__[MIXIN_URI]) for c in nearest]


def pangloss_classes(model: type) -> list[type]:
    """The class and its parents and traits, as the node's labels have them"""
    model = declared_class(model)
    models = ModelRegistry.all_models()
    names = labels_for_model(model, "")[:-1]  # ty: ignore[invalid-argument-type]
    return [
        models[name]
        for name in names
        if name in models and not is_excluded(models[name])
    ]


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple, set, frozenset)):
        return list(value)
    return [value]


class _Walk:
    def __init__(self, head: IRI) -> None:
        self.head = head

    def node(self, value: Any, uri: IRI, context: Context) -> Iterator[Quad]:
        owner = declared_class(value._owner)
        for cls in pangloss_classes(owner):
            yield context.quad(uri, RDF_TYPE, class_uri(cls))
        kind = value.__metatype__
        yield context.quad(uri, RDF_TYPE, pgo(kind))
        if context.asserted:
            for outside in outside_classes(owner):
                yield context.quad(uri, RDF_TYPE, outside)
        for space in context.spaces:
            yield context.quad(uri, pgo("inSpace"), space)
        label = getattr(value, "label", None)
        if label is not None:
            yield context.quad(uri, RDFS_LABEL, to_literal(label))
        converters = [c for c in _converters if issubclass(owner, c[0])]
        if not any(replace for _, _, replace in converters):
            yield from self.fields(value, owner, uri, context)
        for _, converter, _ in converters:
            yield from converter(value, uri, context)

    def fields(
        self, value: Any, owner: type, uri: IRI, context: Context
    ) -> Iterator[Quad]:
        meta = value._owner._meta
        inner = context
        if value.__metatype__ == "SemanticSpace":
            inner = Context(context.graph, (*context.spaces, uri))
        for name, definition in meta.fields.items():
            marker = rdf_field(definition)
            if definition.db_field or (marker and marker.exclude):
                continue
            found = getattr(value, name, None)
            if found is None:
                continue
            match definition:
                case RelationFieldDefinition():
                    yield from self.relation(
                        owner, name, marker, found, uri, context, inner
                    )
                case EmbeddedFieldDefinition():
                    yield from self.embedded(owner, name, marker, found, uri, context)
                case AnnotatedValueFieldDefinition():
                    yield from self.annotated(owner, name, marker, found, uri, context)
                case (
                    LiteralFieldDefinition()
                    | ListFieldDefinition()
                    | LiteralTypeVarFieldDefinition()
                ):
                    yield from self.literal(owner, name, marker, found, uri, context)
                case _:
                    _unknown(definition)

    def edge(
        self,
        subject: IRI,
        predicate: IRI,
        name: str,
        target: IRI,
        position: int,
        context: Context,
    ) -> tuple[IRI, Iterator[Quad]]:
        uri = edge_uri(subject, name, position)

        def quads() -> Iterator[Quad]:
            yield context.quad(subject, pgo("edge"), uri)
            yield context.quad(uri, RDF_TYPE, pgo("Edge"))
            yield context.quad(uri, RDF_SUBJECT, subject)
            yield context.quad(uri, RDF_PREDICATE, predicate)
            yield context.quad(uri, RDF_OBJECT, target)
            yield context.quad(uri, pgo("position"), to_literal(position))

        return uri, quads()

    def relation(
        self,
        owner: type,
        name: str,
        marker: RDFField | None,
        found: Any,
        subject: IRI,
        context: Context,
        inner: Context,
    ) -> Iterator[Quad]:
        predicate = property_uri(owner, name)
        local = property_name(owner, name)
        for position, value in enumerate(_as_list(found)):
            if is_excluded(value._owner):
                continue
            target = item_uri(value._owner, value.id)
            if context.asserted:
                yield context.quad(subject, predicate, target)
                for aligned in marker.parent if marker else ():
                    for reached in self.aligned_targets(value):
                        yield context.quad(subject, IRI(aligned.uri), reached)
            edge, quads = self.edge(subject, predicate, local, target, position, inner)
            yield from quads
            yield from self.edge_properties(value, edge, inner)
            yield from self.target(value, target, inner)

    def edge_properties(
        self, value: Any, edge: IRI, context: Context
    ) -> Iterator[Quad]:
        properties = getattr(value, "edge_properties", None)
        if properties is None:
            return
        model = type(properties)
        for field in model._meta.fields:
            found = getattr(properties, field, None)
            if found is not None:
                yield context.quad(edge, property_uri(model, field), to_literal(found))

    def target(self, value: Any, uri: IRI, context: Context) -> Iterator[Quad]:
        kind = value.__metatype__
        if kind == "Entity":
            # (what a chip shows: what else is said of it is in its own export)
            yield context.quad(uri, RDF_TYPE, class_uri(value._owner))
            yield context.quad(uri, RDFS_LABEL, to_literal(value.label))
            return
        if kind in ("Document", "ReifiedRelationDocument"):
            yield context.quad(uri, pgo("partOf"), self.head)
        yield from self.node(value, uri, context)

    def aligned_targets(self, value: Any) -> Iterator[IRI]:
        """What an outside property reaches: through a reified relation to what it is about; never through a semantic
        space or a conjunction, where the value is not simply so"""
        kind = value.__metatype__
        if kind in ("SemanticSpace", "Conjunction"):
            return
        if kind in ("ReifiedRelation", "ReifiedRelationDocument"):
            for inner in _as_list(getattr(value, "target", None) or ()):
                yield from self.aligned_targets(inner)
            return
        yield item_uri(value._owner, value.id)

    def embedded(
        self,
        owner: type,
        name: str,
        marker: RDFField | None,
        found: Any,
        subject: IRI,
        context: Context,
    ) -> Iterator[Quad]:
        predicate = property_uri(owner, name)
        local = property_name(owner, name)
        uri = value_uri(subject, local)
        if context.asserted:
            yield context.quad(subject, predicate, uri)
            for aligned in marker.parent if marker else ():
                yield context.quad(subject, IRI(aligned.uri), uri)
        _, quads = self.edge(subject, predicate, local, uri, 0, context)
        yield from quads
        yield from self.node(found, uri, context)

    def annotated(
        self,
        owner: type,
        name: str,
        marker: RDFField | None,
        found: Any,
        subject: IRI,
        context: Context,
    ) -> Iterator[Quad]:
        predicate = property_uri(owner, name)
        local = property_name(owner, name)
        many = isinstance(found, (list, tuple))
        language = marker.language if marker else None
        for position, value in enumerate(_as_list(found)):
            uri = value_uri(subject, local, position if many else None)
            model = type(value)
            yield context.quad(subject, predicate, uri)
            yield context.quad(uri, RDF_TYPE, class_uri(model))
            for inner in _as_list(value.value):
                literal = to_literal(inner, language)
                yield context.quad(uri, RDF_VALUE, literal)
                if context.asserted:
                    for aligned in marker.parent if marker else ():
                        yield context.quad(subject, IRI(aligned.uri), literal)
            for field in model._meta.fields:
                extra = getattr(value, field, None)
                if field == "value" or extra is None:
                    continue
                yield from self.annotated_extra(model, field, extra, uri, context)

    def annotated_extra(
        self, model: type, field: str, extra: Any, uri: IRI, context: Context
    ) -> Iterator[Quad]:
        predicate = property_uri(model, field)
        for item in _as_list(extra):
            yield context.quad(uri, predicate, to_literal(item))

    def literal(
        self,
        owner: type,
        name: str,
        marker: RDFField | None,
        found: Any,
        subject: IRI,
        context: Context,
    ) -> Iterator[Quad]:
        predicate = property_uri(owner, name)
        local = property_name(owner, name)
        language = marker.language if marker else None
        values = _as_list(found)
        if marker and marker.ordered and isinstance(found, (list, tuple)):
            yield from self.rdf_list(
                subject, predicate, local, values, language, context
            )
            return
        many = len(values) > 1
        for position, value in enumerate(values):
            if isinstance(value, dict):
                uri = value_uri(subject, local, position if many else None)
                yield context.quad(subject, predicate, uri)
                yield from self.map(predicate, value, uri, context)
                continue
            literal = to_literal(value, language)
            yield context.quad(subject, predicate, literal)
            if context.asserted:
                for aligned in marker.parent if marker else ():
                    yield context.quad(subject, IRI(aligned.uri), literal)

    def rdf_list(
        self,
        subject: IRI,
        predicate: IRI,
        local: str,
        values: list[Any],
        language: str | None,
        context: Context,
    ) -> Iterator[Quad]:
        if not values:
            yield context.quad(subject, predicate, RDF_NIL)
            return
        cells = [value_uri(subject, f"{local}.list", i) for i in range(len(values))]
        yield context.quad(subject, predicate, cells[0])
        for i, value in enumerate(values):
            yield context.quad(cells[i], RDF_FIRST, to_literal(value, language))
            rest = cells[i + 1] if i + 1 < len(cells) else RDF_NIL
            yield context.quad(cells[i], RDF_REST, rest)

    def map(
        self, parent: IRI, value: dict[str, Any], uri: IRI, context: Context
    ) -> Iterator[Quad]:
        """A `TypedDict`"""
        yield context.quad(uri, RDF_TYPE, pgo("Map"))
        for key, item in value.items():
            if item is None:
                continue
            predicate = IRI(f"{parent}.{to_camel(key)}")
            items = _as_list(item)
            for position, inner in enumerate(items):
                if isinstance(inner, dict):
                    place = value_uri(
                        uri, to_camel(key), position if len(items) > 1 else None
                    )
                    yield context.quad(uri, predicate, place)
                    yield from self.map(predicate, inner, place, context)
                else:
                    yield context.quad(uri, predicate, to_literal(inner))


def _unknown(definition: FieldDefinition) -> None:
    raise TypeError(
        f"{definition.field_on_model.__name__}.{definition.field_name}: "
        f"no RDF for a {type(definition).__name__}"
    )


def users_exposed() -> bool:
    return bool(getattr(get_settings(), "RDF_EXPOSE_USERS", True))


def provenance(item: Any, head: IRI) -> Iterator[Quad]:
    """What is known of the graph, in the default graph: who says this, and when"""
    meta = getattr(item, "meta", None)
    if meta is None:
        return
    version = getattr(meta, "version", None)
    if version is not None:
        yield Quad(head, pgo("version"), to_literal(version))
    for field, term, is_user in (
        ("created_by", "creator", True),
        ("updated_by", "contributor", True),
        ("created_when", "created", False),
        ("updated_when", "modified", False),
    ):
        found = getattr(meta, field, None)
        if found is None or (is_user and not users_exposed()):
            continue
        yield Quad(head, dcterms(term), to_literal(found))
    status = getattr(meta, "review_status", None)
    if status is not None:
        yield Quad(head, pgo("reviewStatus"), to_literal(status))


def convert(item: Any) -> Iterator[Quad]:
    """The quads of a document or an entity, as read (`Model.get`): its graph, and what is known of it"""
    load_app_converters()
    head = item_uri(item._owner, item.id)
    context = Context(head)
    yield from provenance(item, head)
    yield from _Walk(head).node(item, head, context)
    for url in getattr(item, "urls", None) or ():
        yield context.quad(head, OWL_SAME_AS, IRI(str(url)))


__all__ = [
    "Context",
    "Converter",
    "convert",
    "load_app_converters",
    "register_rdf_converter",
]
