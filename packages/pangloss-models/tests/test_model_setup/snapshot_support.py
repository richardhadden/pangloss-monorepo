"""Describe the models that `initialise()` makes as plain, ordered data, so that they can be
compared with a stored snapshot.

The snapshot is a characterisation test: it pins what the initialisation produces now (the
fields of every generated model, with their annotations, defaults, aliases and
discriminators, and the field definitions and incoming relations they were made from), so
that the code which makes them can be restructured and shown to make the same thing.

Everything is made deterministic: unions and sets are sorted, memory addresses are not
used, and classes are named, not shown with `repr`.
"""

import json
import re
import types
import typing
from collections.abc import Iterable
from enum import Enum
from typing import Annotated, Any, Literal, TypeVar, Union, get_args, get_origin

from pangloss_models.field_definitions import FieldBinding, FieldSubclassing
from pangloss_models.model_registry import ModelRegistry
from pydantic import BaseModel
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

GENERATED = (
    "Create",
    "CreateDB",
    "Update",
    "UpdateDB",
    "View",
    "HeadView",
    "EditView",
    "ReferenceSet",
    "ReferenceView",
)


_ADDRESS = re.compile(r" at 0x[0-9a-f]+")
_BOUND = re.compile(r"\[bound=\((.*?)\)\]")
_BINDING = re.compile(
    r"FieldBinding\(bound_field='(.*?)', child_fields=\[(.*?)\], allowed_type_names=\[(.*?)\], "
    r"excluded_type_names=\[(.*?)\], converter=(.*)\)$"
)


def normalise_name(name: str) -> str:
    """The name of a generated class, made the same on every run.

    A model with field bindings is named with them, taken from a `frozenset` in whatever order
    that has, and with the address of a converter function in it. Here they are sorted and short."""

    def bindings(match: re.Match) -> str:
        parts = match.group(1).split(",FieldBinding(")
        short = []
        for part in parts:
            part = part if part.startswith("FieldBinding(") else "FieldBinding(" + part
            found = _BINDING.match(part)
            if not found:
                short.append(part)
                continue
            bound, children, allowed, excluded, converter = found.groups()
            short.append(
                f"{bound}->{children.replace(chr(39), '')}"
                + (f" only {allowed.replace(chr(39), '')}" if allowed else "")
                + (f" not {excluded.replace(chr(39), '')}" if excluded else "")
                + (" converted" if converter != "None" else "")
            )
        return "[bound=" + "; ".join(sorted(short)) + "]"

    return sort_brackets(_BOUND.sub(bindings, _ADDRESS.sub("", name)))


def sort_brackets(text: str) -> str:
    """Sort the comma-separated parts inside every `[...]` of a name, nested ones first.

    The names of generated classes list the types they were made for (`InRole[Person, Group]`) in
    the order of a set, which is not the same on every run."""
    result, i = "", 0
    while i < len(text):
        if text[i] != "[":
            result += text[i]
            i += 1
            continue
        depth, j = 1, i + 1
        while j < len(text) and depth:
            depth += {"[": 1, "]": -1}.get(text[j], 0)
            j += 1
        inner = text[i + 1 : j - 1]
        parts, level, start = [], 0, 0
        for k, char in enumerate(inner):
            level += {"[": 1, "]": -1}.get(char, 0)
            if char == "," and level == 0:
                parts.append(inner[start:k].strip())
                start = k + 1
        parts.append(inner[start:].strip())
        result += "[" + ", ".join(sorted(sort_brackets(p) for p in parts)) + "]"
        i = j
    return result


def describe_union(members: tuple[Any, ...]) -> str:
    """A union with its members in a stable order.

    The order of the members that stand for one model (an `Update` and a `Create` of the same
    document) is kept, as pydantic can use it to choose between members that both fit; groups of
    members are sorted, as the order in which a set of types was visited is not stable."""
    groups: dict[str, list[str]] = {}
    for member in members:
        owner = getattr(member, "_owner", None) if isinstance(member, type) else None
        key = owner.__name__ if isinstance(owner, type) else describe_type(member)
        groups.setdefault(key, []).append(describe_type(member))
    return " | ".join(" > ".join(groups[key]) for key in sorted(groups))


