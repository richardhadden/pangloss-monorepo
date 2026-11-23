"""`pangloss reconcile worker --once`, run against the database (step 10.5d). (The command runs its own event loop:
these tests are not async, and what they write first is written in a loop of its own.) What the worker does is
claimed in `test_reconcile_worker_live.py`; here, that the command does it, that history records the version it
writes as the toolchain's, and how it refuses a toolchain that is a person"""

from typing import no_type_check

import pytest
from pangloss_models.migrations.files import EMPTY_SNAPSHOT, load
from pangloss_reconcile.cli import cli
from pangloss_testing.live import run_command, run_connected
from pangloss_testing.parts import drop_vector_indexes
from test_reconcile_worker_live import (
    NAME,
    TOOLCHAIN,
    factoid,
    history,  # noqa: F401
    marks,
    settle,
    suggestions,
    unknown,
    world,
    worker_models,
)


@pytest.fixture
def made(db_driver, clear_database, command_backend):
    """The world of the worker's tests, and a factoid that names Jon Smyth, not identified, marked, its vectors done:
    the models and the factoid's id"""
    from pangloss_core import backend as backends
    from pangloss_testing.live import apply_changes

    drop_vector_indexes(db_driver)
    m = worker_models()

    async def make():
        for name in ["0001_initial", "0002_models", "0003_suggested"]:
            migration = load("pangloss_reconcile", name)
            await apply_changes(
                backends.current().database(), EMPTY_SNAPSHOT, list(migration.changes)
            )
        ids = await world(m, db_driver)
        written = await factoid(m, ids, unknown())
        await settle(db_driver)
        return written.id

    head = run_connected(command_backend, make)
    yield m, head
    drop_vector_indexes(db_driver)


@no_type_check
def test_the_command_worker_once_writes_the_suggestions_as_the_toolchain_and_history_records_it(
    db_driver,
    made,
    command_backend,
    history,  # noqa: F811
):
    from pangloss_history import listener

    m, head = made
    store = history()
    assert marks(db_driver) == [str(head)]

    result = run_command(cli, command_backend, "worker", "--once")

    assert result.exit_code == 0, result.output
    assert result.output.splitlines() == ["1 document done"]
    (suggested,) = suggestions(db_driver, head)
    assert (suggested["p"]["text"], suggested["p"]["identified_by"]) == (
        NAME,
        TOOLCHAIN,
    )
    assert marks(db_driver) == []
    listener.get_recorder().drain()
    assert [(r.version, r.who) for r in store.versions(head)] == [(2, TOOLCHAIN)]

    again = run_command(cli, command_backend, "worker", "--once")
    assert again.output.splitlines() == ["0 documents done"]


@no_type_check
def test_the_command_worker_refuses_a_toolchain_that_is_a_person(
    db_driver, made, command_backend
):
    from pangloss_users import service

    m, head = made

    async def person():
        await service.create_user(TOOLCHAIN, "reconcile@example.com", "a long password")

    run_connected(command_backend, person)

    result = run_command(cli, command_backend, "worker", "--once")

    assert result.exit_code == 1
    assert (
        "Refused: RECONCILE_TOOLCHAIN names 'pangloss-reconcile', who is a person"
        in result.output
    )
    assert suggestions(db_driver, head) == []
    assert marks(db_driver) == [str(head)]
