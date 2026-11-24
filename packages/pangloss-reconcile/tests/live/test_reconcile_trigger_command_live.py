"""`pangloss reconcile suggest` and `pangloss reconcile status`, run against the database (step 10.5e). (A command
runs its own event loop: these tests are not async, and what they write first is written in a loop of its own.) What
`mark_stored` and `status` do is claimed in `test_reconcile_trigger_live.py`; here, that the commands do it and say
so, and how a class that can hold no stand-in is refused"""

import re
from typing import no_type_check

import pytest
from pangloss_models.migrations.files import EMPTY_SNAPSHOT, load
from pangloss_reconcile.cli import cli
from pangloss_testing.live import run_command, run_connected
from pangloss_testing.parts import drop_vector_indexes
from test_reconcile_trigger_live import letter, mention, tokens, trigger_models
from test_reconcile_worker_live import marks


@pytest.fixture
def made(db_driver, clear_database, command_backend):
    """The models of the trigger's tests, a letter and a postcard that each name someone not identified, nothing
    marked: the models and the heads' ids"""
    from pangloss_core import backend as backends
    from pangloss_testing.live import apply_changes

    drop_vector_indexes(db_driver)
    m = trigger_models()

    async def make():
        for name in ["0001_initial", "0002_models", "0003_suggested"]:
            migration = load("pangloss_reconcile", name)
            await apply_changes(
                backends.current().database(), EMPTY_SNAPSHOT, list(migration.changes)
            )
        plain = await letter(m, mention(), mention())
        card = await letter(m, mention(), kind="Postcard")
        return str(plain.id), str(card.id)

    heads = run_connected(command_backend, make)
    yield m, heads
    drop_vector_indexes(db_driver)


@no_type_check
def test_the_command_suggest_marks_what_holds_a_stand_in_and_says_how_many(
    db_driver, made, command_backend
):
    m, (plain, card) = made
    assert marks(db_driver) == []

    narrowed = run_command(cli, command_backend, "suggest", "--class", "Postcard")
    assert narrowed.exit_code == 0, narrowed.output
    assert narrowed.output.splitlines() == [
        "1 document left for the worker; 0 were already waiting (1 mention in them)"
    ]
    assert marks(db_driver) == [card]
    first = tokens(db_driver)

    every = run_command(cli, command_backend, "suggest")
    assert every.exit_code == 0, every.output
    assert every.output.splitlines() == [
        "1 document left for the worker; 1 was already waiting (3 mentions in them)"
    ]
    assert marks(db_driver) == sorted([plain, card])
    assert tokens(db_driver)[card] == first[card]

    again = run_command(cli, command_backend, "suggest", "--again")
    assert again.exit_code == 0, again.output
    assert again.output.splitlines() == [
        "0 documents left for the worker; 2 were already waiting (3 mentions in them)",
        "0 mentions tried before to be asked again",
    ]


@no_type_check
def test_the_command_suggest_refuses_a_class_that_can_hold_no_stand_in(
    db_driver, made, command_backend
):
    result = run_command(cli, command_backend, "suggest", "--class", "PlaceNote")

    assert result.exit_code == 1
    assert "Refused: 'PlaceNote': no class that can hold a stand-in" in result.output
    assert "The classes that can: Diary, Letter, Postcard" in result.output
    assert marks(db_driver) == []


@no_type_check
def test_the_command_status_says_what_waits_and_what_was_done(
    db_driver, made, command_backend
):
    quiet = run_command(cli, command_backend, "status")
    assert quiet.exit_code == 0, quiet.output
    assert quiet.output.splitlines() == [
        "waiting: 0 documents (0 claimed)",
        "waiting for the vectors: 0",
        "worker: none running",
        "mentions tried and left: 0",
        "suggestions not yet confirmed: 0",
    ]

    run_command(cli, command_backend, "suggest")
    busy = run_command(cli, command_backend, "status")
    assert busy.exit_code == 0, busy.output
    lines = busy.output.splitlines()
    assert lines[0] == "waiting: 2 documents (0 claimed)"
    assert re.fullmatch(r"oldest: \d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00", lines[1])
    assert lines[2:] == [
        # (the letters' own marks of the vectors are there: no vectors worker ran)
        "waiting for the vectors: 2",
        "worker: none running",
        "mentions tried and left: 0",
        "suggestions not yet confirmed: 0",
    ]
