"""Derived edges as RDF, for `pangloss_rdf`: a part of a dump it adds only when asked (`pangloss rdf dump
--include-derived`), and the terms of the ontology that go with it. Found by name; only imported by that package.

An edge is written as `pangloss_rdf` writes a relation of a document (implementation_docs/rdf.md): a direct triple,
and a node that is the statement of it.

    <A> :sameGroup <B> .                                      # only if a justification the reader sees is plain
    <…/derived/SameGroup/KEY> a pgo:DerivedEdge, :SameGroup ;
        rdf:subject <A> ; rdf:predicate :sameGroup ; rdf:object <B> ;
        :SameGroup.group <G> ;                                # its qualifiers
        pgo:plain true ; pgo:justificationCount 2 ; pgo:context "Negative" ;
        pgo:derivedStatus "reported" ;                       # unless it is plain and asserted
        pgo:justifiedBy <…/Factoid/F1>, <…/Factoid/F2> .     # the documents it rests on

All of it is what the reader of the dump may know: only justifications resting on documents they see are counted,
and an edge none of whose justifications is plain has no direct triple (what is only said in a `Negative` is not
asserted). What its justifications say, summed up (`pgo:derivedStatus`: contested, reported, prescribed, denied,
nothing; `pangloss_derived.status.summed`), is written of an edge that is not plain, and of a plain one that is
contested: of a plain one that is asserted, the direct triple says it. A value of a justification
(`PerJustification()`) is not written. Each edge is in a graph of its own, as
each item of a dump is.
"""

from collections.abc import AsyncIterator, Iterator
from typing import Any
from urllib.parse import quote

from pangloss_models import ModelRegistry
from pangloss_models.exceptions import PanglossMetaError
from pangloss_rdf import IRI, Quad, class_uri, item_uri, to_literal
from pangloss_rdf.sections import DumpSection, register_dump_section
from pangloss_rdf.meta import is_excluded
from pangloss_rdf.uris import base_url, class_name, ontology_url
from pangloss_rdf.vocabulary import (
    RDF_OBJECT,
    RDF_PREDICATE,
    RDF_SUBJECT,
    RDF_TYPE,
    RDFS_COMMENT,
    RDFS_LABEL,
    RDFS_SUBCLASS,
    owl,
    pgo,
    rdfs,
)
from pydantic.alias_generators import to_camel

from pangloss_derived.declare import DerivedEdge
from pangloss_derived.registry import DerivedRegistry
from pangloss_derived.status import ASSERTED

SECTION = "derived"


def lower_first(name: str) -> str:
    return name[:1].lower() + name[1:]


def predicate_uri(model: type[DerivedEdge]) -> IRI:
    """The property a derived edge is: `SameGroup` is `sameGroup`"""
    return IRI(f"{ontology_url()}{lower_first(model.__name__)}")


def reverse_uri(model: type[DerivedEdge]) -> IRI | None:
    """The property that is its inverse, if its object has a `reverse_name` (in the ontology only)"""
    if not model._reverse_name:
        return None
    return IRI(f"{ontology_url()}{to_camel(model._reverse_name)}")


def edge_class_uri(model: type[DerivedEdge]) -> IRI:
    return IRI(f"{ontology_url()}{model.__name__}")


def qualifier_uri(model: type[DerivedEdge], field: str) -> IRI:
    return IRI(f"{ontology_url()}{model.__name__}.{to_camel(field)}")


def edge_uri(model: type[DerivedEdge], key: str) -> IRI:
    return IRI(f"{base_url()}/{SECTION}/{model.__name__}/{quote(str(key), safe='')}")


def model_named(name: str) -> type | None:
    return ModelRegistry.all_models().get(name)


def uri_of(ref: Any) -> IRI | None:
    """The URI of an entity or a head document a derived edge names: None if its class is not exported"""
    model = model_named(ref["type"] if isinstance(ref, dict) else ref.type)
    if model is None or is_excluded(model):
        return None
    return item_uri(model, ref["id"] if isinstance(ref, dict) else ref.id)


def edge_quads(model: type[DerivedEdge], found: dict[str, Any]) -> list[Quad]:
    """The quads of one edge, as `read.edges_with_evidence` gives it; none if an end is of a class that is not exported"""
    view = found["view"]
    subject_field, object_field = model._ends
    subject, object_ = (
        uri_of(getattr(view, subject_field)),
        uri_of(getattr(view, object_field)),
    )
    if subject is None or object_ is None:
        return []
    uri = edge_uri(model, view.id)
    predicate = predicate_uri(model)

    def quad(s: IRI, p: IRI, o: Any) -> Quad:
        return Quad(s, p, o, uri)

    quads: list[Quad] = []
    if found["plain"]:
        quads.append(quad(subject, predicate, object_))
    quads += [
        quad(uri, RDF_TYPE, pgo("DerivedEdge")),
        quad(uri, RDF_TYPE, edge_class_uri(model)),
        quad(uri, RDF_SUBJECT, subject),
        quad(uri, RDF_PREDICATE, predicate),
        quad(uri, RDF_OBJECT, object_),
    ]
    for field in model.qualifiers():
        value = getattr(view.qualifiers, field.name, None)
        if value is None:
            continue
        if field.kind == "relation":
            target = uri_of(value)
            if target is not None:
                quads.append(quad(uri, qualifier_uri(model, field.name), target))
        else:
            quads.append(quad(uri, qualifier_uri(model, field.name), to_literal(value)))
    quads.append(quad(uri, pgo("plain"), to_literal(bool(found["plain"]))))
    quads.append(
        quad(uri, pgo("justificationCount"), to_literal(found["justifications"]))
    )
    for label in found["context_labels"]:
        quads.append(quad(uri, pgo("context"), to_literal(label)))
    if not found["plain"] or found["status"] != ASSERTED:
        quads.append(quad(uri, pgo("derivedStatus"), to_literal(found["status"])))
    for head in found["evidence"]:
        document = uri_of(head)
        if document is not None:
            quads.append(quad(uri, pgo("justifiedBy"), document))
    return quads


