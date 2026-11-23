"""`pangloss reconcile sweep`, run against the database (step 11.4). (The command runs its own event loop: this test
is not async; what the sweep removes is claimed in `test_reconcile_decisions_live.py`)"""

import datetime
from typing import no_type_check

from pangloss_reconcile.cli import cli
from pangloss_testing.live import run, run_command

LONG_AGO = datetime.datetime(2000, 1, 1, tzinfo=datetime.UTC)


@no_type_check
def test_the_command_sweep_removes_what_can_make_no_example_and_says_how_many_went(
    clear_database, db_driver, command_backend
):
    run(
        db_driver,
        "CREATE (:PGReconcileShown {stand_in: 'a', user: 'ann', at: $at}), "
        "(:PGReconcileShown {stand_in: 'b', user: 'ann', at: $at})",
        at=LONG_AGO,
    )

    result = run_command(cli, command_backend, "sweep")
    assert result.exit_code == 0, result.output
    assert result.output.splitlines() == ["2 records of what was offered removed"]
    assert run(db_driver, "MATCH (s:PGReconcileShown) RETURN count(s) AS n") == [
        {"n": 0}
    ]

    again = run_command(cli, command_backend, "sweep")
    assert again.exit_code == 0, again.output
    assert again.output.splitlines() == ["0 records of what was offered removed"]
