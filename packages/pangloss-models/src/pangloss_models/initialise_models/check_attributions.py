"""The checks at `initialise()` of `Attribution(by=..., to=...)` (`pangloss_models.markers`): that it is on a relation
that can hold a semantic space, and that the fields it names are other relations of the class that reach an entity,
directly or through a wrapper. A name that is wrong would otherwise say nothing, and the space would be no one's.

Each class is checked with the fields it has, those it inherits included: a subclass in which a named field no longer
reaches an entity is refused in its own name"""

from collections.abc import Iterable

from pangloss_models.diagnostics import reported
from pangloss_models.exceptions import AtString, PanglossModelError, did_you_mean
from pangloss_models.field_definitions import (
    FieldDefinition,
    RelationFieldDefinition,
    RelationToSemanticSpace,
)
from pangloss_models.markers import Attribution
from pangloss_models.model_bases.entity import Entity
from pangloss_models.search import leaf_classes


def reaches_an_entity(definition: FieldDefinition) -> bool:
    """Whether a relation can point at an entity: directly, or behind the wrappers on its way (`InRole[Person]`), as
    search reaches them"""
    from pangloss_models.exceptions import PanglossSearchError

    if not isinstance(definition, RelationFieldDefinition):
        return False
    for option in definition.type_options:
        found: list[type] = []
        try:
            leaf_classes(definition.field_name, option, found, [False])
        except PanglossSearchError:
            # (an option search cannot follow, a type variable's: it reaches nothing that can be named here)
            continue
        if any(isinstance(c, type) and issubclass(c, Entity) for c in found):
            return True
    return False


def holds_a_space(definition: FieldDefinition | None) -> bool:
    return isinstance(definition, RelationFieldDefinition) and any(
        isinstance(option, RelationToSemanticSpace)
        for option in definition.type_options
    )


def check_attribution(model: type, field_name: str, marks: list[Attribution]) -> None:
    where = f"{model.__name__}.{field_name}"
    if len(marks) > 1:
        raise PanglossModelError(
            f"{where} has {len(marks)} Attribution markers: a field has one, which names both fields "
            "(`Attribution(by=..., to=...)`)"
        )
    (attribution,) = marks
    if attribution.by is None and attribution.to is None:
        raise PanglossModelError(
            f"{where}: Attribution() names no field. Give `by` (whose attitude or act it is), `to` (whom it is "
            "addressed to), or both"
        )
    fields: dict[str, FieldDefinition] = dict(model._meta.fields)  # ty: ignore[unresolved-attribute]
    if not holds_a_space(fields.get(field_name)):
        raise PanglossModelError(
            f"{where}: Attribution is for a relation that holds a semantic space (`Ordered[Statement]`, or a list "
            "or union with one among its types), and this field holds none"
        )
    candidates = sorted(
        name
        for name, definition in fields.items()
        if name != field_name and reaches_an_entity(definition)
    )
    for option in ("by", "to"):
        named = getattr(attribution, option)
        if named is None:
            continue
        said = f"{where}: Attribution({option}={named!r})"
        if named == field_name:
            raise PanglossModelError(
                f"{said} names the field it is on. Name the relation to whoever the space is "
                + ("of" if option == "by" else "addressed to"),
                at_string=AtString(option, named),
            )
        definition = fields.get(named)
        if definition is None:
            raise PanglossModelError(
                f"{said}: {model.__name__} has no field {named!r}."
                + did_you_mean(named, candidates),
                at_string=AtString(option, named, tuple(candidates)),
            )
        if not reaches_an_entity(definition):
            what = (
                "a relation that reaches only documents"
                if isinstance(definition, RelationFieldDefinition)
                else "not a relation"
            )
            raise PanglossModelError(
                f"{said}: {model.__name__}.{named} is {what}. It must be a relation that reaches an entity "
                "(`Person`, `list[Person]`, `Person | None`, or through a reified relation: `InRole[Person]`)",
                at_string=AtString(option, named),
            )


def _is_checked(model: type) -> bool:
    # (a parametrisation, `InRole[Person]`, has the fields of its generic, which is checked)
    metadata = getattr(model, "__pydantic_generic_metadata__", None) or {}
    return (
        getattr(getattr(model, "_meta", None), "fields", None) is not None
        and metadata.get("origin") is None
    )


def check_attributions(models: Iterable[type]) -> None:
    for model in models:
        if not _is_checked(model):
            continue
        # (read from what the field is annotated with, not its definition: an embedded field's definition keeps only
        # the markers the server applies, and an Attribution on one would be lost)
        for field_name, info in model.model_fields.items():  # ty: ignore[unresolved-attribute]
            marks = [m for m in info.metadata if isinstance(m, Attribution)]
            if marks:
                with reported(model, field_name):
                    check_attribution(model, field_name, marks)
