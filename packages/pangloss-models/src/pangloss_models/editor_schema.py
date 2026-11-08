"""What an editor needs to complete a project's models (`pangloss check --json`, the language server).

It is made from the classes themselves, never kept by hand: the options of each `Meta`, with the comment above each
one as its documentation; the meta slots the installed apps registered; the models, and the kind of each of their
fields. A meta class can say what values one of its options takes by an `editor_choices(option)` class method (the
interface's `view_card` takes the components of the installed interface modules, which only it can find).
"""

import dataclasses
import enum
import inspect
import re
import types
import typing
from collections.abc import Iterable
from typing import Any, Literal, get_args, get_origin

from pydantic import BaseModel
from pydantic_core import PydanticUndefined

from pangloss_models.diagnostics import _type_name
from pangloss_models.model_bases.binding import NOT_MODELS

# (a base class whose `Meta` an author calls: `Document.Meta(...)`)
BASE_CLASSES = (
    "Document",
    "Entity",
    "Embedded",
    "ReifiedRelation",
    "ReifiedRelationDocument",
    "SemanticSpace",
    "Conjunction",
    "Trait",
    "NonHeritableTrait",
    "EdgeModel",
    "AnnotatedValue",
)

# (the config objects an author writes in an `Annotated` or a `_meta`, that are not a `Meta` of a class)
CONFIG_CLASSES = ("RelationConfig", "FieldBinding")

# (what a field definition is, for what a completion offers: an index names a value the node holds)
FIELD_KINDS = {
    "LiteralFieldDefinition": "literal",
    "ListFieldDefinition": "list",
    "AnnotatedValueFieldDefinition": "annotated",
    "EmbeddedFieldDefinition": "embedded",
    "RelationFieldDefinition": "relation",
}


def comments_above_fields(cls: type) -> dict[str, str]:
    """The comment lines directly above each annotated name in a class body, as one sentence per field. (This is
    how the classes document their options: a comment above the line, not a docstring below it)"""
    try:
        source = inspect.getsource(cls)
    except OSError, TypeError:
        return {}
    lines = source.splitlines()
    # (the `class` line may come after decorators)
    start = next(
        (i for i, line in enumerate(lines) if line.lstrip().startswith("class ")), 0
    )
    body = lines[start + 1 :]
    first = next((line for line in body if line.strip()), "")
    member_indent = len(first) - len(first.lstrip())
    comments: dict[str, str] = {}
    pending: list[str] = []
    for line in body:
        stripped = line.strip()
        if stripped.startswith("#"):
            pending.append(stripped.lstrip("#").strip())
            continue
        # (a blank line breaks a comment from the field below it: it is about the section, not the field)
        if not stripped:
            pending = []
            continue
        declared = re.match(r"([A-Za-z_]\w*)\s*:", stripped)
        indent = len(line) - len(line.lstrip())
        if declared and pending and indent == member_indent:
            text = " ".join(pending)
            # (a comment in parentheses is an aside to the code, and the whole of it is the documentation)
            comments[declared[1]] = (
                text[1:-1] if text.startswith("(") and text.endswith(")") else text
            )
        pending = []
    return comments


def _union_members(annotation: Any) -> tuple[Any, ...]:
    if get_origin(annotation) in (typing.Union, types.UnionType):
        return get_args(annotation)
    return (annotation,)


def choices_of(annotation: Any) -> list[tuple[str, bool]]:
    """The values an annotation allows, as `(source text, is it a string)`, if it is a short list of them"""
    values: list[tuple[str, bool]] = []
    for member in _union_members(annotation):
        if get_origin(member) is typing.Annotated:
            member = get_args(member)[0]
        if get_origin(member) is Literal:
            for value in get_args(member):
                values.append((str(value), isinstance(value, str)))
        elif member is bool:
            values += [("True", False), ("False", False)]
        elif isinstance(member, type) and issubclass(member, enum.Enum):
            values += [(str(m.value), isinstance(m.value, str)) for m in member]
        elif isinstance(member, typing.TypeAliasType):
            values += choices_of(member.__value__)
    return values


def _parameters(meta_class: type) -> list[dict[str, Any]]:
    documentation = {}
    for base in reversed(meta_class.__mro__):
        documentation |= comments_above_fields(base)
    fields: list[tuple[str, Any, Any]] = []
    if issubclass(meta_class, BaseModel):
        for name, info in meta_class.model_fields.items():
            default = (
                info.default_factory()
                if info.default_factory is not None
                else info.default
            )
            fields.append((name, info.annotation, default))
    elif dataclasses.is_dataclass(meta_class):
        hints = typing.get_type_hints(meta_class, include_extras=True)
        for field in dataclasses.fields(meta_class):
            if not field.init:
                continue
            default = (
                field.default_factory()
                if field.default_factory is not dataclasses.MISSING
                else field.default
            )
            fields.append((field.name, hints.get(field.name, field.type), default))
    else:
        return []

    editor_choices = getattr(meta_class, "editor_choices", None)
    parameters = []
    for name, annotation, default in fields:
        # (the internals of the meta objects are not options: what the models fill in themselves)
        if name.startswith("_") or name in ("field_definitions", "fields"):
            continue
        shown: str | None
        if default is PydanticUndefined or default is dataclasses.MISSING:
            shown = None
        elif "InheritValue" in repr(default):
            shown = "inherited"
        else:
            shown = repr(default)
        offered = editor_choices(name) if callable(editor_choices) else None
        choices = (
            [(text, True) for text in offered]
            if offered is not None
            else choices_of(annotation)
        )
        parameters.append(
            {
                "name": name,
                "type": _type_name(annotation),
                "default": shown,
                "doc": documentation.get(name),
                "choices": choices,
            }
        )
    return parameters


