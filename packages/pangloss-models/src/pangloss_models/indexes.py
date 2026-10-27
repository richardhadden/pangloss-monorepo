"""The indexes the models ask for (see docs/structured-search.md, "Which indexes help").

A search of a class starts at the nodes with the label of its name, and without an index finds them by
looking at every node of the database. So each class of document and entity has an index of its label
(the nodes of its subclasses have it too), and a class can ask for an index of the fields that are searched
for particular values, with `indexes` in its `Meta`:

    class Letter(Document):
        _meta = Document.Meta(indexes=["year"])
        year: int

The entries are plain data, as the snapshot of the models has them (`{"kind", "label", "properties"}`); the
database package makes them.
"""

from typing import Any

from pangloss_models.exceptions import PanglossMetaError
from pangloss_models.field_definitions import (
    ListFieldDefinition,
    LiteralFieldDefinition,
)
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.embedded import Embedded
from pangloss_models.model_bases.entity import Entity


def indexed_classes() -> list[type]:
    """The classes of documents and entities (abstract ones too: a search of a parent class starts at its label),
    and the embedded classes that ask for an index of a field"""
    from pangloss_models.model_registry import ModelRegistry

    return sorted(
        (
            model
            for model in ModelRegistry.all_models().values()
            if isinstance(model, type)
            and (
                issubclass(model, (Document, Entity))
                or (issubclass(model, Embedded) and model._meta.indexes)
            )
        ),
        key=lambda model: model.__name__,
    )


def check_indexes(model: type) -> None:
    """Whether the fields a class asks for indexes of are ones that have a value of their own"""
    names = list(getattr(model._meta, "indexes", []))  # type: ignore
    if len(set(names)) != len(names):
        raise PanglossMetaError(f"{model.__name__}: indexes names a field twice")
    fields = model._meta.fields  # type: ignore
    for name in names:
        if (
            name == "label" and getattr(model, "__metatype__", None) != "Embedded"
        ):  # (every document and entity has one: it is not one of the fields)
            continue
        definition = fields.get(name)
        if definition is None:
            raise PanglossMetaError(
                f"{model.__name__}: indexes names '{name}', which is not a field of it"
            )
        if not isinstance(definition, (LiteralFieldDefinition, ListFieldDefinition)):
            raise PanglossMetaError(
                f"{model.__name__}: '{name}' cannot be indexed: only a field with a value of its own "
                "(text, a number, a date, a choice, a list of these) is stored as a property"
            )


def model_indexes() -> list[dict[str, Any]]:
    """The indexes of the registered models: the label of each class, and each field it asks for"""
    entries: list[dict[str, Any]] = []
    for model in indexed_classes():
        if not issubclass(model, Embedded):
            entries.append({"kind": "label", "label": model.__name__, "properties": []})
        for name in model._meta.indexes:  # type: ignore
            entries.append(
                {
                    "kind": "label+property",
                    "label": model.__name__,
                    "properties": [name],
                }
            )
    return entries
