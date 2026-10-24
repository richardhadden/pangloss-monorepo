"""The checks of the JavaScript side, run with the rest of the tests: its type-check (with the
package's own empty models), its tests (vitest) and the layers of `interface-core`. They need Node
and the packages installed in `js/` (`npm install` there); without them they are skipped, and say so."""

import shutil
import subprocess
from pathlib import Path

import pangloss_interface
import pytest

JS = Path(pangloss_interface.__file__).parent / "js"

pytestmark = [
    pytest.mark.skipif(shutil.which("npm") is None, reason="npm is not installed"),
    pytest.mark.skipif(
        not (JS / "node_modules").is_dir(),
        reason=f"the packages are not installed: npm install in {JS}",
    ),
    # (one worker: the scripts share the workspace's caches)
    pytest.mark.xdist_group("javascript"),
]


def run(*script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["npm", "run", *script], cwd=JS, capture_output=True, text=True, timeout=300
    )


@pytest.mark.parametrize("script", ["typecheck", "test", "check:layers"])
def test_the_javascript_passes(script):
    result = run(script)
    assert result.returncode == 0, (result.stdout + result.stderr)[-3000:]
