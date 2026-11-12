"""The interface modules' own Vitest tests and type-checks, run where a project builds them (a module has no
node_modules of its own, so they cannot be run in the package). Calendar, history, review, typology and users have
theirs beside their browser tests; these are the rest."""

import subprocess

import pytest
from conftest import Stack, environment


@pytest.mark.parametrize(
    "module",
    ["pangloss_admin", "pangloss_dates", "pangloss_derived", "pangloss_interface", "pangloss_library", "pangloss_rdf", "pangloss_zotero"],
)
def test_the_module_tests_pass_in_the_built_project(stack: Stack, module: str):
    interface = stack.project / ".pangloss" / "interface"
    assert (interface / "modules" / module).is_dir(), f"{module} has no interface module in the built project"
    for command in (
        ["npx", "vitest", "run", "--root", f"modules/{module}"],
        ["npx", "tsc", "--noEmit", "-p", f"modules/{module}/tsconfig.json"],
    ):
        done = subprocess.run(
            command, cwd=interface, env=environment(), capture_output=True, text=True, timeout=300, check=False
        )
        assert done.returncode == 0, (done.stdout + done.stderr)[-3000:]
