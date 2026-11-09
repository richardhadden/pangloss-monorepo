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
    embedded        model, types, markers (what the field is annotated with that the server applies to
                    the value, `SortDefault(...)`: its name, and what it says of itself in `export()`)
    relation        many, reverseName, options, validators, subclasses (the names of the
                    fields of its ancestors that it stands for, directly or through another:
                    `RelationConfig(subclasses_parent_fields=...)`), defaultReifiedType
                    (the reified relation an entity found by searching is put in, or null:
                    `RelationConfig(default_reified_type=...)`), bindings (the fields of the model
                    given to fields of what it holds: `RelationConfig(bind_to_child_field=...)`)

A type is `{"type": "str"}` (also `int`, `float`, `bool`, `decimal`, `date`, `datetime`, `time`,
`duration`), with a `"format"` when the stored text means something more (`{"type": "str", "format":
"uuid"}`; also `url`, `email`, `ip`, `path`, `regex`, `fraction`), `{"type": "enum", "enum": "Name"}`
(the members are in `enums`), `{"type": "typedDict", "fields": {...}}`, `{"type": "list", "item": type}`
(with `"unique": true` for a set, `"length": n` for a tuple of a fixed length), `{"type": "literal",
"values": [...]}` or `{"type": "unknown", "repr": "..."}`. See `pangloss_models.literals`.

