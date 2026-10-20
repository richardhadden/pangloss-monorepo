import ast
import importlib
import os
import tomllib
from pathlib import Path

import pytest
from pangloss_cli.main import build_app
from pangloss_cli.scaffold import add_to_installed_apps
from typer.testing import CliRunner

runner = CliRunner()


class Result:
    def __init__(self, result):
        self.exit_code = result.exit_code
        self.output = result.output + result.stderr


def invoke(*args: str) -> Result:
    app = build_app(argv=[], environment={})
    return Result(runner.invoke(app, list(args)))


def installed_apps(path: Path) -> list[str]:
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == (
            "INSTALLED_APPS"
        ):
            return ast.literal_eval(node.value)
    raise AssertionError("no INSTALLED_APPS")


# ---------------------------------------------------------------------------
# new-project
# ---------------------------------------------------------------------------


def test_new_project(workdir: Path):
    result = invoke("new-project", "my_site")
    assert result.exit_code == 0, result.output
    assert "Created project 'my_site'" in result.output

    assert (workdir / "my_site" / "__init__.py").is_file()
    assert (workdir / "my_site" / "settings.py").is_file()

    # pyproject.toml says where the settings are
    pyproject = tomllib.loads((workdir / "pyproject.toml").read_text())
    assert pyproject["tool"]["pangloss"]["settings"] == "my_site.settings"
    assert pyproject["project"]["name"] == "my-site"

    # The secret is in .env, not in the settings, and .env is not for version control
    env = (workdir / ".env").read_text()
    assert env.startswith("AUTHJWT_SECRET_KEY=")
    assert len(env.split("=", 1)[1].strip()) >= 32
    assert "AUTHJWT_SECRET_KEY=" not in (workdir / "my_site" / "settings.py").read_text()
    assert ".env" in (workdir / ".gitignore").read_text().splitlines()


def test_each_project_gets_its_own_secret(workdir: Path):
    one = workdir / "one"
    two = workdir / "two"
    one.mkdir()
    two.mkdir()
    secrets = []
    for directory in (one, two):
    
        os.chdir(directory)
        assert invoke("new-project", "shop").exit_code == 0
        secrets.append((directory / ".env").read_text())
    assert secrets[0] != secrets[1]


def test_a_new_project_can_be_loaded(workdir: Path):
    assert invoke("new-project", "my_site").exit_code == 0

    # (a new command line, in the project: its settings are found and loaded)
    app = build_app(argv=[], environment={})
    result = Result(runner.invoke(app, ["--help"]))
    assert result.exit_code == 0
    assert "memgraph" in result.output  # the command from the installed app
    assert "Cannot load" not in result.output

    settings = importlib.import_module("my_site.settings")
    assert settings.Settings().INSTALLED_APPS == ["pangloss_memgraph"]
    assert settings.Settings().PROJECT_NAME == "my_site"
    assert settings.Settings().BACKEND_CORS_ORIGINS == ["http://localhost:5173"]


def test_settings_are_read_from_the_project_directory(workdir: Path):
    """`.env` is next to pyproject.toml, wherever the command is run from"""
    assert invoke("new-project", "my_site").exit_code == 0
    sub = workdir / "some" / "where"
    sub.mkdir(parents=True)
    os.chdir(sub)

    app = build_app(argv=[], environment={})
    result = Result(runner.invoke(app, ["--help"]))
    assert "Cannot load" not in result.output
    assert Path.cwd() == sub  # (and the directory is as it was)
    from pangloss_core import settings as core_settings

    assert len(core_settings.SETTINGS.AUTHJWT_SECRET_KEY) >= 32


