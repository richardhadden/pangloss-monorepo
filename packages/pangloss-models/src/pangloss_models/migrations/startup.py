"""Whether the database and the models agree with the migrations, for a server to check as it
starts (`docs/migrations.md` 3.3).

A project that has migrations promises that its database is what they say and its models are what
they come to. Three things break that: migrations not applied yet, a migration that was changed
or lost after it was applied, and models that have changed since the migrations were written. A
project with no migrations makes no promise, and is not checked.
"""

import importlib
from types import ModuleType
from typing import Any

from pangloss_models.migrations.files import graph_of
from pangloss_models.migrations.history import pending, problems
from pangloss_models.migrations.snapshot import build_snapshot, data_view


def migration_backend_of(database_module: str) -> ModuleType | None:
    """The `migration_backend` of a database package, if it has one"""
    try:
        return importlib.import_module(f"{database_module}.migration_backend")
    except ModuleNotFoundError as error:
        if error.name == f"{database_module}.migration_backend":
            return None
        raise


def structure_of(backend: ModuleType) -> dict[str, Any] | None:
    """The indexes and constraints the database needs (for the snapshot), if it says"""
    return backend.structure() if hasattr(backend, "structure") else None


async def migration_problems(
    apps: list[str], backend: ModuleType, snapshot: dict[str, Any] | None = None
) -> list[str]:
    """What is wrong, as sentences (none: all is well, or the project has no migrations).
    `snapshot` is of the initialised models; it is made if it is not given."""
    if not graph_of(apps).migrations:
        return []

    applied = await backend.applied()
    graph = graph_of(apps, applied)
    applied = graph.reconcile(applied)
    found = problems(graph, applied)

    todo = pending(graph, applied)
    if todo:
        names = ", ".join(str(m) for m in todo[:5]) + (", ..." if len(todo) > 5 else "")
        found.append(f"{len(todo)} migrations have not been applied ({names}): run `pangloss migrate`")

    if snapshot is None:
        snapshot = build_snapshot(structure_of(backend))
    if not todo and graph.state() != data_view(snapshot):
        found.append(
            "The models are not what the migrations come to: run `pangloss makemigrations`"
        )
    return found
