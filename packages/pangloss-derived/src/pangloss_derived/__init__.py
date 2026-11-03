"""Derived relations: rules that make new facts from what documents say, kept up to date in the background. See
docs/derived.md.

Installed as an app (`"pangloss_derived"` in `INSTALLED_APPS`, before the apps whose `derived.py` declare rules). When
the models are initialised it imports `<app>/derived.py` of each installed app, and checks the rules; a write of a
document that a rule can be triggered by leaves it pending for the worker (a background task of the server, or
`pangloss derive worker`).
"""

import importlib
import logging
from typing import Any

from pangloss_models import hooks
from pangloss_models.model_registry import ModelRegistry
from pangloss_models.search import Var

from pangloss_derived.declare import (
    Constraint,
    Derived,
    DerivedMeta,
    Rule,
    RuleType,
    between,
    distinct,
    gt,
    gte,
    lt,
    lte,
    rule,
    same,
    same_document,
)
from pangloss_derived.registry import DerivedRegistry, PanglossDerivedError

__all__ = [
    "Constraint",
    "Derived",
    "DerivedMeta",
    "PanglossDerivedError",
    "Rule",
    "RuleType",
    "Var",
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
    `Derived` classes, check the rules, and work out what can trigger them"""
    from pangloss_derived.check import initialise_classes, initialise_rules

    from pangloss_derived.access import bind_reads

    import_derived_modules()
    initialise_classes()
    initialise_rules()
    bind_reads()
    DerivedRegistry.initialised = True
    if DerivedRegistry.checked:
        logger.info(
            "Derived: %s rules of %s classes; triggered by %s",
            len(DerivedRegistry.checked),
            len(DerivedRegistry.concrete_classes()),
            ", ".join(sorted(DerivedRegistry.triggers)) or "nothing",
        )


def pending_work_of(model: type) -> list[str]:
    """(`hooks.pending_work`) a write of a head node of a class that can trigger a rule leaves work for the worker"""
    return ["derive"] if model.__name__ in DerivedRegistry.triggers else []


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


def _install() -> None:
    # (nothing of the database is imported here: a client of the SDK imports this package with the models)
    if initialise in ModelRegistry.after_finalise:
        return
    from pangloss_models import typestubs

    from pangloss_derived import search

    search.install()
    ModelRegistry.after_finalise.append(initialise)
    typestubs.stub_classes.append(lambda: DerivedRegistry.classes.values())
    ModelRegistry.on_reset.append(DerivedRegistry.reset)
    hooks.pending_work.append(pending_work_of)
    hooks.after_write.append(wake_worker)
    hooks.head_view_extras.append(derived_section)


_install()
