"""`pangloss derive shortcuts` and what `pangloss derive status` says of the shortcut edges, run against the database.
(The commands run their own event loop: these tests are not async)"""

from typing import no_type_check

from pangloss_testing.live import run, run_command, run_connected

from pangloss_derived.cli import cli
from pangloss_derived.worker import run_pending_derivations

from test_derived_shortcuts_live import (
    assert_one_beside_each,
    entities,
    member,
    models,
    says,
    stored,
    transfer,
)


@no_type_check
def test_the_command_says_how_many_there_are_and_writes_them_again(
    clear_database, db_driver, command_backend
):
    m = models(gave_to=False)

    async def make():
        n = await entities(m)
        await says(m, "F1", member(n["A"], n["G"]), member(n["B"], n["G"]))
        await says(m, "F2", member(n["C"], n["G"]), transfer(n["A"], n["B"]))
        await run_pending_derivations()

    run_connected(command_backend, make)
    assert len(stored(db_driver)) == 3

    result = run_command(cli, command_backend, "shortcuts")
    assert result.exit_code == 0, result.output
    assert result.output.strip() == "SameGroup: 3 shortcut edges of 3 derived edges"
    status = run_command(cli, command_backend, "status")
    assert "shortcut edges of SameGroup: 3 of 3" in status.output

    run(db_driver, "MATCH ()-[e:SameGroup]->() WHERE e.derived DELETE e")
    status = run_command(cli, command_backend, "status")
    assert (
        "shortcut edges of SameGroup: 0 of 3 (3 missing: run `pangloss derive shortcuts --rebuild`)"
        in status.output
    )
    result = run_command(cli, command_backend, "shortcuts", "--rebuild")
    assert result.exit_code == 0, result.output
    assert (
        result.output.strip()
        == 'SameGroup: 3 shortcut edges of 3 derived edges, {"written": 3}'
    )
    assert len(stored(db_driver)) == 3
    assert_one_beside_each(db_driver, classes=("SameGroup",))

    # (a project with no such class)
    models(same_group=False, gave_to=False)
    result = run_command(cli, command_backend, "shortcuts")
    assert result.exit_code == 0, result.output
    assert result.output.splitlines() == [
        "No class has shortcut=True",
        '(classes without shortcut): {"deleted": 3}',
    ]
    assert stored(db_driver) == []