A literal or list field has `default`: the value the class declares for it (which the generated models
take, so the field may be left out), or null; `required` says whether it may be left out.
"""

import dataclasses
import enum
import inspect
import typing
from types import UnionType
from typing import Any, get_args, get_origin, is_typeddict

from pydantic.alias_generators import to_camel

from pangloss_models import literals
from pangloss_models.field_definitions import (
    AnnotatedValueFieldDefinition,
    EmbeddedFieldDefinition,
    FieldBinding,
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


class Exporter:
    def __init__(self) -> None:
        self.enums: dict[str, dict[str, Any]] = {}

    # --- types -----------------------------------------------------------

    def describe_type(self, tp: Any) -> dict[str, Any]:
        """A type as `pangloss_models.literals.export_type` says it (the enums met on the way are kept)"""
        origin = get_origin(tp)
        if origin in (
            typing.Annotated,
            typing.Required,
            typing.NotRequired,
            typing.ReadOnly,
        ):
            return self.describe_type(get_args(tp)[0])
        if origin is typing.Literal:
            return {"type": "literal", "values": [self.plain(v) for v in get_args(tp)]}
        if origin in literals.LIST_ORIGINS:
            item = literals.collection_item_type(tp)
            return {
                "type": "list",
                "item": self.describe_type(item)
                if item is not None
                else {"type": "unknown", "repr": "?"},
                **literals.collection_rule(tp),
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
                        for name, annotation in typing.get_type_hints(
                            tp, include_extras=True
                        ).items()
                    },
                }
            codec = literals.codec_for(tp)
            if codec is not None:
                return codec.describe()
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
        """What a field is annotated with, by name: the constraints of `annotated_types` (`Gt(5)`, `MaxLen(10)`)
        with their values, pydantic's `Strict` and the arguments of `Field(pattern=...)` or `StringConstraints`
        (as `Constraints`, with what was given), and its functional validators by name alone (`AfterValidator`:
        a function, which only the server runs). A callable is never exported"""
        result = []
        for validator in validators:
            name = type(validator).__name__
            entry: dict[str, Any] = {
                "name": "Constraints" if name.startswith("_Pydantic") else name
            }
            attributes = (
                {
                    f.name: getattr(validator, f.name)
                    for f in dataclasses.fields(validator)
                }
                if dataclasses.is_dataclass(validator)
                else dict(getattr(validator, "__dict__", {}))
            )
            for key, value in attributes.items():
                if value is None or callable(value):
                    continue
                entry[key] = self.plain(value)
            result.append(entry)
        return result

    def binding(self, binding: FieldBinding) -> dict[str, Any]:
        """A field of the model given to fields of what the relation holds (`bind_to_child_field`), by key: for the
        interface to copy it as it is typed. `converted`: it is changed on the way (`converter`), which only the
        server can do"""
        return {
            "boundField": to_camel(binding.bound_field),
            "childFields": [to_camel(name) for name in binding.child_fields],
            "allowedTypes": list(binding.allowed_type_names),
            "excludedTypes": list(binding.excluded_type_names),
            "converted": binding.converter is not None,
        }

    def markers(self, markers: tuple) -> list[dict[str, Any]]:
        """What an embedded field is annotated with (`SortDefault(...)`), by name, with what the marker says of
        itself (`export()`, if it has one) for an editor to show: the server applies them, the interface does not"""
        return [
            {"name": type(marker).__name__}
            | (self.plain(marker.export()) if hasattr(marker, "export") else {})
            for marker in markers
        ]

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
                # (what the collection itself says: a set has no repeats, a tuple a fixed length)
                "validators": self.validators(definition.validators)
                + self.collection_validators(definition.annotated_type),
                "itemValidators": self.validators(definition.inner_type_validators),
                "default": self.default(definition),
            }
        elif isinstance(definition, LiteralFieldDefinition):
            entry |= {
                "kind": "literal",
                "type": self.describe_type(definition.annotated_type),
                "validators": self.validators(definition.validators),
                "markers": self.markers(definition.markers),
                "default": self.default(definition),
            }
            for marker in definition.markers:
                marker.check(definition.field_on_model.__name__, entry)
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
            # (only a list says so: the export of a single value, and the snapshots made from it, are as they were)
            if definition.many:
                entry["many"] = True
        elif isinstance(definition, EmbeddedFieldDefinition):
            entry |= {
                "kind": "embedded",
                "model": definition.annotated_type.__name__
                if isinstance(definition.annotated_type, type)
                else None,
                "types": sorted(
                    o.annotated_type.__name__ for o in definition.type_options
                ),
                "markers": self.markers(definition.markers),
            }
        elif isinstance(definition, RelationFieldDefinition):
            entry |= {
                "kind": "relation",
                "many": definition.wrapper is not None,
                "reverseName": definition.reverse_name,
                "options": self.options(definition.type_options),
                "validators": self.validators(definition.validators),
                "subclasses": sorted(
                    {
                        s if isinstance(s, str) else s.field_name
                        for s in definition.subclasses_parent_fields
                    }
                ),
                "defaultReifiedType": definition.default_reified_type,
                "bindings": [
                    self.binding(binding) for binding in definition.bind_to_child_field
                ],
            }
        else:
            entry["kind"] = "unknown"
        return entry

    def collection_validators(self, annotation: Any) -> list[dict[str, Any]]:
        """The rule of a collection as validators: `Unique` for a set, `MinLen` and `MaxLen` for a tuple of a
        fixed length (which the interface already checks on a list)"""
        rule = literals.collection_rule(literals.without_none(annotation))
        found: list[dict[str, Any]] = []
        if rule.get("unique"):
            found.append({"name": "Unique"})
        if "length" in rule:
            found.append({"name": "MinLen", "min_length": rule["length"]})
            found.append({"name": "MaxLen", "max_length": rule["length"]})
        return found

    def default(self, definition: Any) -> Any:
        """The default the class declares for a literal or list field, as JSON can have it; None for none"""
        if not definition.has_default:
            return None
        return self.plain(definition.default_value())

    def field_requirements(self, definition: FieldDefinition) -> dict[str, Any]:
        """Whether the field may be left out, or be null, as the model declares it (and as `Create` has it: a field
        declared `X | None` may be left out)"""
        try:
            model_field = definition.model_field
        except Exception:
            return {"required": False, "nullable": False}
        annotation = model_field.annotation
        nullable = annotation is type(None) or type(None) in get_args(annotation)
        return {
            "required": model_field.is_required() and not nullable,
            "nullable": nullable,
        }

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
        from pangloss_models.utils import (
            get_concrete_types,
            get_parent_class,
            model_is_trait,
        )

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
            # (a document that is only ever part of another; an entity always can be)
            "createDirectly": bool(getattr(meta, "create_directly", True)),
            "acceptUrlAsId": bool(getattr(meta, "accept_url_as_id", False)),
            "globalSearch": bool(getattr(meta, "global_search", True)),
            "requireLabel": bool(getattr(meta, "require_label", True)),
            "useInSemanticSpaceLabel": bool(
                getattr(meta, "use_in_semantic_space_label", True)
            ),
            "fields": [
                self.export_field(n, d)
                for n, d in meta.field_definitions.fields.items()
            ],
            "incoming": self.incoming(meta.field_definitions.incoming_fields),
            # (the traits it has, by name: a module can tell "anything dateable" without reading its fields)
            "traits": sorted(
                c.__name__
                for c in model.__mro__
                if c is not model
                and model_is_trait(c)
                and c.__name__ != "Trait"
                and not c.__module__.startswith("pangloss_models.model_bases")
            ),
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
