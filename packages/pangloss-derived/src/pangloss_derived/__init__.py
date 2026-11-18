"""Derived relations: rules that make new facts from what documents say, kept up to date in the background. See
implementation_docs/derived.md.

Installed as an app (`"pangloss_derived"` in `INSTALLED_APPS`, before the apps whose `derived.py` declare rules). When
the models are initialised it imports `<app>/derived.py` of each installed app, and checks the rules; a write of a
document that a rule can be triggered by leaves it pending for the worker (a background task of the server, or
`pangloss derive worker`).
"""

import importlib
import logging
from typing import Any

from pangloss_models import ModelRegistry, Var, hooks

from pangloss_derived.declare import (
    Constraint,
    DerivedEdge,
    DerivedFrom,
    DerivedMeta,
    Object,
    PerJustification,
    Rule,
    RuleType,
    Subject,
    SymmetricLabel,
    between,
    distinct,
    gt,
    gte,
    lt,
    lte,
    rule,
    same,
    same_document,
    unordered,
)
from pangloss_derived.derives import DerivesEdge
from pangloss_derived.documents import (
    DerivedDocument,
    DerivedDocumentMeta,
    PanglossDerivedDocumentError,
    writing_derived,
)
from pangloss_derived.registry import DerivedRegistry, PanglossDerivedError
from pangloss_derived.templates import Via

__all__ = [
    "Constraint",
    "DerivedDocument",
    "DerivedDocumentMeta",
    "DerivedEdge",
    "DerivedFrom",
    "DerivedMeta",
    "DerivesEdge",
    "Object",
    "PanglossDerivedDocumentError",
    "PanglossDerivedError",
    "PerJustification",
    "Rule",
    "RuleType",
    "Subject",
    "SymmetricLabel",
    "Var",
    "Via",
    "between",
    "distinct",
    "gt",
    "graph",
    "gte",
    "initialise",
    "lt",
    "lte",
    "requires",
    "rule",
    "same",
    "same_document",
    "unordered",
    "writing_derived",
]

# (the rules run their own Cypher: checked at start-up, see `pangloss_core.storage.check_requirements`)
requires = {"cypher"}

logger = logging.getLogger("pangloss.derived")


def import_derived_modules() -> None:
    """Import `<app>.derived` of each installed app that has one (which declares its classes and rules)"""
    from pangloss_core import settings as core_settings

    settings = core_settings.__dict__.get("SETTINGS")
    for app in getattr(settings, "INSTALLED_APPS", []) or []:
        try:
            importlib.import_module(f"{app}.derived")
        except ModuleNotFoundError as error:
            if error.name not in (app, f"{app}.derived"):
                raise


def initialise() -> None:
    """(Called at the end of the models' `initialise()`) load the `derived.py` of the apps, make the classes of the
    `DerivedEdge` classes, check the rules, and work out what can trigger them"""
    from pangloss_derived.check import initialise_classes, initialise_rules

    from pangloss_derived.access import bind_reads

    from pangloss_derived import documents
    from pangloss_derived.derives import make_declared_edges
    from pangloss_derived.templates import make_templates

    # (first: a `derived.py` may write a rule of its own for an edge that a document class declares)
    make_declared_edges()
    import_derived_modules()
    initialise_classes()
    # (what a rule that derives a document writes with: `Sibling.Template`, `DerivedFactoid.Derive`)
    documents.check_classes()
    make_templates()
    initialise_rules()
    bind_reads()
    DerivedRegistry.initialised = True
    if DerivedRegistry.checked or DerivedRegistry.documents:
        logger.info(
            "Derived: %s rules of %s classes, %s rules of documents; triggered by %s",
            len(DerivedRegistry.checked),
            len(DerivedRegistry.concrete_classes()),
            len(DerivedRegistry.documents),
            ", ".join(sorted(DerivedRegistry.triggers)) or "nothing",
        )


def pending_work_of(model: type) -> list[str]:
    """(`hooks.pending_work`) a write of a head node of a class that can trigger a rule leaves work for the worker.
    Not the worker's own write of a derived document that no rule reads"""
    from pangloss_derived import documents

    if model.__name__ not in DerivedRegistry.triggers:
        return []
    writing = documents.writing()
    if (
        writing is not None
        and writing.rule in DerivedRegistry.documents
        and documents.is_derived_document(model)
        and not DerivedRegistry.readers.get(writing.rule)
    ):
        return []
    return ["derive"]


