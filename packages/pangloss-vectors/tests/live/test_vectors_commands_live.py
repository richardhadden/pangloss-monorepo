"""`pangloss vectors rebuild | status | weights`, run against the database (step 2.5). (The commands run their own
event loop: these tests are not async)"""

from typing import no_type_check

import pytest
from pangloss_testing.live import run_command, run_connected
from pangloss_vectors.class_part import PART
from pangloss_vectors.cli import cli
from vectors_live_support import EVENTS, declare_events, saved_events


@pytest.fixture
def class_part(clear_database, parts_of_the_test):
    """The class part alone (the default profile is it, at its weight)"""
    parts_of_the_test(PART)
    return PART


@no_type_check
def test_the_commands_rebuild_say_the_status_and_the_weights(
    class_part, command_backend
):
    m = declare_events()
    run_connected(command_backend, lambda: saved_events(m, **EVENTS))

    told = run_command(cli, command_backend, "status")
    assert told.exit_code == 0, told.output
    lines = told.output.splitlines()
    assert lines[0].startswith(
        f"part class: never built (dimension {PART.dimension()}, signature "
    )
    assert "  rebuild due: it has never been built" in lines
    assert lines[-1] == "A rebuild is due: pangloss vectors rebuild"

    result = run_command(cli, command_backend, "rebuild")
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert lines[0].startswith("part class: generation ")
    assert ", 7 vectors in " in lines[0]
    assert lines[1].startswith("profile default: generation ")
    assert lines[-1].startswith("done in ")

    told = run_command(cli, command_backend, "status")
    assert told.exit_code == 0, told.output
    assert "rebuild due" not in told.output
    assert (
        f", 7 vectors, 0 stale (dimension {PART.dimension()}, signature " in told.output
    )
    assert "profile default (class 0.1): generation " in told.output

    weights = run_command(cli, command_backend, "weights")
    assert weights.exit_code == 0, weights.output
    assert weights.output.splitlines() == [
        "profile default: class 0.1",
        f"part class: dimension {PART.dimension()}, signature {PART.signature()}, "
        "refreshed after a write",
    ]

    unknown = run_command(cli, command_backend, "rebuild", "--part", "nope")
    assert unknown.exit_code == 2
    assert "no part named 'nope'" in unknown.output
