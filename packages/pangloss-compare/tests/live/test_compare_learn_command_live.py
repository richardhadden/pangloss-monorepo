"""`pangloss compare learn` and `pangloss compare status`, run against the database (step 6.6). (A command runs its
own event loop: these tests are not async, and the judgements are made in a loop of their own. What a fit does is
claimed in `test_compare_learn_live.py`; here, what the commands print and how they refuse)"""

from typing import no_type_check

import pangloss_core.settings as core_settings
import pytest
from pangloss_compare.cli import cli
from pangloss_models.migrations.files import EMPTY_SNAPSHOT, load
from pangloss_testing.live import run, run_command, run_connected

from test_compare_learn_live import LEARN_FROM, x_and_y


@pytest.fixture(autouse=True)
def structure(clear_database, command_backend, monkeypatch):
    """The package's structure applied, as `pangloss migrate` would; `COMPARE_LEARN_FROM` lowered"""
    from pangloss_core import backend as backends
    from pangloss_testing.live import apply_changes

    monkeypatch.setattr(core_settings.SETTINGS, "COMPARE_LEARN_FROM", LEARN_FROM)

    async def migrate():
        migration = load("pangloss_compare", "0002_models")
        await apply_changes(
            backends.current().database(), EMPTY_SNAPSHOT, list(migration.changes)
        )

    run_connected(command_backend, migrate)


@no_type_check
def judged(db_driver, backend) -> None:
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)

    async def make():
        await x_and_y(m, db_driver, 10, 10, "two_events", "agree", fresh=False)

    run_connected(backend, make)


def fits_of(db_driver) -> list[dict]:
    return run(
        db_driver,
        "MATCH (m:PGCompareModel) RETURN m.id AS id, m.in_use AS in_use ORDER BY m.at",
    )


@no_type_check
def test_the_command_learn_prints_what_it_did_line_by_line(db_driver, command_backend):
    judged(db_driver, command_backend)

    dry = run_command(cli, command_backend, "learn", "--dry-run")
    assert dry.exit_code == 0, dry.output
    lines = dry.output.splitlines()
    assert lines[:3] == [
        "20 judgements read",
        '20 judgements of "one event or two"',
        '0 judgements of "does this answer that"',
    ]
    assert lines[3].startswith(
        '"One event or two": fitted on 20 judgements; of 20 held out, called rightly in 20 by the fit, 0 by the '
        "hand-set score; used"
    )
    assert lines[4].startswith('"Does this answer that": not fitted (0 examples are too few')  # fmt: skip
    assert lines[-1] == 'Nothing written (a dry run): the fit would be put in use, for "one event or two"'  # fmt: skip
    assert fits_of(db_driver) == []

    result = run_command(cli, command_backend, "learn")
    assert result.exit_code == 0, result.output
    (fit,) = fits_of(db_driver)
    assert result.output.splitlines()[-1] == f'Written: the fit {fit["id"]}, in use for "one event or two"'  # fmt: skip


@no_type_check
def test_the_command_learn_use_puts_a_fit_in_use_or_none_and_says_why_it_refuses(
    db_driver, command_backend
):
    judged(db_driver, command_backend)
    assert run_command(cli, command_backend, "learn").exit_code == 0
    (fit,) = fits_of(db_driver)

    none = run_command(cli, command_backend, "learn", "--use", "none")
    assert none.exit_code == 0, none.output
    assert none.output.splitlines() == ["No fit is in use"]
    assert fits_of(db_driver) == [{"id": fit["id"], "in_use": False}]

    used = run_command(cli, command_backend, "learn", "--use", fit["id"])
    assert used.exit_code == 0, used.output
    assert used.output.splitlines() == [f'The fit {fit["id"]} is in use, for "one event or two"']  # fmt: skip
    assert fits_of(db_driver) == [{"id": fit["id"], "in_use": True}]

    refused = run_command(cli, command_backend, "learn", "--use", "nope")
    assert refused.exit_code == 1
    assert refused.output.splitlines() == ["Refused: There is no fit nope"]

    both = run_command(cli, command_backend, "learn", "--use", "none", "--dry-run")
    assert both.exit_code != 0
    assert fits_of(db_driver) == [{"id": fit["id"], "in_use": True}]


@no_type_check
def test_the_command_status_says_what_is_in_use_and_how_many_more_are_needed(
    db_driver, command_backend
):
    from pangloss_testing.similar_models import declare

    declare(compared=True)
    empty = run_command(cli, command_backend, "status")
    assert empty.exit_code == 0, empty.output
    assert empty.output.splitlines() == [
        "judgements: 0",
        f"COMPARE_LEARN_FROM: {LEARN_FROM} (judgements of one kind of pair, for a fitted model to be used): at "
        f"least {LEARN_FROM} more needed",
        "No fit is in use",
    ]

    judged(db_driver, command_backend)
    assert run_command(cli, command_backend, "learn").exit_code == 0
    (fit,) = fits_of(db_driver)
    found = run_command(cli, command_backend, "status")
    assert found.exit_code == 0, found.output
    lines = found.output.splitlines()
    assert lines[:2] == [
        "judgements: 20",
        f"COMPARE_LEARN_FROM: {LEARN_FROM} (judgements of one kind of pair, for a fitted model to be used)",
    ]
    assert lines[2].startswith(f"in use: the fit {fit['id']} of ")
    assert lines[2].endswith(', for "one event or two"')
    assert len(lines) == 3
