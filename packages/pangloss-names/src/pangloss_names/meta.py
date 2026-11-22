"""`_names_meta`: which classes have names, and which of their fields are names (implementation_docs/similarity-build-plan.md,
step 8.3).

    class Person(Entity):
        aliases: list[str] = []
        _names_meta = NamesMeta(fields=["label", "aliases"])

    class Letter(Document):
        _names_meta = NamesMeta(include=True)        # its label is a name

    class Place(Entity):
        _names_meta = NamesMeta(include=False)       # no name vector

A subclass has its parent's setting unless it sets its own (a trait's counts for the classes that have it). With
none anywhere, **an entity has names** (its `label`) and **a document has none**.

- `fields` (`["label"]`): the fields whose values are the item's names. `label` is every document's and entity's;
  any other is a field the class declares as text: `str`, `str | None`, or `list[str]` (each item one name).
- `include`: whether the items of the class have names, and so a name vector.

A class that `pangloss-vectors` gives no vectors (`pangloss_vectors.meta.included`) has no name vector either.
Refused at `initialise()`, by the name of the class that says it: a field the class has not, or one that is not
text; no field at all; the slot on a class that is not one of documents or entities, nor a trait.
"""

import dataclasses
from collections.abc import Sequence
from inspect import isclass
from typing import Any

from pangloss_models import ModelRegistry, PanglossMetaError, register_meta_slot
from pangloss_models.exceptions import did_you_mean
from pangloss_models.meta_slots import declared_slots

SLOT = "_names_meta"

# (every head has it, from the base models: it is not among a class's declared fields)
LABEL = "label"


@dataclasses.dataclass(frozen=True)
class NamesMeta:
    fields: Sequence[str] = (LABEL,)
    """The fields whose values are names: `label`, and fields of the class that are `str`, `str | None` or
    `list[str]`"""

    include: bool = True
    """Whether the items of the class have names"""


register_meta_slot(SLOT, NamesMeta)

ENTITY_DEFAULT = NamesMeta()
DOCUMENT_DEFAULT = NamesMeta(include=False)

ITEM_KINDS = ("Document", "Entity")


def _kind(model: type) -> str | None:
    return getattr(model, "__metatype__", None)


def names_meta(model: type) -> NamesMeta:
    """The class's setting, its parent's (or a trait's), or the default of its kind (an entity's has names, a
    document's has none)"""
    meta = getattr(model, SLOT, None)
    if isinstance(meta, NamesMeta):
        return meta
    return ENTITY_DEFAULT if _kind(model) == "Entity" else DOCUMENT_DEFAULT


def declarer(model: type) -> str:
    """The name of the class that sets the setting `model` has (itself, a parent or a trait)"""
    for cls in model.__mro__:
        if SLOT in declared_slots(cls):
            return cls.__name__
    return model.__name__


def _is_generic(model: type) -> bool:
    """A generic base (`class Wrapper[T](Document)`) or a use of one (`Wrapper[Person]`)"""
    metadata = getattr(model, "__pydantic_generic_metadata__", None) or {}
    return (
        bool(metadata.get("parameters"))
        or metadata.get("origin") is not None
        or "[" in model.__name__
    )


def item_classes() -> list[tuple[str, type]]:
    """The registered classes of documents and entities a node can be of, by name: not abstract, no generics"""
    return [
        (name, model)
        for name, model in sorted(ModelRegistry._model_dict.items())
        if isclass(model)
        and _kind(model) in ITEM_KINDS
        and not _is_generic(model)
        and not getattr(getattr(model, "_meta", None), "abstract", False)
    ]


def _is_text(definition: Any) -> bool:
    """A field that holds text: `str`, `str | None`, or `list[str]`"""
    from pangloss_models.field_definitions import (
        ListFieldDefinition,
        LiteralFieldDefinition,
    )

    if isinstance(definition, ListFieldDefinition):
        return definition.inner_type is str
    if isinstance(definition, LiteralFieldDefinition):
        return definition.annotated_type in (str, str | None)
    return False


def _fields_of(model: type) -> dict[str, Any]:
    fields = getattr(getattr(model, "_meta", None), "fields", None)
    return dict(fields) if fields is not None else {}


def check_meta() -> None:
    """(`ModelRegistry.after_finalise`, when the fields of every class are known) refuse what a `NamesMeta` cannot
    mean, by the name of the class that says it"""
    from pangloss_models.utils import model_is_trait

    for name, model in sorted(ModelRegistry._model_dict.items()):
        if not isclass(model) or SLOT not in declared_slots(model):
            continue
        kind = _kind(model)
        if kind not in ITEM_KINDS and not model_is_trait(model):
            raise PanglossMetaError(
                f"{name}: NamesMeta is for a class of documents or entities (or a trait they have), and {name} is "
                f"{'an edge model' if kind == 'EdgeModel' else 'a wrapper, which has no vector'}"
            )
        meta = getattr(model, SLOT)
        if isinstance(meta.fields, str) or not isinstance(meta.fields, Sequence):
            raise PanglossMetaError(
                f"{name}: NamesMeta(fields=...) is a list of the fields that are names (['label']), not "
                f"{meta.fields!r}"
            )
        if meta.include and not meta.fields:
            raise PanglossMetaError(
                f"{name}: NamesMeta(fields=[]) names no field: its items would have no names (say include=False)"
            )
    for name, model in item_classes():
        meta = names_meta(model)
        if not meta.include:
            continue
        said = declarer(model)
        fields = _fields_of(model)
        for field in meta.fields:
            if field == LABEL:
                continue
            definition = fields.get(field)
            if definition is None:
                raise PanglossMetaError(
                    f"{said}: NamesMeta(fields=...) names {field!r}, which is not a field of {name}."
                    f"{did_you_mean(field, [LABEL, *fields])}"
                )
            if not _is_text(definition):
                raise PanglossMetaError(
                    f"{said}: NamesMeta(fields=...) names {field!r}, which is not text in {name}: a name field is "
                    "`str`, `str | None` or `list[str]`"
                )


def has_names(model: type) -> bool:
    """Whether items of the class have names: its `NamesMeta`, and vectors at all (`pangloss_vectors.meta`)"""
    from pangloss_vectors.meta import model_included

    return names_meta(model).include and model_included(model)


def named() -> dict[str, list[str]]:
    """Each class of documents or entities that has names, by name, with its name fields (in the order given, each
    once)"""
    return {
        name: list(dict.fromkeys(names_meta(model).fields))
        for name, model in item_classes()
        if has_names(model)
    }


def install() -> None:
    if check_meta not in ModelRegistry.after_finalise:
        ModelRegistry.after_finalise.append(check_meta)


# (done as soon as a model can say it, whether or not the app is installed)
install()
