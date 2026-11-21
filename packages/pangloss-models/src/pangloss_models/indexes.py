"""The indexes the models ask for (see implementation_docs/structured-search.md, "Which indexes help").

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

from pangloss_models import literals
from pangloss_models.exceptions import AtString, PanglossMetaError, did_you_mean
from pangloss_models.field_definitions import (
    ListFieldDefinition,
    LiteralFieldDefinition,
)
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.embedded import Embedded
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.reified_relation import ReifiedRelation


def indexed_classes() -> list[type]:
    """The classes of documents and entities (abstract ones too: a search of a parent class starts at its label),
    the embedded classes that ask for an index of a field, and the reified relations that ask for one of their label"""
    from pangloss_models.model_registry import ModelRegistry

    return sorted(
        (
            model
            for model in ModelRegistry.all_models().values()
            if isinstance(model, type)
            and (
                issubclass(model, (Document, Entity))
                or (issubclass(model, Embedded) and model._meta.indexes)
                or (
                    issubclass(model, ReifiedRelation)
                    and getattr(model._meta, "label_index", False)
                    # (the class as declared: one bound to what it holds, `Name[...]`, is written with its label)
                    and model.__name__.isidentifier()
                )
            )
        ),
        key=lambda model: model.__name__,
    )


def check_indexes(model: type) -> None:
    """Whether the fields a class asks for indexes of are ones that have a value of their own"""
    names = list(getattr(model._meta, "indexes", []))  # type: ignore
    fields = model._meta.fields  # type: ignore
    has_label = getattr(model, "__metatype__", None) != "Embedded"
    # (what could have been meant: every document and entity has a label, which is not one of the fields)
    indexable = [
        name
        for name, definition in fields.items()
        if isinstance(definition, (LiteralFieldDefinition, ListFieldDefinition))
    ] + (["label"] if has_label else [])
    for name in names:
        if names.count(name) > 1:
            raise PanglossMetaError(
                f"{model.__name__}: indexes names '{name}' twice",
                at_string=AtString("indexes", name),
            )
    for name in names:
        if name == "label" and has_label:
            continue
        definition = fields.get(name)
        if definition is None:
            raise PanglossMetaError(
                f"{model.__name__}: indexes names '{name}', which is not a field of it."
                + did_you_mean(name, indexable),
                at_string=AtString("indexes", name, tuple(indexable)),
            )
        if not isinstance(definition, (LiteralFieldDefinition, ListFieldDefinition)):
            raise PanglossMetaError(
                f"{model.__name__}: '{name}' cannot be indexed: only a field with a value of its own "
                "(text, a number, a date, a choice, a list of these) is stored as a property",
                at_string=AtString("indexes", name),
            )
        base = (
            definition.inner_type
            if isinstance(definition, ListFieldDefinition)
            else definition.annotated_type
        )
        if literals.search_kind_of(base) == "decimal":
            # (a Decimal is stored as text, to keep its exact value, and a search compares it as a number
            # (`toFloat`), which no index of the text serves)
            raise PanglossMetaError(
                f"{model.__name__}: '{name}' is a Decimal, which is stored as text and compared as a number: "
                "an index of it would not be used. Store a float beside it if it is to be searched by range",
                at_string=AtString("indexes", name),
            )


def model_indexes() -> list[dict[str, Any]]:
    """The indexes of the registered models: the label of each class, and each field it asks for"""
    entries: list[dict[str, Any]] = []
    for model in indexed_classes():
        if not issubclass(model, Embedded):
            entries.append({"kind": "label", "label": model.__name__, "properties": []})
        for name in getattr(model._meta, "indexes", ()):  # type: ignore
            entries.append(
                {
                    "kind": "label+property",
                    "label": model.__name__,
                    "properties": [name],
                }
            )
    return entries


def installed_app_structure() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The indexes and constraints that installed apps ask for, for nodes that are not models (the calendar's days),
    for the `structure()` of each database package. An app with a `structure` module has `INDEXES` and `CONSTRAINTS`,
    lists of entries as in the snapshot (`{"kind": "label+property", "label": "CalendarDay", "properties": ["jdn"]}`),
    and may have functions `indexes()` and `constraints()` that give more, called here (after `initialise()`: what
    they give may follow the models, as the vector indexes of `pangloss-vectors` do).

    Each entry is stamped with the app, whose migrations make it, unless it names an installed app of its own
    (`"app"`): an index the project's models call for belongs in the project's migrations, not the library's"""
    import importlib

    from pangloss_core import settings as core_settings

    from pangloss_models.exceptions import PanglossMigrationError

    settings = core_settings.__dict__.get("SETTINGS")
    apps = list(getattr(settings, "INSTALLED_APPS", None) or [])
    indexes: list[dict[str, Any]] = []
    constraints: list[dict[str, Any]] = []
    for app in apps:
        try:
            module = importlib.import_module(f"{app}.structure")
        except ModuleNotFoundError as error:
            if error.name in (app, f"{app}.structure"):
                continue
            raise
        for listed, function, found in (
            ("INDEXES", "indexes", indexes),
            ("CONSTRAINTS", "constraints", constraints),
        ):
            entries = list(getattr(module, listed, []))
            made = getattr(module, function, None)
            if callable(made):
                entries += list(made())
            for entry in entries:
                own = entry.get("app")
                if own is not None and own not in apps:
                    raise PanglossMigrationError(
                        f"{app}.structure gives an entry for the app {own!r}, which is not installed: {entry!r}"
                    )
                found.append({"app": app, **entry})
    return indexes, constraints
