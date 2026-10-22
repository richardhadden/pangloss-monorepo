"""Sample data for the declared models, made from their field definitions.

`sample_payload(model)` is a valid payload for `model.Create`: a value for every field, a nested
sample for every document, an embedded object or a wrapper, and a reference for every entity. It is
written from the field definitions (`model._meta.fields`), not from the generated models, so that a
test which gives the payload to the generated models is checking them against what they were made
from.

Everything is deterministic (the options of a relation are taken in the order of their names).
"""

import datetime
import enum
import typing
from decimal import Decimal
from typing import Any, get_args, get_origin
from uuid import UUID, uuid7

from annotated_types import Ge, Gt, Le, Lt, MaxLen, MinLen

from pangloss_models.field_definitions import (
    AnnotatedValueFieldDefinition,
    EmbeddedFieldDefinition,
    ListFieldDefinition,
    LiteralFieldDefinition,
    LiteralTypeVarFieldDefinition,
    RelationFieldDefinition,
    RelationToDocument,
    RelationToEntity,
    RelationToTypeVar,
)


def sample_literal(tp: Any, validators: list[Any] | tuple[Any, ...] = ()) -> Any:
    """A value of a literal type that satisfies its validators"""
    origin = get_origin(tp)
    if origin is typing.Union or origin is getattr(__import__("types"), "UnionType", None):
        options = [a for a in get_args(tp) if a is not type(None)]
        return sample_literal(options[0], validators)
    if origin is list:
        return [sample_literal(get_args(tp)[0])]
    if origin is typing.Annotated:
        inner, *metadata = get_args(tp)
        return sample_literal(inner, [*validators, *metadata])

    minimum = next((v.min_length for v in validators if isinstance(v, MinLen)), 0)
    maximum = next((v.max_length for v in validators if isinstance(v, MaxLen)), None)

    if tp is str:
        text = "sample text"
        text = (text * (minimum // len(text) + 1))[: max(minimum, len(text))]
        return text[:maximum] if maximum else text
    if tp is bool:
        return True
    if tp in (int, float):
        value = 7
        for v in validators:
            if isinstance(v, Ge):
                value = max(value, v.ge)
            elif isinstance(v, Gt):
                value = max(value, v.gt + 1)
            elif isinstance(v, Le):
                value = min(value, v.le)
            elif isinstance(v, Lt):
                value = min(value, v.lt - 1)
        return tp(value)
    if tp is Decimal:
        return "3.5"
    if tp is datetime.datetime:
        return "2020-01-02T03:04:05Z"
    if tp is datetime.date:
        return "2020-01-02"
    if isinstance(tp, type) and issubclass(tp, enum.Enum):
        return next(iter(tp)).value
    if isinstance(tp, type) and typing.is_typeddict(tp):
        return {name: sample_literal(t) for name, t in typing.get_type_hints(tp).items()}
    raise NotImplementedError(f"no sample for the literal type {tp!r}")


def by_name(options):
    return sorted(options, key=lambda o: getattr(o.annotated_type, "__name__", str(o.annotated_type)))


class Sampler:
    def __init__(self, choice: int = 0):
        """`choice` says which of the types a relation allows is used (0 for the first, by name, 1 for
        the second, and so on, round again): a different `choice` reaches different members of a union"""
        self.choice = choice
        self.references: list[tuple[str, UUID]] = []

    def pick(self, options):
        ordered = by_name(options)
        return ordered[self.choice % len(ordered)]

    # --- values of one kind of field ------------------------------------------------------------

    def fields(self, model, skip: frozenset[str] | set[str] = frozenset(), types: dict[str, Any] | None = None) -> dict[str, Any]:
        """A value for each field of a declared model (or wrapper) that is not a database field.
        `types` is what the type variables of a wrapper stand for."""
        payload: dict[str, Any] = {}
        for name, definition in model._meta.fields.items():
            if name in skip or definition.db_field:
                continue
            payload[name] = self.field(definition, types or {})
        return payload

    def field(self, definition, types: dict[str, Any]) -> Any:
        if isinstance(definition, LiteralFieldDefinition):
            return sample_literal(definition.annotated_type, definition.validators)
        if isinstance(definition, ListFieldDefinition):
            return [sample_literal(definition.inner_type, definition.inner_type_validators)]
        if isinstance(definition, LiteralTypeVarFieldDefinition):
            return sample_literal(types[definition.type_var_name.split("~")[-1]])
        if isinstance(definition, EmbeddedFieldDefinition):
            option = self.pick(definition.type_options)
            embedded = option.annotated_type
            return {"type": embedded.__name__, **self.fields(embedded)}
        if isinstance(definition, AnnotatedValueFieldDefinition):
            return self.annotated_value(definition.annotated_type)
        if isinstance(definition, RelationFieldDefinition):
            value = self.relation(definition, types)
            return [value] if definition.wrapper else value
        raise NotImplementedError(f"no sample for {type(definition).__name__}")

    def annotated_value(self, tp) -> dict[str, Any]:
        """`WithCertainty[str]`: its `value`, and its own fields"""
        generic = tp.__pydantic_generic_metadata__
        arguments = dict(zip((p.__name__ for p in generic["origin"].__pydantic_generic_metadata__["parameters"]), generic["args"]))
        payload: dict[str, Any] = {}
        for name, definition in tp._meta.fields.items():
            payload[name] = (
                sample_literal(arguments["T"]) if isinstance(definition, LiteralTypeVarFieldDefinition) else self.field(definition, arguments)
            )
        return payload

    # --- relations ------------------------------------------------------------------------------

    def relation(self, definition: RelationFieldDefinition, types: dict[str, Any]) -> Any:
        """One value for a relation: for the first of the types it allows"""
        option = self.pick(definition.type_options)
        if isinstance(option, RelationToTypeVar):
            return self.option_value(types[option.type_var_name], types)
        return self.option_value(option, types)

    def option_value(self, option, types) -> Any:
        edge = getattr(option, "edge_model", None)
        if isinstance(option, RelationToEntity):
            value = self.reference(option.annotated_type)
        elif isinstance(option, RelationToDocument):
            value = self.head(option.annotated_type)
        else:
            value = self.wrapper(option)
        if edge is not None:
            value = {**value, "edge_properties": self.fields(edge)}
        return value

    def reference(self, entity) -> dict[str, Any]:
        identifier = uuid7()
        self.references.append((entity.__name__, identifier))
        return {"type": entity.__name__, "id": identifier}

    def wrapper(self, option) -> dict[str, Any]:
        """A reified relation, semantic space or conjunction: its own fields, and, for each of
        its type variables, a sample of what it stands for"""
        base = option.base_type
        standing_for = {
            name: self.parameter_value(parameter)
            for name, parameter in option.parameter_type_options.items()
        }
        payload: dict[str, Any] = {"type": base.__name__}
        if getattr(base._meta, "require_label", False):  # (a reified relation that is a document)
            payload["label"] = f"A {base.__name__}"
        for name, definition in base._meta.fields.items():
            if definition.db_field or name == "label":
                continue
            holds_type_variable = isinstance(definition, RelationFieldDefinition) and any(
                isinstance(o, RelationToTypeVar) for o in definition.type_options
            )
            if holds_type_variable:
                variable = next(o for o in definition.type_options if isinstance(o, RelationToTypeVar))
                value = standing_for[variable.type_var_name]
                payload[name] = [value] if definition.wrapper else value
            else:
                payload[name] = self.field(definition, {})
        return payload

    def parameter_value(self, parameter) -> Any:
        return self.option_value(self.pick(parameter.type_options), {})

    # --- a document or an entity -----------------------------------------------------------------

    def head(self, model) -> dict[str, Any]:
        """A payload for `model.Create`"""
        payload: dict[str, Any] = {"type": model.__name__}
        if getattr(model._meta, "require_label", True):
            payload["label"] = f"A {model.__name__}"
        payload.update(self.fields(model, skip={"label"}))
        return payload


def sample_payload(model, choice: int = 0) -> dict[str, Any]:
    """A valid payload for `model.Create` (without its `type`)"""
    payload = Sampler(choice).head(model)
    payload.pop("type")
    return payload


CHOICES = range(4)  # (the most any relation in the models used offers)