def uncounted_classes() -> list[str]:
    """(`hooks.references_not_counted`) what a derived document names is not "referred to" by it: an entity that only
    derived documents name is not used, and can be deleted (the worker removes what was derived about it)"""
    from pangloss_derived import documents

    return documents.concrete_class_names()


async def resolve_citation(type_name: str, id: Any, tx: Any) -> Any:
    """(`hooks.resolve_citation`) a citation of a derived document is one of what it rests on"""
    from pangloss_derived.citing import resolve

    return await resolve(type_name, id, tx)


async def mark_citations(tx: Any, op: str, model: type, id: Any) -> None:
    """(`hooks.in_write`) the citations made through a derived document follow what the worker does to it"""
    from pangloss_derived.citing import mark_citations as mark

    await mark(tx, op, model, id)


def wake_for_marked(model: type) -> None:
    """(`hooks.work_marked`) wake the worker of this process, if it runs"""
    from pangloss_derived.worker import worker

    worker.marked(model)


def graph(type_name: str, plain_only: bool = False) -> Any:
    """The facts derived by the rules of a type of rule, as edges between their two ends (see `read.graph`). As the
    models' functions are: a coroutine, or, with the blocking SDK (`connect(sync=True)`), the edges"""
    from pangloss_derived.access import graph as read_graph

    return read_graph(type_name, plain_only)


def wake_worker(event: hooks.WriteEvent) -> None:
    """(`hooks.after_write`) wake the worker of this process, if it runs"""
    from pangloss_derived.worker import worker

    worker.listen(event)


async def derived_section(owner: type, view: object) -> dict:
    """(`hooks.head_view_extras`) `_derived` of a head node's view"""
    from pangloss_derived.read import derived_section as section

    return await section(owner, view)


def translatable_models() -> list[hooks.TranslatableModel]:
    """(`hooks.translatable_models`) the derived classes, for the interface's translation files: their names, the
    names of their fields (the two ends of a symmetric class as one, by their `SymmetricLabel`), and the
    `reverse_name` of their object"""
    found = []
    for name, model in DerivedRegistry.concrete_classes().items():
        label = model._symmetric_label
        fields: dict[str, tuple[str, str]] = {}
        for field in model._fields:
            if label and field in model._ends:
                fields.setdefault(label, ("", ""))
            else:
                fields[field] = ("", "")
        found.append(
            hooks.TranslatableModel(
                name=name,
                module=model.__module__,
                kind="DerivedEdge",
                description=(model.__doc__ or "").strip(),
                fields=fields,
                incoming=(model._reverse_name,) if model._reverse_name else (),
            )
        )
    return found


def has_shortcut_classes() -> bool:
    """(`hooks.edges_of_no_field`) a class asks for shortcut edges, so there are edges between entities that are of
    no field"""
    from pangloss_derived import shortcuts

    return bool(shortcuts.classes())


def _install() -> None:
    # (nothing of the database is imported here: a client of the SDK imports this package with the models)
    if initialise in ModelRegistry.after_finalise:
        return
    from pangloss_models import typestubs

    from pangloss_derived import documents, search

    search.install()
    ModelRegistry.after_finalise.append(initialise)
    typestubs.stub_classes.append(lambda: DerivedRegistry.classes.values())
    ModelRegistry.on_reset.append(DerivedRegistry.reset)
    ModelRegistry.on_reset.append(documents.forget_cited_basis)
    hooks.pending_work.append(pending_work_of)
    hooks.not_written_by_people.append(documents.not_written_by_people)
    hooks.in_write.append(documents.refuse_other_writers)
    hooks.in_write.append(mark_citations)
    hooks.new_head_properties.append(documents.head_properties)
    hooks.updated_head_properties.append(documents.head_properties)
    from pangloss_derived.convert import KEPT

    hooks.kept_head_properties.extend(
        n for n in KEPT if n not in hooks.kept_head_properties
    )
    hooks.references_not_counted.append(uncounted_classes)
    hooks.edges_of_no_field.append(has_shortcut_classes)
    hooks.resolve_citation.append(resolve_citation)
    hooks.work_marked.append(wake_for_marked)
    hooks.after_write.append(wake_worker)
    hooks.head_view_extras.append(derived_section)
    hooks.translatable_models.append(translatable_models)


_install()
