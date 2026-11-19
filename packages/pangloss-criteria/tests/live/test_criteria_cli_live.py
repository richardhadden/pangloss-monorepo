"""`pangloss criteria status | explain | rebuild | check`, run against the database. (The commands run their own event
loop: these tests are not async)"""

from typing import no_type_check

from criteria_court_support import Court, description_of
from pangloss_criteria.cli import cli
from pangloss_criteria.worker import Worker, run_pending
from pangloss_testing.live import run, run_command, run_connected

from test_criteria_commands_live import DOCTORS, models


@no_type_check
def a_court(command_backend, *criteria) -> tuple[Court, list]:
    """Maximilian's secretary Waldauf, and an activity for each of the criteria (a secretary of Maximilian for
    None), evaluated"""
    court = Court(*models())

    async def make():
        await court.office("Secretary")
        await court.person("Maximilian")
        await court.holds("Waldauf")
        made = [
            await court.described(label=f"Activity {n}", criteria=c)
            for n, c in enumerate(criteria)
        ]
        await run_pending()
        return made

    return court, run_connected(command_backend, make)


@no_type_check
def test_status_says_what_is_pending_and_how_many_of_each_kind(
    clear_database, command_backend
):
    a_court(command_backend, None, DOCTORS)

    result = run_command(cli, command_backend, "status")

    assert result.exit_code == 0, result.output
    assert result.output.splitlines() == [
        "pending: 0 heads (0 claimed)",
        "descriptions: 2",
        "  far: 0 (evaluated in full after every write of a class they depend on)",
        "  no anchor, evaluated root first: 1 (of them far: 0)",
        "  too broad: 0 (more candidates than are linked; the count is exact after `rebuild`)",
        "  broken: 0",
    ]


@no_type_check
def test_explain_says_what_a_description_is(clear_database, command_backend):
    court, (activity,) = a_court(command_backend, None)
    described = description_of(activity)

    result = run_command(cli, command_backend, "explain", str(described.id))

    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert lines[0] == f"{described.id}  (in {activity.id})"
    assert "  local, complete" in lines
    assert f"  anchor: {court.people['Maximilian'].id}, 1 hops" in lines
    assert "  evaluated after:" in lines
    assert any(line.startswith("  in full: from the anchor") for line in lines)
    assert any("MATCH" in line for line in lines)
    assert any(line.startswith("    parameters: ") for line in lines)

    unknown = run_command(
        cli, command_backend, "explain", "01a1c564-7def-70f0-bd21-410a35c82ab1"
    )
    assert unknown.exit_code == 2
    assert "No description" in unknown.output


@no_type_check
def test_rebuild_writes_what_changed_and_is_refused_beside_a_worker(
    clear_database, command_backend, db_driver
):
    court, (activity,) = a_court(command_backend, None)
    run_connected(command_backend, lambda: court.holds("Serntein"))
    run(db_driver, "MATCH (p:PGPending) DELETE p")

    result = run_command(cli, command_backend, "rebuild", "--type", "Person")

    assert result.exit_code == 0, result.output
    assert result.output.strip() == (
        '{"descriptions": 1, "evaluated": 1, "changed": 1, "broken": 0, "refused": 0, "anchored": 1, '
        '"root_first": 0}'
    )
    other = Worker()
    run_connected(command_backend, other.take_lease)
    refused = run_command(cli, command_backend, "rebuild")
    assert refused.exit_code == 1
    assert "Another criteria worker is working" in refused.output


@no_type_check
def test_check_exits_with_1_when_criteria_no_longer_hold(
    clear_database, command_backend, db_driver
):
    court, (activity, doctors) = a_court(command_backend, None, DOCTORS)

    fine = run_command(cli, command_backend, "check")
    assert fine.exit_code == 0, fine.output
    assert fine.output.strip() == "every description's criteria fit the models"

    run(
        db_driver,
        """
        MATCH (d:MatchesCriteria {id: $id})
        SET d.criteria = '{"type": "Person", "where": {"shoe_size": {"gt": 40}}}'
        """,
        id=str(description_of(doctors).id),
    )
    result = run_command(cli, command_backend, "check")
    assert result.exit_code == 1
    assert (
        f"{description_of(doctors).id} (in {doctors.id}): criteria: " in result.output
    )
    assert "shoe_size" in result.output
