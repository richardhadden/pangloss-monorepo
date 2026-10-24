"""Which migrations the database has had, as `{app: last migration}`, for each record.

Without it, an old version could not be upgraded to the models of today. It is read from the
migration files of the installed apps: the server checks as it starts that the database is what
they say (`MIGRATION_CHECK`), so the last migration of each app is where the database is. It is
read once, and again if the server is told that a migration was run (`forget`)."""

from typing import Any

from pangloss_models.migrations.files import graph_of

_cache: dict[str, str] | None = None


def compute(apps: list[str]) -> dict[str, str]:
    latest: dict[str, Any] = {}
    for migration in graph_of(apps).migrations.values():
        if (
            migration.app not in latest
            or migration.number > latest[migration.app].number
        ):
            latest[migration.app] = migration
    return {app: migration.name for app, migration in sorted(latest.items())}


def schema_position(apps: list[str]) -> dict[str, str]:
    global _cache
    if _cache is None:
        _cache = compute(apps)
    return _cache


def forget() -> None:
    global _cache
    _cache = None
