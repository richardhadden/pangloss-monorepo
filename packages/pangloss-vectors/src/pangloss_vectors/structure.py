"""The indexes of the nodes of vectors (not models): read by the database package (`pangloss_models.indexes.
installed_app_structure`), which puts them in the snapshot that migrations are made from.

- `INDEXES`: the plain indexes, made by this package's migrations (`0001_initial.py`, `0002_profile_vector_type.py`);
- `indexes()`: the vector indexes, which follow the project's models and settings (a vector index for each profile,
  and for each profile and group, `meta.groups`; their names and labels carry the dimension, `store.Layout`). They
  belong in the **project's** migrations, not this package's, which cannot know the project: each entry names its app
  (implementation_docs/similarity-build-plan.md, step 2.2).
"""

from typing import Any

from pangloss_models import Document, Entity, ModelRegistry
from pangloss_models.exceptions import PanglossInitialisationError

INDEXES = [
    # (the vectors of an item: read, replaced and deleted by its id; a generation, found and dropped by its number)
    {"kind": "label+property", "label": "PGVector", "properties": ["of"]},
    {"kind": "label+property", "label": "PGVector", "properties": ["generation"]},
    # (the state of a part: its generation in use, when it was built, its signature)
    {"kind": "label+property", "label": "PGVectorState", "properties": ["part"]},
    # (the vectors of each profile, as those of the parts; and the state of each profile)
    {"kind": "label+property", "label": "PGProfileVector", "properties": ["of"]},
    {
        "kind": "label+property",
        "label": "PGProfileVector",
        "properties": ["generation"],
    },
    {"kind": "label+property", "label": "PGVectorProfile", "properties": ["profile"]},
    # (the vectors of a profile by the class of their item: the exact scan of classes no group covers, `search`.
    # Made by `migrations/0002_profile_vector_type.py`)
    {"kind": "label+property", "label": "PGProfileVector", "properties": ["type"]},
]

CONSTRAINTS: list[dict] = []


def _settings() -> Any:
    from pangloss_core import settings as core_settings

    return core_settings.__dict__.get("SETTINGS")


def project_app(settings: Any = None) -> str | None:
    """The app whose migrations make the vector indexes of the profiles: the setting `VECTORS_MIGRATIONS_APP` if it is
    given (an installed app), or else the installed app that holds the most classes of documents and entities whose
    module is not in a `pangloss_*` package (of two that hold as many, the later in `INSTALLED_APPS`). None if no app
    holds any"""
    from pangloss_models.migrations.planner import app_of_module

    settings = settings if settings is not None else _settings()
    apps = list(getattr(settings, "INSTALLED_APPS", None) or [])
    named = getattr(settings, "VECTORS_MIGRATIONS_APP", None)
    if named is not None:
        if named not in apps:
            raise PanglossInitialisationError(
                f"VECTORS_MIGRATIONS_APP is {named!r}, which is not among INSTALLED_APPS: it names the app whose "
                "migrations make the vector indexes"
            )
        return named
    counts = {app: 0 for app in apps}
    for model in ModelRegistry._model_dict.values():
        if not issubclass(model, (Document, Entity)):
            continue
        module = model.__module__
        if module.split(".")[0].startswith("pangloss_"):
            continue
        app = app_of_module(module, apps)
        if app is not None:
            counts[app] += 1
    best: str | None = None
    for app in apps:
        if counts[app] and (best is None or counts[app] >= counts[best]):
            best = app
    return best


def vector_entry(name: str, label: str, dimension: int, app: str) -> dict[str, Any]:
    """The entry of a vector index of the vectors of a profile (cosine; not quantized, which on Neo4j costs recall)"""
    return {
        "kind": "vector",
        "name": name,
        "label": label,
        "properties": ["vector"],
        "dimension": dimension,
        "metric": "cos",
        "quantization": False,
        "app": app,
    }


def indexes() -> list[dict[str, Any]]:
    """(called after `initialise()`) The vector index of each profile, and of each profile and group, with the app
    whose migrations make them: the project's (`project_app`) for a profile's own, and for a group's, the app the
    class's module is in (the project's, if it is in none). None if no part is registered, nor for a profile that
    weighs nothing, nor if no app holds the project's models"""
    from pangloss_models.migrations.planner import app_of_module

    from pangloss_vectors import meta, parts, store

    if not parts.parts():
        return []
    settings = _settings()
    app = project_app(settings)
    if app is None:
        return []
    apps = list(getattr(settings, "INSTALLED_APPS", None) or [])
    groups = meta.groups()
    entries: list[dict[str, Any]] = []
    for profile_name, weights in parts.profiles(settings).items():
        if not weights:
            continue
        lay = store.layout(profile_name, weights)
        entries.append(vector_entry(lay.index_name, lay.label, lay.dimension, app))
        for group in groups:
            module = ModelRegistry._model_dict[group].__module__
            entries.append(
                vector_entry(
                    lay.group_index_name(group),
                    lay.group_label(group),
                    lay.dimension,
                    app_of_module(module, apps) or app,
                )
            )
    names = [entry["name"] for entry in entries]
    twice = sorted({name for name in names if names.count(name) > 1})
    if twice:
        raise PanglossInitialisationError(
            f"Two vector indexes would be named {', '.join(twice)}: the names of the groups (classes with "
            "VectorsMeta(searchable=True)) are lower-cased in them, so two classes cannot differ only in case"
        )
    return entries
