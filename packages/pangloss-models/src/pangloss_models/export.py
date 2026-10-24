"""The definitions of the models (`ModelFields`) as plain data, for something that is not
Python to read: the interface uses it to know what to show.

`export_models()` gives a dict that `json.dumps` can write. It is made from the
initialised models, so `initialise()` has to have run, and it needs no database. The
keys are the names in the JSON of the API (camel case, such as `bornIn`) as well as the
Python names, because both are needed: `key` is what is in the JSON of a request or response.

Its shape (`ModelsExport`), for each model:

    name, kind, abstract, description, parent, concreteTypes, typeParameters,
    createWithId, acceptUrlAsId, requireLabel, useInSemanticSpaceLabel, fields, incoming

and each field has a `kind`:

    literal         type (see below), validators
    list            item (a type), validators, itemValidators
    annotatedValue  model, valueType
    typeVar         typeVar
    embedded        model, types
    relation        many, reverseName, options, validators

A type is `{"type": "str"}` (also `int`, `float`, `bool`, `decimal`, `date`, `datetime`,
`uuid`), `{"type": "enum", "enum": "Name"}` (the members are in `enums`), `{"type":
"typedDict", "fields": {...}}`, `{"type": "list", "item": type}`, `{"type": "literal",
"values": [...]}` or `{"type": "unknown", "repr": "..."}`.
"""

import dataclasses
import datetime
import decimal
import enum
import inspect
import typing
import uuid
from types import UnionType
from typing import Any, get_args, get_origin, is_typeddict

from pydantic.alias_generators import to_camel

from pangloss_models.field_definitions import (
    AnnotatedValueFieldDefinition,
    EmbeddedFieldDefinition,
    FieldDefinition,
    IncomingRelationDefinition,
    ListFieldDefinition,
    LiteralFieldDefinition,
    LiteralTypeVarFieldDefinition,
    ParameterTypeOptions,
    RelationFieldDefinition,
    RelationOption,
    RelationToConjunction,
    RelationToDocument,
    RelationToEntity,
    RelationToReifiedRelation,
    RelationToReifiedRelationDocument,
    RelationToSemanticSpace,
    RelationToTypeVar,
)
from pangloss_models.model_registry import ModelRegistry

SCALAR_TYPES: list[tuple[type, str]] = [
    # (bool before int, datetime before date)
    (bool, "bool"),
    (int, "int"),
    (float, "float"),
    (str, "str"),
    (decimal.Decimal, "decimal"),
    (datetime.datetime, "datetime"),
    (datetime.date, "date"),
    (uuid.UUID, "uuid"),
]


