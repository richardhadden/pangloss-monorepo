"""What `pangloss rdf check` says beyond `check_models`: not wrong, but worth knowing before anything is published"""

from urllib.parse import urlsplit

from pangloss_models.field_definitions import (
    ListFieldDefinition,
    RelationFieldDefinition,
)
from pangloss_models.exceptions import PanglossMetaError

from pangloss_rdf.convert import MIXIN_URI
from pangloss_rdf.fields import rdf_field
from pangloss_rdf.meta import declared_class
from pangloss_rdf.ontology import _option_class, exported_models, own_fields
from pangloss_rdf.uris import base_url


def _outside_uris(model: type) -> set[str]:
    return {c.__dict__[MIXIN_URI] for c in model.__mro__ if MIXIN_URI in c.__dict__}


def check_markers() -> None:
    """Raise for an `RDFField` that cannot do what it says"""
    problems = []
    for model in exported_models():
        for name, definition in own_fields(model):
            marker = rdf_field(definition)
            if (
                marker
                and marker.ordered
                and not isinstance(definition, ListFieldDefinition)
            ):
                problems.append(
                    f"{model.__name__}.{name}: only a list of literals can be ordered=True"
                )
    if problems:
        raise PanglossMetaError("RDFField: " + "; ".join(problems))


def warnings() -> list[str]:
    found = []
    if "example.org" in base_url():
        found.append(
            f"ENTITY_BASE_URL is still {base_url()}: URIs are permanent once published"
        )
    if not urlsplit(base_url()).path.strip("/"):
        found.append(
            "ENTITY_BASE_URL has no path of its own: its URIs are at the root of the site, which is the interface's. "
            "Give it one (https://example.com/id/) to have them resolve"
        )
    for model in exported_models():
        for name, definition in own_fields(model):
            marker = rdf_field(definition)
            for parent in marker.parent if marker else ():
                if parent.domain and not set(parent.domain) & _outside_uris(model):
                    found.append(
                        f"{model.__name__}.{name}: {model.__name__} is not in the domain of {parent.uri}"
                    )
                if isinstance(definition, RelationFieldDefinition) and parent.range:
                    for option in definition.type_options:
                        target = declared_class(_option_class(option))
                        if isinstance(target, type) and not set(
                            parent.range
                        ) & _outside_uris(target):
                            found.append(
                                f"{model.__name__}.{name}: {target.__name__} is not in the range of {parent.uri}"
                            )
    return found
