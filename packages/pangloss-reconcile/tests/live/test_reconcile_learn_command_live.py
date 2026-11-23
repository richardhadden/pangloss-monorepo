"""`pangloss reconcile learn`, run against the database (step 11.5). (The command runs its own event loop: these tests
are not async, and the examples are written in a loop of their own. What a fit does is claimed in
`test_reconcile_learn_live.py`; here, what the command prints and how it refuses)"""

import json
from typing import no_type_check

import pangloss_core.settings as core_settings
import pytest
from pangloss_models.migrations.files import EMPTY_SNAPSHOT, load
from pangloss_reconcile import decisions
from pangloss_reconcile.cli import cli
from pangloss_testing.live import run, run_command, run_connected
from test_reconcile_learn_live import LEARN_FROM, START, TODAY, made


@pytest.fixture
def learnable(db_driver, clear_database, monkeypatch):
    from pangloss_vectors import import_installed_apps

    import_installed_apps()
    monkeypatch.setattr(core_settings.SETTINGS, "RECONCILE_LEARN_FROM", LEARN_FROM)
    run(db_driver, TODAY)
    return db_driver


@pytest.fixture(autouse=True)
def structure(learnable, command_backend):
    """The package's migrations applied, as `pangloss migrate` would (as the other live files do)"""
    from pangloss_core import backend as backends
    from pangloss_testing.live import apply_changes

    async def migrate():
        for name in ["0001_initial", "0002_models"]:
            migration = load("pangloss_reconcile", name)
            await apply_changes(
                backends.current().database(), EMPTY_SNAPSHOT, list(migration.changes)
            )

    run_connected(command_backend, migrate)


@no_type_check
def keep(backend, made_decisions) -> None:
    """The decisions written as examples through the listener's writer, with today's signatures"""
    import datetime

    from pangloss_core import backend as backends
    from pangloss_vectors import store

    async def write_them():
        record = decisions.today(await store.states())
        database = backends.current().database()

        @database.write_transaction
        async def write(tx):
            for n, decision in enumerate(made_decisions):
                await decisions.write_example(
                    tx,
                    decision["stand_in"],
                    START + datetime.timedelta(seconds=n),
                    {**record, "rows": json.dumps(decision["rows"])},
                    decision["taken"],
                )

        await write()

    run_connected(backend, write_them)


def fits_of(db_driver) -> list[dict]:
    return run(
        db_driver,
        "MATCH (m:PGReconcileModel) RETURN m.id AS id, m.in_use AS in_use ORDER BY m.at",
    )


@no_type_check
def test_the_command_learn_prints_what_it_did_line_by_line(learnable, command_backend):
    keep(command_backend, made(60))

    dry = run_command(cli, command_backend, "learn", "--dry-run")
    assert dry.exit_code == 0, dry.output
    lines = dry.output.splitlines()
    assert lines[:3] == [
        "0 records of what was offered would be removed (a dry run)",
        "60 examples read",
        "60 decisions to learn from",
    ]
    assert lines[-1] == "Nothing written (a dry run): the fit would be put in use"
    assert fits_of(learnable) == []

    result = run_command(cli, command_backend, "learn")
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    (fit,) = fits_of(learnable)
    assert lines[0] == "0 records of what was offered removed"
    assert any(
        line.startswith("The ranking model: fitted on 600 rows;") for line in lines
    )
    assert any(
        line.startswith('The "none of these" model: fitted on') for line in lines
    )
    assert lines[-1] == f"Written: the fit {fit['id']}, in use"

    again = run_command(cli, command_backend, "learn")
    assert again.exit_code == 0, again.output
    assert again.output.splitlines()[-1].endswith(f"({fit['id']}): nothing written")


@no_type_check
def test_the_command_learn_use_puts_a_fit_in_use_or_none_and_says_why_it_refuses(
    learnable, command_backend
):
    keep(command_backend, made(60))
    assert run_command(cli, command_backend, "learn").exit_code == 0
    (fit,) = fits_of(learnable)

    none = run_command(cli, command_backend, "learn", "--use", "none")
    assert none.exit_code == 0, none.output
    assert none.output.splitlines() == ["No fit is in use"]
    assert fits_of(learnable) == [{"id": fit["id"], "in_use": False}]

    used = run_command(cli, command_backend, "learn", "--use", fit["id"])
    assert used.exit_code == 0, used.output
    assert used.output.splitlines() == [
        f"The fit {fit['id']} is in use (of 60 decisions)"
    ]
    assert fits_of(learnable) == [{"id": fit["id"], "in_use": True}]

    refused = run_command(cli, command_backend, "learn", "--use", "nope")
    assert refused.exit_code == 1
    assert refused.output.splitlines() == ["Refused: There is no fit nope"]

    both = run_command(cli, command_backend, "learn", "--use", "none", "--dry-run")
    assert both.exit_code != 0
    assert fits_of(learnable) == [{"id": fit["id"], "in_use": True}]
