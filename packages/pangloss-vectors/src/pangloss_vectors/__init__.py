"""Similarity for Pangloss (an app: `INSTALLED_APPS += ["pangloss_vectors"]`): a vector for each document and entity,
made by the parts that other packages register (`parts.py`), stored on nodes of their own, kept current and searched.
implementation_docs/similarity-build-plan.md"""

import importlib
from typing import Any

from pangloss_models import ModelRegistry

lazy from pangloss_vectors.parts import (
    DEFAULT_PROFILE,
    Changed,
    Item,
    Part,
    Refreshed,
    Vector,
    VectorRow,
    Writer,
    part,
    profile,
    profiles,
    register_part,
    signature_of,
    unregister_part,
)
lazy from pangloss_vectors.meta import VectorsMeta
lazy from pangloss_vectors.search import Hit, Nearest, NotAGroup, nearest

# (`parts()` is not among them: `parts` is the module, which would replace the lazy name once imported. It is
# `pangloss_vectors.parts.parts()`)
__all__ = [
    "DEFAULT_PROFILE",
    "Changed",
    "Hit",
    "Item",
    "Nearest",
    "NotAGroup",
    "Part",
    "Refreshed",
    "Vector",
    "VectorRow",
    "VectorsMeta",
    "Writer",
    "nearest",
    "part",
    "profile",
    "profiles",
    "register_part",
    "requires",
    "signature_of",
    "unregister_part",
]

# (its vectors are stored and searched with Cypher of its own, through the backend's vector index: checked at
# start-up, see `pangloss_core.storage.check_requirements`)
requires = {"cypher", "vector_index"}

APP = "pangloss_vectors"


def check_profiles() -> None:
    """(`ModelRegistry.after_finalise`) a project with this app installed has its `VECTORS_PROFILES` checked at
    `initialise()`, so that a profile naming a part that is not registered, or a bad weight, is refused there. Each
    installed app is imported first, so that every part's package has registered its part"""
    from pangloss_core import settings as core_settings

    settings: Any = core_settings.__dict__.get("SETTINGS")
    apps = list(getattr(settings, "INSTALLED_APPS", None) or [])
    if APP not in apps:
        return
    for app in apps:
        try:
            importlib.import_module(app)
        except ModuleNotFoundError as error:
            if error.name == app:
                continue  # (not this check's to report: `check_requirements` and the loading of models say so)
            raise
    from pangloss_vectors.parts import profiles

    profiles(settings)


def _install() -> None:
    # (nothing of the database is imported here: a client of the SDK imports this package with the models)
    from pangloss_vectors import class_part

    if check_profiles not in ModelRegistry.after_finalise:
        ModelRegistry.after_finalise.append(check_profiles)
    # (the class part, which needs only the models: implementation_docs/similarity-build-plan.md, step 2.3)
    class_part.install()


_install()
