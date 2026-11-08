"""What the builders of the generated models (`initialise_create_model`, `..._create_db_model`,
`..._update_model`, `..._update_db_model`, `..._view_model`) have in common."""

from typing import Any

from frozendict import frozendict
from pydantic import field_validator, model_validator

from pangloss_models.field_definitions import (
    EmbeddedFieldDefinition,
    ParameterTypeOptions,
    RelationToDocument,
    RelationToEntity,
    RelationToGeneric,
)
from pangloss_models.model_bases.base_models import _DeclaredClass
from pangloss_models.model_bases.conjunction import Conjunction
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.embedded import Embedded
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.reified_relation import (
    ReifiedRelation,
    ReifiedRelationDocument,
)
from pangloss_models.model_bases.semantic_space import SemanticSpace
from pangloss_models.validators import SumsTo

# The kinds of declared model that have the models made from them (`Create`, `View`, ...)
MODEL_KINDS_WITH_ACTION_MODELS = (
    Document,
    Entity,
    ReifiedRelation,
    ReifiedRelationDocument,
    Conjunction,
    SemanticSpace,
    Embedded,
)


def can_have_action_models(model: type[_DeclaredClass]) -> bool:
    """Whether a declared model is of a kind that has `Create`, `Update`, `View` and the rest"""
    return issubclass(model, MODEL_KINDS_WITH_ACTION_MODELS)


def pick_base_class(
    model: type[_DeclaredClass], bases: tuple[tuple[type, type], ...]
) -> type | None:
    """The base class for the generated model of `model`: that of the first declared kind it is a
    subclass of (the order of `bases` matters)"""
    for declared_kind, base in bases:
        if issubclass(model, declared_kind):
            return base
    return None


def check_create_and_id_present(self):
    """Validator to ensure that both create_new=True and an ID must be provided together"""

    if getattr(self, "id", None) and not getattr(self, "create_new", None):
        raise ValueError(
            f"If an id is provided to {self.__class__.__name__}, the create_new=True flag must also be set"
        )
    if getattr(self, "create_new", None) and not getattr(self, "id", None):
        raise ValueError(
            f"If create_new=True flag set on {self.__class__.__name__}, an id must be provided"
        )
    return self


def get_model_validators(model, ids: bool, declared: bool) -> dict[str, Any]:
    """The validators a generated model has: if the model can be given an id (`ids`), the id and `create_new` go
    together; and (`declared`) the validators the class itself declares, which are copied to the models that are
    written (`Create`, `Update`, `CreateDB`, `UpdateDB`): its model validators (of any mode) so that a class can
    fill in what it derives from its other fields (the bounds of a date), and its field validators, which are of
    literal fields (`check_declared_class` refuses one of a relation). They are passed the generated model, so a
    model validator can use only the literal fields the class has."""
    validators = {}
    if ids and getattr(model._meta, "create_with_id", False):
        validators["check_create_and_id_present"] = model_validator(mode="after")(
            check_create_and_id_present
        )
    if declared:
        # (the markers of embedded fields first: a validator of the class that copies from such a field, as a
        # `Dateable` copies its date's sort day, sees it as it will be stored)
        markers = {
            name: definition.markers
            for name, definition in model._meta.fields.items()
            if isinstance(definition, EmbeddedFieldDefinition) and definition.markers
        }
        if markers:
            validators["apply_embedded_markers"] = model_validator(mode="after")(
                _apply_markers(markers)
            )

        for name, decorator in model.__pydantic_decorators__.model_validators.items():
            # (not those of Pangloss's own base classes, which the generated models have in their own way)
            if not decorator.cls_ref.startswith("pangloss_models."):
                validators[name] = model_validator(mode=decorator.info.mode)(
                    decorator.func
                )
        for name, decorator in model.__pydantic_decorators__.field_validators.items():
            if not decorator.cls_ref.startswith("pangloss_models."):
                # (`check_fields=False`: the fields are there, but added after the model is made)
                validators[name] = field_validator(
                    *decorator.info.fields,
                    mode=decorator.info.mode,
                    check_fields=False,
                )(decorator.func)

        shares = {
            name: found
            for name, definition in model._meta.fields.relation_fields.items()
            if (found := [v for v in definition.validators if isinstance(v, SumsTo)])
        }
        if shares:
            validators["check_shares"] = model_validator(mode="after")(
                _check_shares(shares)
            )

    return validators


def _check_shares(shares: dict[str, list[SumsTo]]):
    def check_shares(self):
        for name, found in shares.items():
            items = getattr(self, name, None) or []
            for sums_to in found:
                given = [
                    getattr(getattr(item, "edge_properties", None), sums_to.field, None)
                    for item in items
                ]
                if not items:
                    continue
                if any(value is None for value in given):
                    raise ValueError(
                        f"every one of {name} needs its {sums_to.field} (they add up to {sums_to.total})"
                    )
                if sum(given) != sums_to.total:
                    raise ValueError(
                        f"the {sums_to.field} of {name} add up to {sum(given)}, not {sums_to.total}"
                    )
        return self

    return check_shares


def _apply_markers(markers: dict[str, tuple[Any, ...]]):
    def apply_embedded_markers(self):
        for name, found in markers.items():
            value = getattr(self, name, None)
            if value is not None:
                for marker in found:
                    marker.apply_to_embedded(value)
        return self

    return apply_embedded_markers


def recursively_get_generic_naming(
    parameter_type_options: frozendict[str, ParameterTypeOptions],
) -> str:
    """The names of the types a generic is made for, for the name of the model made for it:
    `Group, Person` for `InRole[Person | Group]`"""
    names = []
    for pto in parameter_type_options.values():
        for to in pto.type_options:
            if isinstance(to, RelationToGeneric):
                names.append(
                    f"{to.base_type.__name__}[{recursively_get_generic_naming(to.parameter_type_options)}]"
                )
            elif isinstance(to, (RelationToEntity, RelationToDocument)):
                names.append(to.annotated_type.__name__)
    # (sorted: the options are a set, so the name must not depend on the order they come in)
    return ", ".join(sorted(names))
