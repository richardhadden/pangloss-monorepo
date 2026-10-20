import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from cli_support import SETTINGS, write
from pangloss_cli import server
from pangloss_cli.main import build_app
from typer.testing import CliRunner

runner = CliRunner()


class Result:
    def __init__(self, result):
        self.exit_code = result.exit_code
        self.output = result.output + result.stderr


def invoke(*args: str) -> Result:
    return Result(runner.invoke(build_app(argv=[], environment={}), list(args)))


@pytest.fixture
def uvicorn_run(monkeypatch):
    """Stand in for uvicorn.run, recording how it is called"""
    import uvicorn

    calls = []
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: calls.append((args, kwargs)))
    # (the command changes these; put them back afterwards)
    monkeypatch.setenv("PANGLOSS_SETTINGS", "before")
    monkeypatch.setenv("PYTHONPATH", "before")
    return calls


# ---------------------------------------------------------------------------
# What is passed to uvicorn
# ---------------------------------------------------------------------------


def test_run(project: Path, uvicorn_run):
    result = invoke("run")
    assert result.exit_code == 0, result.output

    [(args, kwargs)] = uvicorn_run
    assert args == ("pangloss_api.app:create_app",)
    assert kwargs["factory"] is True
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == 8000
    assert "reload" not in kwargs
    assert kwargs["app_dir"] == str(project.resolve())

    # The server finds the settings and the project's code from its environment
    assert os.environ["PANGLOSS_SETTINGS"] == "myproject.settings"
    assert os.environ["PYTHONPATH"].split(os.pathsep) == [
        str(project.resolve()),
        "before",
    ]


def test_run_host_and_port(project: Path, uvicorn_run):
    assert invoke("run", "--host", "0.0.0.0", "--port", "9000").exit_code == 0
    [(_, kwargs)] = uvicorn_run
    assert kwargs["host"] == "0.0.0.0"
    assert kwargs["port"] == 9000


def test_dev_reloads(project: Path, uvicorn_run):
    (project / ".venv").mkdir()

    assert invoke("dev").exit_code == 0
    [(args, kwargs)] = uvicorn_run
    assert args == ("pangloss_api.app:create_app",)
    assert kwargs["reload"] is True
    assert kwargs["reload_dirs"] == [str(project.resolve())]
    # settings in `.env` count, and an environment in the project does not
    assert set(kwargs["reload_includes"]) == {"*.py", ".env"}
    assert kwargs["reload_excludes"] == [str(project.resolve() / ".venv")]


def test_the_server_runs_from_the_project_directory(project: Path, uvicorn_run):
    sub = project / "some" / "where"
    sub.mkdir(parents=True)
    os.chdir(sub)

    assert invoke("run").exit_code == 0
    assert Path.cwd().resolve() == project.resolve()


def test_dev_watches_installed_apps_outside_the_project(
    project: Path, tmp_path_factory, monkeypatch, uvicorn_run
):
    elsewhere = tmp_path_factory.mktemp("elsewhere")
    write(elsewhere, "outsideapp/__init__.py", "")
    monkeypatch.syspath_prepend(str(elsewhere))
    write(
        project,
        "myproject/settings.py",
        SETTINGS.format(apps=["fakeapp", "outsideapp"], database="fakedb"),
    )

    assert invoke("dev").exit_code == 0
    [(_, kwargs)] = uvicorn_run
    assert kwargs["reload_dirs"] == [
        str(project.resolve()),
        str((elsewhere / "outsideapp").resolve()),
    ]
    sys.modules.pop("outsideapp", None)


def test_installed_packages_are_not_watched(project: Path, uvicorn_run):
    write(
        project,
        "myproject/settings.py",
        SETTINGS.format(apps=["pydantic"], database="fakedb"),
    )
    assert invoke("dev").exit_code == 0
    [(_, kwargs)] = uvicorn_run
    assert kwargs["reload_dirs"] == [str(project.resolve())]


# ---------------------------------------------------------------------------
# When it cannot start
# ---------------------------------------------------------------------------


def test_run_outside_a_project(tmp_path: Path, monkeypatch, uvicorn_run):
    monkeypatch.chdir(tmp_path)
    for command in ("run", "dev"):
        result = invoke(command)
        assert result.exit_code == 1
        assert "No settings found" in result.output
    assert uvicorn_run == []


def test_run_without_the_api_package(project: Path, monkeypatch, uvicorn_run):
    monkeypatch.setitem(sys.modules, "pangloss_api", None)
    result = invoke("run")
    assert result.exit_code == 1
    assert "pangloss-api" in result.output
    assert uvicorn_run == []


def test_run_without_uvicorn(project: Path, monkeypatch):
    monkeypatch.setitem(sys.modules, "uvicorn", None)
    result = invoke("dev")
    assert result.exit_code == 1
    assert "pangloss-api" in result.output


def test_installed_app_directories_ignores_missing_apps(project: Path):
    from pangloss_cli.project import load_project

    loaded = load_project(argv=[], environment={}, directory=project)
    assert loaded.settings is not None
    loaded.settings.INSTALLED_APPS = ["no_such_app_at_all", "fakeapp"]
    assert server.installed_app_directories(loaded, project.resolve()) == []


# ---------------------------------------------------------------------------
# Really starting the server
# ---------------------------------------------------------------------------


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def get_title(port: int) -> str | None:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/openapi.json", timeout=2
        ) as response:
            return json.load(response)["info"]["title"]
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        return None


def wait_for_title(port: int, expected: str, seconds: float = 30) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if get_title(port) == expected:
            return True
        time.sleep(0.25)
    return False


@pytest.fixture
def server_process(project: Path):
    """Start `pangloss <command>` in the project; stop it (and what it started) after"""
    started = []

    def start(command: str, port: int) -> subprocess.Popen:
        environment = {
            key: value
            for key, value in os.environ.items()
            if key not in ("PANGLOSS_SETTINGS", "PYTHONPATH")
        }
        process = subprocess.Popen(
            [sys.executable, "-m", "pangloss_cli.main", command, "--port", str(port)],
            cwd=project,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        started.append(process)
        return process

    yield start

    for process in started:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
        process.stdout.close()


def test_run_starts_the_api(project: Path, server_process):
    port = free_port()
    server_process("run", port)
    assert wait_for_title(port, "Test"), "the server did not start"

    # (the user endpoints are there)
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/users/me", method="GET"
    )
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(request, timeout=5)
    assert error.value.code == 401


def test_dev_restarts_when_the_settings_change(project: Path, server_process):
    port = free_port()
    server_process("dev", port)
    assert wait_for_title(port, "Test"), "the server did not start"

    settings = project / "myproject" / "settings.py"
    settings.write_text(settings.read_text().replace('"Test"', '"Changed"'))
    assert wait_for_title(port, "Changed"), "the server did not restart"