def test_new_project_adds_to_an_existing_pyproject_and_env(workdir: Path):
    (workdir / "pyproject.toml").write_text(
        '[project]\nname = "mine"\nversion = "1.0"\n'
    )
    (workdir / ".env").write_text("OTHER=1")
    (workdir / ".gitignore").write_text("*.pyc")

    assert invoke("new-project", "my_site").exit_code == 0

    pyproject = tomllib.loads((workdir / "pyproject.toml").read_text())
    assert pyproject["project"]["name"] == "mine"
    assert pyproject["tool"]["pangloss"]["settings"] == "my_site.settings"
    env = (workdir / ".env").read_text().splitlines()
    assert env[0] == "OTHER=1"
    assert env[1].startswith("AUTHJWT_SECRET_KEY=")
    assert (workdir / ".gitignore").read_text().splitlines() == ["*.pyc", ".env"]


def test_new_project_keeps_an_existing_secret_and_gitignore_entry(workdir: Path):
    (workdir / ".env").write_text("AUTHJWT_SECRET_KEY=mine\n")
    (workdir / ".gitignore").write_text(".env\n")
    assert invoke("new-project", "my_site").exit_code == 0
    assert (workdir / ".env").read_text() == "AUTHJWT_SECRET_KEY=mine\n"
    assert (workdir / ".gitignore").read_text() == ".env\n"


def test_new_project_refuses_what_it_should(workdir: Path):
    for name in ("my-site", "1site", "class", "has space", "json", "pangloss_core"):
        result = invoke("new-project", name)
        assert result.exit_code == 1, name
        assert "cannot be the name of a project" in result.output
    assert list(workdir.iterdir()) == []

    (workdir / "taken").mkdir()
    assert "already exists" in invoke("new-project", "taken").output

    # Nothing is written when it refuses: a second project does not overwrite the first
    assert invoke("new-project", "first").exit_code == 0
    before = (workdir / "first" / "settings.py").read_text()
    result = invoke("new-project", "second")
    assert result.exit_code == 1
    assert "already a Pangloss project" in result.output
    assert not (workdir / "second").exists()
    assert (workdir / "first" / "settings.py").read_text() == before


# ---------------------------------------------------------------------------
# new-app
# ---------------------------------------------------------------------------


def test_new_app(workdir: Path):
    assert invoke("new-project", "my_site").exit_code == 0

    result = invoke("new-app", "blog")
    assert result.exit_code == 0, result.output
    assert (workdir / "blog" / "__init__.py").is_file()
    models = (workdir / "blog" / "models.py").read_text()
    assert "blog" in models
    compile(models, "models.py", "exec")

    settings = workdir / "my_site" / "settings.py"
    assert installed_apps(settings) == ["pangloss_memgraph", "blog"]

    # The settings still load, and the app can be imported
    app = build_app(argv=[], environment={})
    assert runner.invoke(app, ["--help"]).exit_code == 0
    assert importlib.import_module("blog.models")

    # Another app is added after it
    assert invoke("new-app", "people").exit_code == 0
    assert installed_apps(settings) == ["pangloss_memgraph", "blog", "people"]


def test_new_app_from_a_subdirectory(workdir: Path):
    assert invoke("new-project", "my_site").exit_code == 0
    sub = workdir / "some" / "where"
    sub.mkdir(parents=True)

    os.chdir(sub)

    assert invoke("new-app", "blog").exit_code == 0
    # (made in the project, not the directory it was run from)
    assert (workdir / "blog" / "models.py").is_file()
    assert not (sub / "blog").exists()


def test_new_app_outside_a_project(workdir: Path):
    result = invoke("new-app", "blog")
    assert result.exit_code == 1
    assert "No settings found" in result.output
    assert list(workdir.iterdir()) == []


def test_new_app_refuses_what_it_should(workdir: Path):
    assert invoke("new-project", "my_site").exit_code == 0
    for name in ("my-app", "2fast", "def", "json", "my_site"):
        result = invoke("new-app", name)
        assert result.exit_code == 1, name
        assert "cannot be the name of an app" in result.output or (
            "already exists" in result.output
        )
    assert installed_apps(workdir / "my_site" / "settings.py") == ["pangloss_memgraph"]

    assert invoke("new-app", "blog").exit_code == 0
    assert "already exists" in invoke("new-app", "blog").output


