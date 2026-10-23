"""What deleting the originals of a squashed migration would do to history.

A version written when the database was part way through a squashed range cannot be upgraded once
the originals are gone (the squash is one step: see `upgrade.migrations_after`). A version written at
the *end* of the range can (the squash stands for the last original). Deleting is not refused:
history is best effort, but the person is told how many versions are inside."""

from collections.abc import Iterable
from typing import Any

from pangloss_models.migrations.files import Migration

from pangloss_history import config
from pangloss_history.store import HistoryStore, SqliteStore


def versions_inside(store: HistoryStore, squashed: Iterable[Migration]) -> list[tuple[Migration, int]]:
    """For each squashed migration, the versions recorded part way through what it replaces"""
    positions = store.position_counts()
    found = []
    for migration in squashed:
        inside = {name for app, name in migration.replaces[:-1] if app == migration.app}
        count = sum(n for position, n in positions if position.get(migration.app) in inside)
        if count:
            found.append((migration, count))
    return found


def warnings_for(settings: Any, squashed: Iterable[Migration]) -> list[str]:
    """Sentences to warn with (none if there is no history store yet, or nothing is inside)"""
    path = config.db_path(settings)
    if not path.exists():
        return []
    return [
        f"{count} recorded version{'s were' if count != 1 else ' was'} written part way through "
        f"what {migration.name} replaces, and could not be upgraded or restored once the originals are gone"
        for migration, count in versions_inside(SqliteStore(path), squashed)
    ]
