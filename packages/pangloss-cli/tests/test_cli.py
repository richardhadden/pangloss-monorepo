import sys
from pathlib import Path

from pangloss_cli.main import build_app
from pangloss_cli.project import find_settings, settings_option_from
from typer.testing import CliRunner

from cli_support import SETTINGS, write

runner = CliRunner()


class Result:
    """What a command printed (to stdout and stderr) and how it ended"""

    def __init__(self, result):
        self.exit_code = result.exit_code
        self.output = result.output + result.stderr


def invoke(*args: str, argv: list[str] | None = None, environment=None):
    app = build_app(argv=argv or [], environment=environment or {})
    return Result(runner.invoke(app, list(args)))


# ---------------------------------------------------------------------------
# Finding the settings
# ---------------------------------------------------------------------------


def test_settings_option_from_argv():
    assert settings_option_from(["--settings", "a.b"]) == "a.b"
    assert settings_option_from(["users", "--settings=a.b", "list"]) == "a.b"
    assert settings_option_from(["users", "list"]) is None
    assert settings_option_from(["--settings"]) is None


def test_settings_are_found_in_order(project: Path):
    sub = project / "a" / "b"
    sub.mkdir(parents=True)

    # pyproject.toml, from this directory or one below it
    for directory in (project, sub):
        location = find_settings([], {}, directory)
        assert location is not None
        assert location.module == "myproject.settings"
        assert location.root == project

    # the environment is before it, and the command line before that
    location = find_settings([], {"PANGLOSS_SETTINGS": "env.settings"}, project)
    assert location.module == "env.settings"
    location = find_settings(
        ["--settings", "arg.settings"], {"PANGLOSS_SETTINGS": "env.settings"}, project
    )
    assert location.module == "arg.settings"


def test_no_settings(tmp_path: Path):
    assert find_settings([], {}, tmp_path) is None


# ---------------------------------------------------------------------------
# Running without, and with, a project
# ---------------------------------------------------------------------------


def test_help_works_without_a_project(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = invoke("--help")
    assert result.exit_code == 0
    assert "setup-database" in result.output
    assert "users" in result.output


def test_commands_that_need_a_project_say_so(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for args in (["setup-database"], ["users", "list"]):
        result = invoke(*args)
        assert result.exit_code == 1
        assert "No settings found" in result.output


def test_a_settings_module_that_cannot_be_loaded(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = invoke("setup-database", argv=["--settings", "no_such.settings"])
    assert result.exit_code == 1
    assert "no_such.settings" in result.output


def test_a_settings_module_that_makes_no_settings(project: Path):
    write(project, "myproject/nothing.py", "x = 1")
    result = invoke("setup-database", argv=["--settings", "myproject.nothing"])
    assert result.exit_code == 1
    assert "did not create the settings" in result.output


def test_database_without_a_setup_module(project: Path):
    write(project, "plainapp/__init__.py", "")
    write(
        project,
        "myproject/settings_plain.py",
        SETTINGS.format(apps=[], database="plainapp"),
    )
    result = invoke("setup-database", argv=["--settings", "myproject.settings_plain"])
    assert result.exit_code == 1
    assert "Cannot load the database 'plainapp'" in result.output


def test_setup_database_calls_the_backend(project: Path):
    result = invoke("setup-database")
    assert result.exit_code == 0, result.output
    assert "created: something" in result.output

    fakedb = sys.modules["fakedb.setup"]
    assert fakedb.CALLS == ["create_database", "connect", "setup_database", "disconnect"]
    # The models of the installed apps were imported
    assert sys.modules["fakeapp.models"].IMPORTED


# ---------------------------------------------------------------------------
# Commands from installed apps
# ---------------------------------------------------------------------------


def test_app_commands_are_added_under_the_name_of_the_app_cli(project: Path):
    result = invoke("fake", "hello", "--name", "pangloss")
    assert result.exit_code == 0, result.output
    assert "hello pangloss" in result.output
    assert "fake" in invoke("--help").output


def test_a_broken_app_is_reported_but_does_not_stop_the_rest(project: Path, capsys):
    result = invoke("fake", "hello")
    assert result.exit_code == 0
    warnings = capsys.readouterr().err
    assert "no commands from 'brokenapp'" in warnings
    assert "broken on purpose" in warnings
    # (an app with no cli.py is fine, and says nothing)
    assert "plainapp" not in warnings


def test_an_app_cannot_replace_a_core_command(project: Path, capsys):
    write(
        project,
        "fakeapp/cli.py",
        """
        import typer
        cli = typer.Typer(name="users")
        """,
    )
    invoke("--help")
    warnings = capsys.readouterr().err
    assert "no commands from 'fakeapp'" in warnings
    assert "'users' is already a command" in warnings


def test_an_app_cli_must_be_a_typer(project: Path, capsys):
    write(project, "fakeapp/cli.py", "cli = 1")
    invoke("--help")
    assert "has no Typer object named 'cli'" in capsys.readouterr().err


def test_the_name_defaults_to_the_app_without_its_prefix(project: Path):
    write(project, "fakeapp/__init__.py", "")
    write(project, "pangloss_thing/__init__.py", "")
    write(
        project,
        "pangloss_thing/cli.py",
        """
        import typer
        cli = typer.Typer()

        @cli.command()
        def go():
            typer.echo("going")
        """,
    )
    write(
        project,
        "myproject/settings_thing.py",
        SETTINGS.format(apps=["pangloss_thing"], database="fakedb"),
    )
    result = invoke(
        "thing", "go", argv=["--settings", "myproject.settings_thing"]
    )
    assert result.exit_code == 0, result.output
    assert "going" in result.output
    del sys.modules["pangloss_thing.cli"], sys.modules["pangloss_thing"]