def test_new_app_when_the_settings_cannot_be_edited(workdir: Path):
    assert invoke("new-project", "my_site").exit_code == 0
    settings = workdir / "my_site" / "settings.py"
    settings.write_text(
        settings.read_text().replace(
            '    INSTALLED_APPS: list[str] = [\n        "pangloss_memgraph",\n    ]',
            '    INSTALLED_APPS: list[str] = get_apps()',
        )
    )
    before = settings.read_text()

    result = invoke("new-app", "blog")
    assert result.exit_code == 0
    assert (workdir / "blog" / "models.py").is_file()
    assert 'Add "blog" to INSTALLED_APPS' in result.output
    assert settings.read_text() == before


# ---------------------------------------------------------------------------
# Editing INSTALLED_APPS
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ('INSTALLED_APPS = []', 'INSTALLED_APPS = ["blog"]'),
        ('INSTALLED_APPS = ["a"]', 'INSTALLED_APPS = ["a", "blog"]'),
        ("INSTALLED_APPS = ['a', 'b']", "INSTALLED_APPS = ['a', 'b', \"blog\"]"),
        (
            'INSTALLED_APPS: list[str] = ["a", "b",]',
            'INSTALLED_APPS: list[str] = ["a", "b", "blog",]',
        ),
        (
            'class S:\n    INSTALLED_APPS = [\n        "a",\n        "b",\n    ]\n',
            'class S:\n    INSTALLED_APPS = [\n        "a",\n        "b",\n        "blog",\n    ]\n',
        ),
        (
            'class S:\n    INSTALLED_APPS = [\n        "a",\n        "b"\n    ]\n',
            'class S:\n    INSTALLED_APPS = [\n        "a",\n        "b",\n        "blog"\n    ]\n',
        ),
        (
            'X = 1\nINSTALLED_APPS = [  # apps\n    "a",  # one\n]\nY = 2\n',
            'X = 1\nINSTALLED_APPS = [  # apps\n    "a",  # one\n    "blog",\n]\nY = 2\n',
        ),
        ('INSTALLED_APPS = ["é", "b"]', 'INSTALLED_APPS = ["é", "b", "blog"]'),
        (
            'INSTALLED_APPS = [\n    "a",\n    "b"  # last\n]\n',
            'INSTALLED_APPS = [\n    "a",\n    "b",  # last\n    "blog"\n]\n',
        ),
        (
            'INSTALLED_APPS = [\n    "a", "b"]\n',
            'INSTALLED_APPS = [\n    "a", "b", "blog"]\n',
        ),
    ],
)
def test_add_to_installed_apps(before: str, after: str):
    edited = add_to_installed_apps(before, "blog")
    assert edited is not None
    ast.parse(edited)
    assert edited == after


def test_add_to_installed_apps_exact_layouts():
    assert (
        add_to_installed_apps('class S:\n    INSTALLED_APPS = [\n        "a",\n    ]\n', "b")
        == 'class S:\n    INSTALLED_APPS = [\n        "a",\n        "b",\n    ]\n'
    )
    assert add_to_installed_apps('INSTALLED_APPS = ["a"]', "b") == (
        'INSTALLED_APPS = ["a", "b"]'
    )


def test_an_app_already_installed_is_left_alone():
    source = 'INSTALLED_APPS = ["blog"]\n'
    assert add_to_installed_apps(source, "blog") == source


@pytest.mark.parametrize(
    "source",
    [
        "INSTALLED_APPS = get_apps()",
        'INSTALLED_APPS = ["a"] + OTHERS',
        'INSTALLED_APPS = [APP, "a"]',
        "X = 1",
        'INSTALLED_APPS = ["a"]\nINSTALLED_APPS = ["b"]',
        "INSTALLED_APPS = [",
    ],
)
def test_installed_apps_that_cannot_be_edited(source: str):
    assert add_to_installed_apps(source, "blog") is None
