"""The checks at `initialise()` of the ground of a head class (`Ground`, `pangloss_models.model_bases.ground`): that
it does not deny, that it has a degree only where what it holds is neither asserted nor denied, that a record names
no one whose it is, and that `by` names a relation of the class that reaches an entity.

A class is refused for what it says of itself: a ground it inherits unchanged is its parent's, but for `by`, which is
checked against the fields of every class that can have items (a subclass in which the named field no longer
reaches an entity is refused in its own name; an abstract class may name a field its subclasses declare)."""

from collections.abc import Iterable

from pangloss_models.diagnostics import reported
from pangloss_models.exceptions import AtString, PanglossModelError, did_you_mean
from pangloss_models.field_definitions import FieldDefinition, RelationFieldDefinition
from pangloss_models.initialise_models.check_attributions import reaches_an_entity
from pangloss_models.model_bases.ground import (
    RECORD,
    Ground,
    ground_of,
    has_ground,
)


def _is_checked(model: type) -> bool:
    metadata = getattr(model, "__pydantic_generic_metadata__", None) or {}
    return (
        has_ground(model)
        and metadata.get("origin") is None
        and isinstance(getattr(getattr(model, "_meta", None), "ground", None), Ground)
    )


def _inherited(model: type, ground: Ground) -> bool:
    """Whether the class has the ground of the nearest class above it that has one"""
    for parent in model.__mro__[1:]:
        if has_ground(parent) and hasattr(parent, "_meta"):
            return getattr(parent._meta, "ground", None) == ground  # ty: ignore[unresolved-attribute]
    return False


def check_ground_values(model: type, ground: Ground) -> None:
    name = model.__name__
    if ground.veridical == -1:
        raise PanglossModelError(
            f"{name}: Ground(veridical=-1): a ground does not deny what its class holds. Give veridical=0 (neither "
            "asserted nor denied), or say what is denied in the document, with a semantic space that is a 'not'"
        )
    if ground.degree is not None and ground.veridical == 1:
        raise PanglossModelError(
            f"{name}: Ground(degree={ground.degree!r}), but what the class holds is asserted (veridical=1): a "
            "degree is only of what is neither asserted nor denied. Leave degree out, or give veridical=0",
            fix="ground_degree",
        )
    if ground.by is not None and ground_of(model).standing == RECORD:
        why = (
            "standing='record'"
            if ground.standing == RECORD
            else f"{name} is an entity, whose ground is the record unless it says standing='claim'"
        )
        raise PanglossModelError(
            f"{name}: Ground(by={ground.by!r}) on a record ({why}): the record is what claims are held against, and "
            "is no one's. Leave by out, or give standing='claim'",
            at_string=AtString("by", ground.by),
        )


def check_ground_by(model: type, ground: Ground) -> None:
    named = ground.by
    if named is None:
        return
    name = model.__name__
    fields: dict[str, FieldDefinition] = dict(model._meta.fields)  # ty: ignore[unresolved-attribute]
    candidates = sorted(n for n, d in fields.items() if reaches_an_entity(d))
    said = f"{name}: Ground(by={named!r})"
    definition = fields.get(named)
    if definition is None:
        raise PanglossModelError(
            f"{said}: {name} has no field {named!r}." + did_you_mean(named, candidates),
            at_string=AtString("by", named, tuple(candidates)),
        )
    if not reaches_an_entity(definition):
        what = (
            "a relation that reaches only documents"
            if isinstance(definition, RelationFieldDefinition)
            else "not a relation"
        )
        raise PanglossModelError(
            f"{said}: {name}.{named} is {what}. It must be a relation that reaches an entity, whose commitment "
            "what the class holds is (`Source`, `Person | None`, or through a reified relation: `InRole[Person]`)",
            at_string=AtString("by", named),
        )


def check_grounds(models: Iterable[type]) -> None:
    for model in models:
        if not _is_checked(model):
            continue
        ground: Ground = model._meta.ground  # ty: ignore[unresolved-attribute]
        with reported(model, "_meta"):
            if not _inherited(model, ground):
                check_ground_values(model, ground)
            if not model._meta.abstract:  # ty: ignore[unresolved-attribute]
                check_ground_by(model, ground)
