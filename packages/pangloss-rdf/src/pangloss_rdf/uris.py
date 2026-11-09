"""The URIs of everything exported (docs/rdf-export-plan.md, §5).

Items are under `ENTITY_BASE_URL`; classes and properties under `RDF_ONTOLOGY_URL`, by default `{ENTITY_BASE_URL}/ontology/`.
"""

from typing import Any
from urllib.parse import quote
from uuid import UUID

from pangloss_core.settings import get_settings
from pangloss_models import ModelRegistry
from pangloss_models.exceptions import PanglossMetaError
from pangloss_models.field_definitions import RelationFieldDefinition
from pydantic.alias_generators import to_camel

from pangloss_rdf.fields import rdf_field
from pangloss_rdf.meta import declared_class, is_valid_name, own_rdf_meta
from pangloss_rdf.terms import IRI

# (the first segment of the ontology's own address, by default: an item of a class of this name would be under it)
ONTOLOGY_SEGMENT = "ontology"


def base_url() -> str:
    return str(get_settings().ENTITY_BASE_URL).rstrip("/")


def ontology_url() -> str:
    """Where classes and properties are: ends in `/` or `#`, so that a name can be added to it"""
    url = getattr(get_settings(), "RDF_ONTOLOGY_URL", None)
    if url is None:
        return f"{base_url()}/{ONTOLOGY_SEGMENT}/"
    url = str(url)
    return url if url.endswith(("/", "#")) else f"{url}/"


def class_name(model: type) -> str:
    """The name of a class in URIs"""
    model = declared_class(model)
    meta = own_rdf_meta(model)
    if meta is not None and meta.class_name is not None:
        return meta.class_name
    return model.__name__


def class_uri(model: type) -> IRI:
    meta = own_rdf_meta(model)
    if meta is not None and meta.class_uri is not None:
        return IRI(meta.class_uri)
    return IRI(f"{ontology_url()}{class_name(model)}")


def _registered() -> list[type]:
    """Every declared class once (the uses of a generic are the generic), in the order they were declared"""
    declared = dict.fromkeys(declared_class(m) for m in ModelRegistry._models)
    # (not the library's own bases, `ReifiedRelation[T]`: `target` of an `InRole` is the `InRole`'s)
    return [
        m
        for m in declared
        if "__metatype__" not in m.__dict__ and not m.__dict__.get("_kind_base")
    ]


def property_owner(model: type, field_name: str) -> type:
    """The class a field belongs to: the top-most that has it, so that a subclass uses its parent's property"""
    registered = set(_registered())
    for parent in reversed(declared_class(model).__mro__):
        if parent in registered and field_name in parent.model_fields:  # ty: ignore[unresolved-attribute]
            return parent
    raise PanglossMetaError(f"{model.__name__} has no field {field_name!r}")


def property_name(model: type, field_name: str) -> str:
    """`Activity.carriedOutBy`: what a property is called, after its ontology's address"""
    owner = property_owner(model, field_name)
    marker = rdf_field(_fields(owner).get(field_name))
    name = marker.name if marker and marker.name else to_camel(field_name)
    return f"{class_name(owner)}.{name}"


def property_uri(model: type, field_name: str) -> IRI:
    marker = rdf_field(_fields(property_owner(model, field_name)).get(field_name))
    if marker and marker.uri:
        return IRI(marker.uri)
    return IRI(f"{ontology_url()}{property_name(model, field_name)}")


def reverse_property_uri(model: type, field_name: str) -> IRI:
    """The property that is the inverse of a relation field (in the ontology only: the data has no reverse triples)"""
    definition = _fields(model).get(field_name)
    if not isinstance(definition, RelationFieldDefinition):
        raise PanglossMetaError(
            f"{model.__name__}.{field_name} is not a relation: it has no reverse"
        )
    owner = class_name(property_owner(model, field_name))
    return IRI(f"{ontology_url()}{owner}.{to_camel(definition.reverse_name)}")


def item_uri(model: type, item_id: UUID | str) -> IRI:
    return IRI(f"{base_url()}/{class_name(model)}/{quote(str(item_id), safe='')}")


def value_uri(parent: IRI, name: str, position: int | None = None) -> IRI:
    """A node with no id of its own, under what holds it: an embedded object, an annotated value, a `TypedDict`"""
    end = "" if position is None else f"/{position}"
    return IRI(f"{parent}/{name}{end}")


def edge_uri(subject: IRI, name: str, position: int = 0) -> IRI:
    """The node of a relation: edges have no ids, so it is made from where the edge is. Changes if a list is reordered"""
    return IRI(f"{subject}/edge/{name}/{position}")


def _fields(model: type) -> dict[str, Any]:
    meta = getattr(declared_class(model), "_meta", None)
    return getattr(meta, "fields", {}) if meta is not None else {}


def check_models() -> None:
    """Raise `PanglossMetaError` with everything wrong with the names of the initialised models: two things with one
    URI, a class whose items would be under the ontology, a name that cannot be part of a URI"""
    problems: list[str] = []
    classes: dict[IRI, type] = {}
    properties: dict[IRI, str] = {}

    def claim(uri: IRI, what: str) -> None:
        taken = properties.setdefault(uri, what)
        if taken != what:
            problems.append(f"{taken} and {what} are both the property {uri}")

    for model in _registered():
        name = class_name(model)
        if not is_valid_name(name):
            problems.append(f"{model.__name__}: {name!r} cannot be part of a URI")
            continue
        if name == ONTOLOGY_SEGMENT:
            problems.append(
                f"{model.__name__}: its items would be under the ontology: give it another RDFMeta(class_name=...)"
            )
        uri = class_uri(model)
        other = classes.setdefault(uri, model)
        if other is not model:
            problems.append(
                f"{other.__name__} and {model.__name__} are both the class {uri}"
            )
        for field_name, definition in _fields(model).items():
            owner = property_owner(model, field_name)
            claim(property_uri(model, field_name), f"{owner.__name__}.{field_name}")
            if isinstance(definition, RelationFieldDefinition):
                claim(
                    reverse_property_uri(model, field_name),
                    f"the reverse of {owner.__name__}.{field_name}",
                )
    if problems:
        raise PanglossMetaError("RDF names: " + "; ".join(problems))
