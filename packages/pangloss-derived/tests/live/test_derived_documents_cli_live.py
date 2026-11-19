"""`pangloss derive` and the rules that derive documents: explained, counted and built. (The commands run
their own event loop: this test is not async)"""

import json
from types import SimpleNamespace
from typing import no_type_check

from pangloss_testing.live import run_command, run_connected
from typer.testing import CliRunner

from pangloss_derived.cli import cli

from test_derived_documents_live import child_of, models, people


@no_type_check
def test_the_commands_take_a_rule_of_documents(clear_database, command_backend):
    m = models()
    project = SimpleNamespace(require_database=lambda: None, import_models=lambda: None)
    explained = CliRunner().invoke(cli, ["explain", "siblings"], obj=project)
    assert explained.exit_code == 0, explained.output
    assert "siblings  (DerivedFactoid, hash " in explained.output
    assert "Two children of one parent are siblings" in explained.output
    assert (
        "derives documents: one for each justification, resting (sources) on documents of DerivedFactoid, "
        "Factoid; at most 2000 from one written document" in explained.output
    )
    assert "read by the rules: kin" in explained.output
    assert "each pair of a and b once" in explained.output
    assert "DerivedFactoid{label: 'Siblings'" in explained.output
    assert "not through: Negative" in explained.output
    blocked = CliRunner().invoke(cli, ["explain", "said_kin"], obj=project)
    assert "not inside a: DerivedFactoid, Hearsay" in blocked.output

    async def make():
        n = await people(m, "ABCP")
        await m.Factoid.Create(
            label="One", statements=[child_of(n[c], n.P) for c in "ABC"]
        ).save()

    run_connected(command_backend, make)
    counted = run_command(cli, command_backend, "dry-run", "siblings")
    assert counted.exit_code == 0, counted.output
    assert "3 documents, from 3 ChildOf nodes" in counted.output
    status = run_command(cli, command_backend, "status")
    assert status.exit_code == 0, status.output
    assert (
        "derived documents: 0 to write or look at again, 0 to delete" in status.output
    )
    assert "siblings: not built" in status.output
    built = run_command(cli, command_backend, "rebuild", "siblings")
    assert built.exit_code == 0, built.output
    assert built.output.startswith("siblings: {")
    counts = json.loads(built.output.split("siblings: ", 1)[1].splitlines()[0])
    assert counts["seeds"] == 3 and counts["new"] == 3
    # (its documents are written before the command ends, with what the pending work gave the other rules)
    assert counts["documents"]["made"] >= 3
    status = run_command(cli, command_backend, "status")
    assert "siblings: ready, 3 documents" in status.output
    assert (
        "derived documents: 0 to write or look at again, 0 to delete" in status.output
    )

    async def read():
        listed = (await m.DerivedFactoid.list(page_size=50)).results
        return sorted(d.derived_by for d in listed)

    assert run_connected(command_backend, read).count("siblings") == 3
    # (built again: nothing is written)
    again = run_command(cli, command_backend, "rebuild", "siblings")
    counts = json.loads(again.output.split("siblings: ", 1)[1].splitlines()[0])
    assert counts["new"] == 0 and counts["removed"] == 0
    assert set(counts["documents"]) <= {"same"}
