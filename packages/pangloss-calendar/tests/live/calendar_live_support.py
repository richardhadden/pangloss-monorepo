"""Shared by the live tests of the calendar"""

from pangloss_core import backend
from pangloss_models.migrations.files import EMPTY_SNAPSHOT, load
from pangloss_testing.live import apply_changes, run


async def structure():
    """The migration of the package, applied (a second time it changes nothing)"""
    migration = load("pangloss_calendar", "0001_initial")
    await apply_changes(
        backend.current().Database.default, EMPTY_SNAPSHOT, list(migration.changes)
    )


def count(db_driver, label):
    return run(db_driver, f"MATCH (n:{label}) RETURN count(n) AS c")[0]["c"]