def describe_type(annotation: Any) -> str:
    """A string for an annotation: classes by name, unions sorted, `Annotated` by its parts"""
    if annotation is None or annotation is type(None):
        return "None"
    if annotation is Ellipsis:
        return "..."
    if isinstance(annotation, TypeVar):
        return f"TypeVar({annotation.__name__})"
    if isinstance(annotation, str):
        return f"'{annotation}'"

    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin is Annotated:
        inner, *metadata = args
        return f"Annotated[{describe_type(inner)}; {'; '.join(describe_metadata(m) for m in metadata)}]"
    if origin is Union or origin is types.UnionType:
        return describe_union(args)
    if origin is Literal:
        return f"Literal[{', '.join(repr(a) for a in args)}]"
    if origin is not None:
        name = getattr(origin, "__name__", repr(origin))
        return f"{name}[{', '.join(describe_type(a) for a in args)}]"
    if isinstance(annotation, type):
        return normalise_name(annotation.__name__)
    return type(annotation).__name__


def describe_metadata(metadata: Any) -> str:
    if isinstance(metadata, FieldInfo):
        return "Field(" + describe_field_extras(metadata) + ")"
    if isinstance(metadata, type):
        return normalise_name(metadata.__name__)
    return describe_value(metadata)


def describe_value(value: Any) -> str:
    """A stable string for a default, a validator or a config object"""
    if value is PydanticUndefined:
        return "<undefined>"
    if isinstance(value, Enum):
        return f"{type(value).__name__}.{value.name}"
    if isinstance(value, type):
        return normalise_name(value.__name__)
    if isinstance(value, FieldBinding):
        return (
            f"FieldBinding(bound_field={value.bound_field!r}, child_fields={value.child_fields!r}, "
            f"allowed={value.allowed_type_names!r}, excluded={value.excluded_type_names!r}, "
            f"converter={getattr(value.converter, '__name__', None)!r})"
        )
    if isinstance(value, FieldSubclassing):
        return (
            f"FieldSubclassing({value.field_name!r}, on={getattr(value.field_on_model, '__name__', None)}, "
            f"disambiguator={value.disambiguator!r})"
        )
    if callable(value) and hasattr(value, "__name__"):
        return f"<function {value.__name__}>"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(describe_value(v) for v in value) + "]"
    if isinstance(value, (set, frozenset)):
        return "{" + ", ".join(sorted(describe_value(v) for v in value)) + "}"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{k!r}: {describe_value(v)}" for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))) + "}"
    if hasattr(value, "__dataclass_fields__"):
        parts = ", ".join(
            f"{name}={describe_value(getattr(value, name))}"
            for name in value.__dataclass_fields__
        )
        return f"{type(value).__name__}({parts})"
    text = repr(value)
    if " at 0x" in text:  # (an address would change from run to run)
        return type(value).__name__
    return text


def describe_field_extras(field: FieldInfo) -> str:
    parts = []
    for name in ("discriminator", "description", "alias", "validation_alias", "serialization_alias"):
        value = getattr(field, name, None)
        if value is not None:
            parts.append(f"{name}={describe_value(value)}")
    return ", ".join(parts)


def describe_field(field: FieldInfo) -> dict[str, Any]:
    default_factory = getattr(field.default_factory, "__name__", None) if field.default_factory else None
    return {
        "annotation": describe_type(field.annotation),
        "required": field.is_required(),
        "default": None if field.default is PydanticUndefined else describe_value(field.default),
        "default_factory": default_factory,
        "alias": field.alias,
        "validation_alias": describe_value(field.validation_alias) if field.validation_alias else None,
        "discriminator": describe_value(field.discriminator) if field.discriminator else None,
        "description": field.description,
        "metadata": [describe_metadata(m) for m in field.metadata],
    }


def models_in(annotation: Any) -> Iterable[type[BaseModel]]:
    """Every pydantic model that an annotation mentions"""
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        yield annotation
    for arg in get_args(annotation):
        yield from models_in(arg)


def describe_model(model: type[BaseModel]) -> dict[str, Any]:
    decorators = getattr(model, "__pydantic_decorators__", None)
    # (the schema itself is not kept: pydantic numbers clashing definition names in an order that
    # is not stable; what the schema is made from, the fields, is what is compared)
    try:
        model.model_json_schema(by_alias=True)
        json_schema = "ok"
    except Exception as error:
        json_schema = f"error: {type(error).__name__}"
    owner = getattr(model, "_owner", None)
    return {
        "bases": [normalise_name(b.__name__) for b in model.__bases__ if b is not object],
        "owner": getattr(owner, "__name__", None) if isinstance(owner, type) else None,
        "doc": model.__doc__,
        "alias_generator": getattr(model.model_config.get("alias_generator"), "__name__", None),
        "model_validators": sorted(decorators.model_validators) if decorators else [],
        "field_validators": sorted(decorators.field_validators) if decorators else [],
        "fields": {name: describe_field(field) for name, field in model.model_fields.items()},
        "json_schema": json_schema,
    }


