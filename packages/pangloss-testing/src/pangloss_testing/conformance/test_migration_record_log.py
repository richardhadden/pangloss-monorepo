"""The record of migrations is one implementation for the Cypher backends (`pangloss_cypher.migrations.record`), and
says what it does to the logger of the backend in use (`pangloss.memgraph.migrations`), as `docs/logging.md` has it"""

import logging

import pytest
from pangloss_models import PanglossMigrationError
from pangloss_testing.under_test import migration_backend as backend
from pangloss_testing.under_test.database import current

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_the_lock_is_logged_by_the_backend_in_use(
    db_driver, clear_database, caplog
):
    name = f"pangloss.{current().dialect.name}.migrations"
    assert name != "pangloss.cypher.migrations"
    await backend.ensure_ready()
    with caplog.at_level(logging.INFO, logger="pangloss"):
        await backend.lock("someone")
        try:
            with pytest.raises(PanglossMigrationError, match="--unlock"):
                await backend.lock("another")
        finally:
            await backend.unlock()
    said = [
        (r.name, r.levelname, r.getMessage())
        for r in caplog.records
        if "lock" in r.getMessage()
    ]
    assert said == [
        (name, "INFO", "Migration lock taken by 'someone'"),
        (name, "ERROR", "Migration lock is held by another migrate (or a stopped one)"),
        (name, "INFO", "Migration lock released"),
    ]


async def test_the_record_is_the_kit_s_for_every_backend():
    from pangloss_cypher.migrations import record

    for name in (
        "applied",
        "apply",
        "dry_run",
        "has_data",
        "lock",
        "unapply",
        "unlock",
    ):
        assert getattr(backend, name) is getattr(record, name), name