def _describe(meta_class: type) -> dict[str, Any]:
    # (its own docstring: not a parent's, and not the signature that a dataclass gives itself, which in Python 3.15
    # is a lazy object that is not a str)
    own = meta_class.__doc__ if "__doc__" in vars(meta_class) else None
    doc = inspect.cleandoc(own) if own else None
    if doc and doc.startswith(f"{meta_class.__name__}("):
        doc = None
    return {
        "doc": " ".join(doc.split("\n\n")[0].split()) if doc else None,
        "parameters": _parameters(meta_class),
    }


def _public_class(name: str) -> type | None:
    import pangloss_models

    found = getattr(pangloss_models, name, None)
    return found if isinstance(found, type) else None


def import_root(cls: type) -> str:
    """The package to import a class from: the root of the one that defines it, if that exports it (the roots of
    packages list their public names)"""
    root = cls.__module__.split(".")[0]
    module = __import__(root)
    return root if getattr(module, cls.__name__, None) is cls else cls.__module__


def editor_schema() -> dict[str, Any]:
    """Everything an editor needs, as plain data. The models should have been initialised (the meta slots of the
    installed apps are known once their packages are imported)"""
    from pangloss_models.meta_slots import meta_slots
    from pangloss_models.model_registry import ModelRegistry

    calls: dict[str, dict[str, Any]] = {}
    aliases: dict[str, str] = {}

    def add_meta(owner: str, meta_class: Any) -> None:
        if not isinstance(meta_class, type):
            return
        if meta_class.__name__ not in calls:
            calls[meta_class.__name__] = _describe(meta_class)
        aliases[f"{owner}.Meta"] = meta_class.__name__

    for name in BASE_CLASSES:
        base = _public_class(name)
        if base is not None:
            add_meta(name, getattr(base, "Meta", None))
    for name, model in ModelRegistry.all_models().items():
        add_meta(name, getattr(model, "Meta", None))
    for name in CONFIG_CLASSES:
        config = _public_class(name)
        if config is not None:
            calls[name] = _describe(config)

    slots = []
    for slot, meta_class in sorted(meta_slots().items()):
        calls.setdefault(meta_class.__name__, _describe(meta_class))
        slots.append(
            {
                "name": slot,
                "class": meta_class.__name__,
                "module": import_root(meta_class),
                "doc": calls[meta_class.__name__]["doc"],
            }
        )

    return {
        "calls": calls,
        "aliases": aliases,
        "slots": slots,
        "models": models_summary(ModelRegistry.all_models().items()),
    }


def models_summary(models: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    """Each model: what it is, and the kind of each of its fields (inherited ones too)"""
    summary: dict[str, Any] = {}
    models = list(models)
    names = {name for name, _ in models}
    for name, model in models:
        meta = getattr(model, "_meta", None)
        definitions = getattr(getattr(meta, "field_definitions", None), "fields", None)
        own_doc = model.__dict__.get("__doc__")
        summary[name] = {
            "kind": getattr(model, "__metatype__", None),
            "abstract": bool(getattr(meta, "abstract", False)),
            # (its own docstring, not a parent's, and not the one pydantic gives a model that has none)
            "doc": " ".join(inspect.cleandoc(own_doc).split("\n\n")[0].split())
            if own_doc
            else None,
            "indexes": list(getattr(meta, "indexes", None) or []),
            # (the classes above it that are the project's: its parents and traits, nearest first)
            "above": [
                parent.__name__
                for parent in model.__mro__[1:]
                if not parent.__module__.startswith(NOT_MODELS)
                and parent.__name__ in names
            ],
            "fields": {
                field: FIELD_KINDS.get(type(definition).__name__, "other")
                for field, definition in (definitions or {}).items()
            },
            "where": where_keys(model),
        }
    return summary


def where_keys(model: Any) -> list[dict[str, str]]:
    """The keywords of `Model.Where(...)`: the fields that can be searched, then the `$` keys. (Read from the
    generated class, which leaves out what cannot be searched yet)"""
    where = model.__dict__.get("Where")
    fields = getattr(where, "model_fields", None)
    if not fields:
        return []
    return [
        {"name": name, "type": _type_name(info.annotation)}
        for name, info in fields.items()
    ]
