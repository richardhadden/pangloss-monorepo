"""Similarity for Pangloss (an app: `INSTALLED_APPS += ["pangloss_vectors"]`): a vector for each document and entity,
made by the parts that other packages register (`parts.py`), stored on nodes of their own, kept current (`worker.py`)
and searched. implementation_docs/similarity-build-plan.md"""

import importlib
from typing import Any

from pangloss_models import ModelRegistry, hooks

lazy from pangloss_vectors.parts import (
    DEFAULT_PROFILE,
    Changed,
    Item,
    Part,
    Refreshed,
    Unknown,
    Vector,
    VectorRow,
    Writer,
    part,
    profile,
    profiles,
    register_part,
    signature_of,
    unknown_vectors,
    unregister_part,
)
lazy from pangloss_vectors.unknowns import unknowns_of
lazy from pangloss_vectors.meta import VectorsMeta
lazy from pangloss_vectors.search import Hit, Nearest, NotAGroup, nearest
lazy from pangloss_vectors.rebuild import Rebuilt, VectorsRebuildBusy
lazy from pangloss_vectors.status import Status
lazy from pangloss_vectors.worker import idle, run_pending

# (`parts()` is not among them: `parts` is the module, which would replace the lazy name once imported. It is
# `pangloss_vectors.parts.parts()`; nor are `rebuild()` and `status()`, for the same reason:
# `pangloss_vectors.rebuild.rebuild()`, `pangloss_vectors.status.status()`)
__all__ = [
    "DEFAULT_PROFILE",
    "Changed",
    "Hit",
    "Item",
    "Nearest",
    "NotAGroup",
    "Part",
    "Rebuilt",
    "Refreshed",
    "Status",
    "Unknown",
    "Vector",
    "VectorRow",
    "VectorsMeta",
    "VectorsRebuildBusy",
    "Writer",
    "idle",
    "nearest",
    "part",
    "profile",
    "profiles",
    "register_part",
    "requires",
    "run_pending",
    "signature_of",
    "unknown_vectors",
    "unknowns_of",
    "unregister_part",
]

# (its vectors are stored and searched with Cypher of its own, through the backend's vector index: checked at
# start-up, see `pangloss_core.storage.check_requirements`)
requires = {"cypher", "vector_index"}

APP = "pangloss_vectors"

# The kind of work a write leaves for the worker (`pangloss_cypher.pending`)
KIND = "vectors"


def import_installed_apps(settings: Any = None) -> list[str]:
    """Import each installed app, so that every part's package has registered its part. Gives `INSTALLED_APPS`"""
    from pangloss_core import settings as core_settings

    if settings is None:
        settings = core_settings.__dict__.get("SETTINGS")
    apps = list(getattr(settings, "INSTALLED_APPS", None) or [])
    for app in apps:
        try:
            importlib.import_module(app)
        except ModuleNotFoundError as error:
            if error.name == app:
                continue  # (not this check's to report: `check_requirements` and the loading of models say so)
            raise
    return apps


def check_profiles() -> None:
    """(`ModelRegistry.after_finalise`) a project with this app installed has its `VECTORS_PROFILES`, and its
    `VECTORS_EXCLUDE` and `VECTORS_INCLUDE` (`meta.check_settings`), checked at `initialise()`, so that a profile naming
    a part that is not registered, a bad weight, or a class that is not one of documents or entities is refused
    there. Each installed app is imported first (`import_installed_apps`)"""
    from pangloss_core import settings as core_settings

    settings: Any = core_settings.__dict__.get("SETTINGS")
    if APP not in list(getattr(settings, "INSTALLED_APPS", None) or []):
        return
    import_installed_apps(settings)
    from pangloss_vectors.meta import check_settings
    from pangloss_vectors.parts import profiles

    profiles(settings)
    check_settings(settings)


def installed(settings: Any = None) -> bool:
    """Whether this app is among the settings' `INSTALLED_APPS`. (The hooks below are installed whenever the package is
    imported, as in a test process that runs the tests of other packages too: they do nothing unless it is)"""
    from pangloss_core import settings as core_settings

    if settings is None:
        settings = core_settings.__dict__.get("SETTINGS")
    return APP in (getattr(settings, "INSTALLED_APPS", None) or ())


def pending_work_of(model: type) -> list[str]:
    """(`hooks.pending_work`) a write of a head (a document or an entity) leaves it for the worker; nothing unless the
    app is installed. A head of a class that has no vectors (`meta.included`) too: a write of it can change what the
    items it names are joined to, and so their vectors (the store leaves out its own row)"""
    from pangloss_models import Document, Entity

    if (
        installed()
        and isinstance(model, type)
        and issubclass(model, (Document, Entity))
    ):
        return [KIND]
    return []


def wake_worker(event: hooks.WriteEvent) -> None:
    """(`hooks.after_write`) wake the worker of this process, if it runs"""
    from pangloss_vectors.worker import worker

    worker.listen(event)


def wake_for_marked(model: type) -> None:
    """(`hooks.work_marked`) wake the worker of this process, if it runs"""
    from pangloss_vectors.worker import worker

    worker.marked(model)


def _install() -> None:
    # (nothing of the database is imported here: a client of the SDK imports this package with the models)
    from pangloss_vectors import class_part

    if check_profiles not in ModelRegistry.after_finalise:
        ModelRegistry.after_finalise.append(check_profiles)
    # (the work a write leaves: implementation_docs/vectors.md, "Keeping vectors current". An update's mark keeps what
    # its tree named, which a part cannot find afterwards: the entities a reference was dropped from, and the
    # documents nested in it, which the update replaces by new ones)
    if pending_work_of not in hooks.pending_work:
        hooks.pending_work.append(pending_work_of)
        hooks.pending_keeps_before.add(KIND)
        hooks.after_write.append(wake_worker)
        hooks.work_marked.append(wake_for_marked)
    # (the class part, which needs only the models: implementation_docs/similarity-build-plan.md, step 2.3)
    class_part.install()


_install()
