"""What the builders of the generated models (`initialise_create_model`, `..._create_db_model`,
`..._update_model`, `..._update_db_model`, `..._view_model`) have in common."""

from typing import Any

from frozendict import frozendict
from pydantic import field_validator, model_validator
from pydantic.alias_generators import to_camel

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
from pangloss_models.write_checks import marked

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


def get_model_validators(model, ids: bool, written: str | None) -> dict[str, Any]:
    """The validators a generated model has: if the model can be given an id (`ids`), the id and `create_new` go
    together; and, for a model that is written (`written` is its kind: `Create`, `Update`, `CreateDB`, `UpdateDB`),
    the validators the class declares.

    Pydantic's (`@model_validator` of any mode, and `@field_validator`, of literal fields: `check_declared_class`
    refuses one of a relation) are on `Create` and `Update`, which is where a payload is parsed: so each runs once,
    as pydantic would run it, and not again when the database model is made from what it gave. A `before` one is
    given the keys in snake_case, whichever the payload used. `@create_validator`s are on `CreateDB`,
    `@update_validator`s on `UpdateDB` (see `write_checks`). They are passed the generated model, so a validator
    can use only the literal fields the class has."""
    validators = {}
    if ids and getattr(model._meta, "create_with_id", False):
        validators["check_create_and_id_present"] = model_validator(mode="after")(
            check_create_and_id_present
        )
    if written:
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

        if written in ("Create", "Update"):
            validators |= declared_pydantic_validators(model)
        what = {"CreateDB": "create_validator", "UpdateDB": "update_validator"}.get(
            written
        )
        for name, function in marked(model, what).items() if what else ():
            validators[name] = model_validator(mode="after")(_returning_self(function))

        if written in ("Create", "Update"):
            stood_in = {
                name: found
                for name, definition in model._meta.fields.relation_fields.items()
                if (found := stand_ins_of(definition.type_options))
            }
            if stood_in:
                validators["check_stand_ins"] = model_validator(mode="after")(
                    check_stand_ins(stood_in)
                )

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


def stand_ins_of(options) -> dict[str, frozenset[str]]:
    """Of the options of a relation, the documents that may be given in place of entities (`hooks.StandIn`): the
    name of each, with the names of the entity classes it stands for there"""
    return {
        option.annotated_type.__name__: option.stands_in_for
        for option in options
        if isinstance(option, RelationToDocument) and option.stands_in_for
    }


def check_stand_ins(fields: dict[str, dict[str, frozenset[str]]]):
    """A validator: each stand-in given for a relation can stand for an entity class of that relation (what the
    package that made it a stand-in checks: `hooks.StandIn.check`). `fields`: by field, `stand_ins_of` its options"""
    from pangloss_models import hooks

    checks = {s.document: s.check for s in hooks.stand_ins if s.check is not None}

    def check(self):
        for name, stood_in in fields.items():
            value = getattr(self, name, None)
            for item in value if isinstance(value, (list, tuple)) else [value]:
                names = stood_in.get(getattr(item, "type", None) or "")
                if names is not None and item.type in checks:
                    try:
                        checks[item.type](item, names)
                    except ValueError as error:
                        raise ValueError(f"{name}: {error}") from error
        return self

    return check


def declared_pydantic_validators(model) -> dict[str, Any]:
    """The `@model_validator`s and `@field_validator`s the class declares (not those of Pangloss's own base classes,
    which the generated models have in their own way), and before them (pydantic runs the `before` validators
    last added first) one that gives them the keys in snake_case"""
    validators: dict[str, Any] = {}
    for name, decorator in model.__pydantic_decorators__.model_validators.items():
        # (the class of a citation is Pangloss's, but a declared class as a project's are)
        if not decorator.cls_ref.startswith(
            "pangloss_models."
        ) or decorator.cls_ref.startswith("pangloss_models.citations."):
            validators[name] = model_validator(mode=decorator.info.mode)(decorator.func)
    for name, decorator in model.__pydantic_decorators__.field_validators.items():
        if not decorator.cls_ref.startswith("pangloss_models."):
            # (`check_fields=False`: the fields are there, but added after the model is made)
            validators[name] = field_validator(
                *decorator.info.fields,
                mode=decorator.info.mode,
                check_fields=False,
            )(decorator.func)
    if validators:
        validators["snake_case_keys"] = model_validator(mode="before")(
            _snake_case_keys(model)
        )
    return validators


def _snake_case_keys(model):
    """The keys of a payload as the class names its fields: a client may send `bornIn` for `born_in`"""
    names = {to_camel(name): name for name in model.model_fields}

    def snake_case_keys(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        return {names.get(key, key): value for key, value in data.items()}

    return classmethod(snake_case_keys)


def _returning_self(function):
    def run(self):
        function(self)
        return self

    run.__name__ = function.__name__
    return run


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
