"""Stop servers that an interrupted e2e run left behind: `uv run python e2e/cleanup.py` (lists them; `--kill` stops them).

Only a process that is listening, and whose working directory is in a pytest temporary directory (`pytest-of-USER`), is
named: whatever else you run is not touched.
"""

import os
import signal
import subprocess
import sys


def listening() -> list[int]:
    done = subprocess.run(
        ["lsof", "-nP", "-iTCP", "-sTCP:LISTEN", "-t"],
        capture_output=True,
        text=True,
        check=False,
    )
    return sorted({int(pid) for pid in done.stdout.split()})


def directory_of(pid: int) -> str:
    done = subprocess.run(
        ["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
        capture_output=True,
        text=True,
        check=False,
    )
    return next(
        (line[1:] for line in done.stdout.splitlines() if line.startswith("n")), ""
    )


def main() -> None:
    kill = "--kill" in sys.argv[1:]
    found = [
        (pid, cwd) for pid in listening() if "pytest-of-" in (cwd := directory_of(pid))
    ]
    for pid, cwd in found:
        print(pid, cwd)
        if kill:
            os.kill(pid, signal.SIGTERM)
    print(f"{len(found)} found" + (", stopped" if kill and found else ""))


if __name__ == "__main__":
    main()
