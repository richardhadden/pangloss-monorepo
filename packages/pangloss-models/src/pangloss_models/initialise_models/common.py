"""What the builders of the generated models (`initialise_create_model`, `..._create_db_model`,
`..._update_model`, `..._update_db_model`, `..._view_model`) have in common."""

from typing import Any

from frozendict import frozendict
from pydantic import model_validator

from pangloss_models.field_definitions import (
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


def get_model_validators(model) -> dict[str, Any]:
    """The validators a `Create` (or `CreateDB`, `Update`) model has: if the model can be given an
    id, the id and `create_new` go together"""
    validators = {}
    if getattr(model._meta, "create_with_id", False):
        validators["check_create_and_id_present"] = model_validator(mode="after")(
            check_create_and_id_present
        )

    return validators


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