class Exporter:
    def __init__(self) -> None:
        self.enums: dict[str, dict[str, Any]] = {}

    # --- types -----------------------------------------------------------

    def describe_type(self, tp: Any) -> dict[str, Any]:
        origin = get_origin(tp)
        if origin is typing.Annotated:
            return self.describe_type(get_args(tp)[0])
        if origin is typing.Literal:
            return {"type": "literal", "values": [self.plain(v) for v in get_args(tp)]}
        if origin in (list, set, frozenset, tuple):
            args = get_args(tp)
            return {
                "type": "list",
                "item": self.describe_type(args[0])
                if args
                else {"type": "unknown", "repr": "?"},
            }
        if origin is typing.Union or origin is UnionType:
            options = [a for a in get_args(tp) if a is not type(None)]
            if len(options) == 1:
                return self.describe_type(options[0])
            return {"type": "unknown", "repr": repr(tp)}
        if isinstance(tp, type):
            if issubclass(tp, enum.Enum):
                return self.describe_enum(tp)
            if is_typeddict(tp):
                return {
                    "type": "typedDict",
                    "fields": {
                        name: self.describe_type(annotation)
                        for name, annotation in typing.get_type_hints(tp).items()
                    },
                }
            for scalar, name in SCALAR_TYPES:
                if issubclass(tp, scalar):
                    return {"type": name}
        return {"type": "unknown", "repr": repr(tp)}

    def describe_enum(self, enumeration: type[enum.Enum]) -> dict[str, Any]:
        name = enumeration.__name__
        self.enums[name] = {
            "name": name,
            "members": [
                {"name": member.name, "value": self.plain(member.value)}
                for member in enumeration
            ],
        }
        return {"type": "enum", "enum": name}

    def plain(self, value: Any) -> Any:
        """A value as JSON can have it"""
        if isinstance(value, enum.Enum):
            return self.plain(value.value)
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        if isinstance(value, (list, tuple, set, frozenset)):
            return [self.plain(v) for v in value]
        if isinstance(value, dict):
            return {str(k): self.plain(v) for k, v in value.items()}
        return str(value)

    def validators(self, validators: list) -> list[dict[str, Any]]:
        """Constraints from `annotated_types` (`Gt(5)`, `MaxLen(10)`, ...), by name"""
        result = []
        for validator in validators:
            entry: dict[str, Any] = {"name": type(validator).__name__}
            if dataclasses.is_dataclass(validator):
                for f in dataclasses.fields(validator):
                    entry[f.name] = self.plain(getattr(validator, f.name))
            result.append(entry)
        return result

    # --- fields ----------------------------------------------------------

    def export_field(self, name: str, definition: FieldDefinition) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "name": name,
            "key": to_camel(name),
            "description": definition.description,
            "dbField": definition.db_field,
        }
        entry.update(self.field_requirements(definition))

        if isinstance(definition, ListFieldDefinition):
            entry |= {
                "kind": "list",
                "item": self.describe_type(definition.inner_type),
                "validators": self.validators(definition.validators),
                "itemValidators": self.validators(definition.inner_type_validators),
            }
        elif isinstance(definition, LiteralFieldDefinition):
            entry |= {
                "kind": "literal",
                "type": self.describe_type(definition.annotated_type),
                "validators": self.validators(definition.validators),
            }
        elif isinstance(definition, LiteralTypeVarFieldDefinition):
            entry |= {"kind": "typeVar", "typeVar": definition.type_var_name}
        elif isinstance(definition, AnnotatedValueFieldDefinition):
            origin = definition.annotated_type.__pydantic_generic_metadata__.get(
                "origin"
            )
            args = definition.annotated_type.__pydantic_generic_metadata__.get(
                "args", ()
            )
            entry |= {
                "kind": "annotatedValue",
                "model": (origin or definition.annotated_type).__name__,
                "valueType": self.describe_type(args[0]) if args else None,
            }
        elif isinstance(definition, EmbeddedFieldDefinition):
            entry |= {
                "kind": "embedded",
                "model": definition.annotated_type.__name__
                if isinstance(definition.annotated_type, type)
                else None,
                "types": sorted(
                    o.annotated_type.__name__ for o in definition.type_options
                ),
            }
        elif isinstance(definition, RelationFieldDefinition):
            entry |= {
                "kind": "relation",
                "many": definition.wrapper is not None,
                "reverseName": definition.reverse_name,
                "options": self.options(definition.type_options),
                "validators": self.validators(definition.validators),
            }
        else:
            entry["kind"] = "unknown"
        return entry

    def field_requirements(self, definition: FieldDefinition) -> dict[str, Any]:
        """Whether the field may be left out, or be null, as the model declares it"""
        try:
            model_field = definition.model_field
        except Exception:
            return {"required": False, "nullable": False}
        annotation = model_field.annotation
        nullable = annotation is type(None) or type(None) in get_args(annotation)
        return {"required": model_field.is_required(), "nullable": nullable}

    # --- relations -------------------------------------------------------

    def options(self, options: Any) -> list[dict[str, Any]]:
        exported = [self.option(o) for o in options]
        return sorted(
            exported, key=lambda o: (o["kind"], str(o.get("type") or o.get("name")))
        )

    def option(self, option: RelationOption) -> dict[str, Any]:
        edge_model = option.edge_model.__name__ if option.edge_model else None
        match option:
            case RelationToDocument():
                return {
                    "kind": "document",
                    "type": option.annotated_type.__name__,
                    "edgeModel": edge_model,
                }
            case RelationToEntity():
                return {
                    "kind": "entity",
                    "type": option.annotated_type.__name__,
                    "edgeModel": edge_model,
                }
            case RelationToTypeVar():
                return {
                    "kind": "typeVar",
                    "name": option.type_var_name,
                    "edgeModel": edge_model,
                }
            case (
                RelationToSemanticSpace()
                | RelationToConjunction()
                | RelationToReifiedRelation()
                | RelationToReifiedRelationDocument()
            ):
                kinds = {
                    RelationToSemanticSpace: "semanticSpace",
                    RelationToConjunction: "conjunction",
                    RelationToReifiedRelation: "reifiedRelation",
                    RelationToReifiedRelationDocument: "reifiedRelationDocument",
                }
                return {
                    "kind": kinds[type(option)],
                    "type": option.base_type.__name__,
                    "edgeModel": edge_model,
                    "params": {
                        name: self.parameter(parameter)
                        for name, parameter in sorted(
                            option.parameter_type_options.items()
                        )
                    },
                }
        return {
            "kind": "unknown",
            "type": getattr(
                option.annotated_type, "__name__", repr(option.annotated_type)
            ),
        }

    def parameter(self, parameter: ParameterTypeOptions) -> dict[str, Any]:
        return {
            "typeVar": parameter.type_var_name,
            "options": self.options(parameter.type_options),
        }

    # --- models ----------------------------------------------------------

    def export_model(self, model: type) -> dict[str, Any]:
        from pangloss_models.utils import get_concrete_types, get_parent_class

        meta = model._meta  # type: ignore[attr-defined]
        description = model.__dict__.get("__doc__")
        parent = None
        concrete: list[str] = []
        parent_class = get_parent_class(model)
        if parent_class is not None:
            origin = (parent_class.__pydantic_generic_metadata__ or {}).get("origin")
            parent_class = origin or parent_class
        # (not the base classes of the library, such as `AnnotatedValue[T]`)
        if parent_class is not None and not parent_class.__module__.startswith(
            "pangloss_models.model_bases"
        ):
            parent = parent_class.__name__
        concrete = sorted(c.__name__ for c in get_concrete_types(model))

        generic = getattr(model, "__pydantic_generic_metadata__", None) or {}
        return {
            "name": model.__name__,
            "kind": model.__metatype__,  # type: ignore[attr-defined]
            "abstract": bool(getattr(meta, "abstract", False)),
            "description": inspect.cleandoc(description) if description else None,
            "parent": parent,
            "concreteTypes": concrete,
            "typeParameters": [p.__name__ for p in generic.get("parameters", ())],
            "createWithId": bool(getattr(meta, "create_with_id", False)),
            "acceptUrlAsId": bool(getattr(meta, "accept_url_as_id", False)),
            "requireLabel": bool(getattr(meta, "require_label", True)),
            "useInSemanticSpaceLabel": bool(
                getattr(meta, "use_in_semantic_space_label", True)
            ),
            "fields": [
                self.export_field(n, d)
                for n, d in meta.field_definitions.fields.items()
            ],
            "incoming": self.incoming(meta.field_definitions.incoming_fields),
        }

    def incoming(
        self, incoming_fields: dict[str, list[IncomingRelationDefinition]]
    ) -> list[dict[str, Any]]:
        return [
            {
                "name": name,
                "key": to_camel(name),
                "sources": sorted(
                    (
                        {
                            "model": d.source.__name__,
                            "field": d.field_definition.field_name,
                            "viaReified": d.via_reified,
                        }
                        for d in definitions
                    ),
                    key=lambda s: (s["model"], s["field"]),
                ),
            }
            for name, definitions in sorted(incoming_fields.items())
        ]


def export_models() -> dict[str, Any]:
    """Every initialised model, and the enums they use. Models made inside a function
    (so that they cannot be named) are included like the others."""
    exporter = Exporter()
    models: dict[str, Any] = {}
    for model in sorted(ModelRegistry._models, key=lambda m: m.__name__):
        if not getattr(model, "__metatype__", None):
            continue
        # (`Negative[Person]` and the like are made where a model is used with
        # parameters; the model is `Negative`, and the field says what it is used with)
        if (getattr(model, "__pydantic_generic_metadata__", None) or {}).get("origin"):
            continue
        field_definitions = getattr(
            getattr(model, "_meta", None), "field_definitions", None
        )
        if field_definitions is None:
            continue
        models[model.__name__] = exporter.export_model(model)
    return {"models": models, "enums": dict(sorted(exporter.enums.items()))}