def describe_relation_option(option: Any) -> str:
    parts = [type(option).__name__]
    for name in ("annotated_type", "base_type", "edge_model", "type_var_name"):
        if hasattr(option, name) and getattr(option, name) is not None:
            parts.append(f"{name}={describe_type(getattr(option, name))}")
    parameters = getattr(option, "parameter_type_options", None)
    if parameters:
        inner = {
            key: sorted(describe_relation_option(o) for o in value.type_options)
            for key, value in parameters.items()
        }
        parts.append(f"parameters={describe_value(inner)}")
    return "(" + ", ".join(parts) + ")"


def describe_field_definition(definition: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "kind": type(definition).__name__,
        "annotated_type": describe_type(definition.annotated_type),
        "db_field": definition.db_field,
        "description": definition.description,
        "field_on_model": getattr(definition.field_on_model, "__name__", None),
        "required_to_fulfil": sorted(
            f"{f.field_name}@{f.fulfils_class.__name__}" for f in definition.field_required_to_fulfil
        ),
    }
    for name in ("inner_type", "type_var_name"):
        if hasattr(definition, name):
            result[name] = describe_type(getattr(definition, name))
    for name in ("validators", "inner_type_validators"):
        if hasattr(definition, name):
            result[name] = [describe_value(v) for v in getattr(definition, name)]
    if hasattr(definition, "type_options"):
        result["type_options"] = sorted(describe_relation_option(o) for o in definition.type_options)
    if hasattr(definition, "reverse_name"):
        result["reverse_name"] = definition.reverse_name
        result["wrapper"] = getattr(definition.wrapper, "__name__", None)
        result["subclasses_parent_fields"] = sorted(describe_value(s) for s in definition.subclasses_parent_fields)
        result["bind_to_child_field"] = [describe_value(b) for b in definition.bind_to_child_field]
    return result


def describe_declared(model: type) -> dict[str, Any]:
    meta = model._meta  # type: ignore[attr-defined]
    definitions = meta.field_definitions
    incoming = {
        name: sorted(
            f"{i.source.__name__}.{i.field_definition.field_name} (reified={i.via_reified})"
            for i in items
        )
        for name, items in sorted(definitions.incoming_fields.items())
    }
    options = {}
    for name, value in meta.model_dump(exclude={"field_definitions"}).items():
        options[name] = describe_value(value)
    return {
        "kind": getattr(model, "__metatype__", None),
        "meta": options,
        "depends_on": sorted(c.__name__ for c in getattr(model, "_depends_on_classes", ())),
        "field_definitions": {
            name: describe_field_definition(d) for name, d in definitions.fields.items()
        },
        "incoming": incoming,
    }


def snapshot_registry() -> dict[str, Any]:
    """Everything the initialisation made, for the models now in the registry"""
    declared: dict[str, Any] = {}
    generated: dict[str, Any] = {}
    seen: dict[int, str] = {}  # (id of a model class -> its key), to describe each class once
    classes: list[type[BaseModel]] = []

    def add(model: type[BaseModel], key: str) -> None:
        if id(model) in seen:
            return
        key = normalise_name(key)
        if key in generated:  # (two different classes with one name: say so)
            key = f"{key}#{sum(1 for k in generated if k.split('#')[0] == key) + 1}"
        seen[id(model)] = key
        generated[key] = describe_model(model)
        classes.append(model)

    # first the models that a declared class owns (`Person.Create`), so that their keys do not
    # depend on which model happened to mention them first; then the ones found only inside
    # annotations (made for a bound or generic relation, with an edge model, ...)
    for model in ModelRegistry._models:
        declared[model.__name__] = describe_declared(model)
        for attribute in GENERATED:
            made = model.__dict__.get(attribute)
            if isinstance(made, type) and issubclass(made, BaseModel):
                add(made, f"{model.__name__}.{attribute}")

    index = 0
    while index < len(classes):  # (the list grows as nested models are found)
        for field in classes[index].model_fields.values():
            for nested in models_in(field.annotation):
                add(nested, nested.__name__)
        index += 1
    return {"declared": declared, "generated": generated}


def dumps(snapshot: dict[str, Any]) -> str:
    return json.dumps(snapshot, indent=1, sort_keys=True, ensure_ascii=False, default=str) + "\n"