async def derived_quads() -> AsyncIterator[list[Quad]]:
    """Each derived edge the reader sees, one after another, class by class"""
    from pangloss_derived import read

    for model in DerivedRegistry.concrete_classes().values():
        async for page in read.edges_with_evidence(model):
            for found in page:
                quads = edge_quads(model, found)
                if quads:
                    yield quads


def words(name: str) -> str:
    """A name as words: `SameGroup` is "Same group", `received_from` is "received from\""""
    spaced = "".join(
        f" {c.lower()}" if c.isupper() and i else c for i, c in enumerate(name)
    )
    return spaced.replace("_", " ")


def check_names() -> None:
    """Refuse a derived class whose terms are those of a model: `PanglossMetaError`, with each named"""
    from pangloss_rdf.ontology import exported_models

    taken = {class_name(model): model.__name__ for model in exported_models()}
    problems = []
    properties: dict[str, str] = {}
    for model in DerivedRegistry.concrete_classes().values():
        if model.__name__ in taken:
            problems.append(
                f"the derived edge {model.__name__} and the model {taken[model.__name__]} are both the class "
                f"{edge_class_uri(model)}"
            )
        for uri, what in (
            (predicate_uri(model), f"the derived edge {model.__name__}"),
            (reverse_uri(model), f"the reverse of the derived edge {model.__name__}"),
        ):
            if uri is None:
                continue
            other = properties.setdefault(uri.value, what)
            if other != what:
                problems.append(f"{other} and {what} are both the property {uri}")
    if problems:
        raise PanglossMetaError("RDF names: " + "; ".join(problems))


def derived_ontology() -> Iterator[Quad]:
    """The terms of the derived edges: what an edge is, and for each class its property (symmetric, or with its
    inverse), the class of its statements, and its qualifiers"""
    # (imported here: see `pangloss_rdf.sections`)
    from pangloss_rdf.ontology import exported_models

    check_names()
    exported = set(exported_models())
    yield Quad(pgo("DerivedEdge"), RDF_TYPE, owl("Class"))
    yield Quad(pgo("DerivedEdge"), RDFS_SUBCLASS, pgo("Edge"))
    yield Quad(pgo("justifiedBy"), RDF_TYPE, owl("ObjectProperty"))
    for name in ("plain", "justificationCount", "context", "derivedStatus"):
        yield Quad(pgo(name), RDF_TYPE, owl("DatatypeProperty"))
    for model in DerivedRegistry.concrete_classes().values():
        predicate = predicate_uri(model)
        subject_field, object_field = (model._fields[f] for f in model._ends)
        description = (model.__doc__ or "").strip()
        yield Quad(predicate, RDF_TYPE, owl("ObjectProperty"))
        if model._meta.symmetric:
            yield Quad(predicate, RDF_TYPE, owl("SymmetricProperty"))
        yield Quad(predicate, RDFS_LABEL, to_literal(words(model.__name__)))
        if description:
            yield Quad(predicate, RDFS_COMMENT, to_literal(description))
        if subject_field.model in exported:
            yield Quad(predicate, rdfs("domain"), class_uri(subject_field.model))
        if object_field.model in exported:
            yield Quad(predicate, rdfs("range"), class_uri(object_field.model))
        reverse = reverse_uri(model)
        if reverse is not None:
            yield Quad(reverse, RDF_TYPE, owl("ObjectProperty"))
            yield Quad(reverse, owl("inverseOf"), predicate)
            yield Quad(
                reverse, RDFS_LABEL, to_literal(words(model._reverse_name or ""))
            )
        statement = edge_class_uri(model)
        yield Quad(statement, RDF_TYPE, owl("Class"))
        yield Quad(statement, RDFS_SUBCLASS, pgo("DerivedEdge"))
        yield Quad(statement, RDFS_LABEL, to_literal(words(model.__name__)))
        for field in model.qualifiers():
            uri = qualifier_uri(model, field.name)
            kind = "ObjectProperty" if field.kind == "relation" else "DatatypeProperty"
            yield Quad(uri, RDF_TYPE, owl(kind))
            yield Quad(uri, rdfs("domain"), statement)
            if field.kind == "relation" and field.model in exported:
                yield Quad(uri, rdfs("range"), class_uri(field.model))


register_dump_section(DumpSection(SECTION, derived_quads, derived_ontology))
