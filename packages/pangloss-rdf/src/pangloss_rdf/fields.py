"""`RDFField`: what a field is called in RDF, and what it means in another ontology.

carried_out_by: Annotated[ViaEdge[Agent, Certainty], RDFField(parent=P14_carried_out_by)]
"""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from pangloss_models.exceptions import PanglossMetaError
from pangloss_models.field_definitions import FieldDefinition
from pangloss_models.markers import FieldMarker

from pangloss_rdf.meta import is_valid_name


@dataclass(frozen=True)
class OntologyProperty:
    """A property of an outside ontology: a value, as a field cannot inherit from anything"""

    uri: str
    domain: tuple[str, ...] = ()
    range: tuple[str, ...] = ()


@dataclass(frozen=True, init=False, eq=True)
class RDFField(FieldMarker):
    name: str | None
    uri: str | None
    parent: tuple[OntologyProperty, ...]
    exclude: bool
    ordered: bool
    language: str | None

    def __init__(
        self,
        name: str | None = None,
        uri: str | None = None,
        parent: OntologyProperty | Iterable[OntologyProperty] = (),
        exclude: bool = False,
        ordered: bool = False,
        language: str | None = None,
    ) -> None:
        if name is not None and uri is not None:
            raise PanglossMetaError("RDFField: give name or uri, not both")
        if name is not None and not is_valid_name(name):
            raise PanglossMetaError(
                f"RDFField: name {name!r} cannot be part of a URI: "
                "use letters, digits, '_' and '-', not starting with a digit"
            )
        parents = (parent,) if isinstance(parent, OntologyProperty) else tuple(parent)
        for field, value in (
            ("name", name),
            ("uri", uri),
            ("parent", parents),
            ("exclude", exclude),
            ("ordered", ordered),
            ("language", language),
        ):
            object.__setattr__(self, field, value)

    def apply_to_embedded(self, value: Any) -> None:
        """(How an embedded field knows a marker. An `RDFField` does nothing to the value)"""

    def __repr__(self) -> str:
        return "RDFField()"


_ontology_prefixes: dict[str, str] = {}


def register_ontology_prefix(prefix: str, namespace: str) -> None:
    """What an outside ontology is called in the output: said by its generated module, as it is imported"""
    _ontology_prefixes[prefix] = namespace


def ontology_prefixes() -> dict[str, str]:
    return dict(_ontology_prefixes)


def rdf_field(definition: FieldDefinition | None) -> RDFField | None:
    if definition is None:
        return None
    return next((m for m in definition.markers if isinstance(m, RDFField)), None)
