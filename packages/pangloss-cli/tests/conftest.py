import sys

import pytest
from pangloss_core import settings as core_settings

from cli_support import (
    FAKE_DB_EXPOSED,
    FAKE_DB_SETUP,
    PACKAGES,
    SETTINGS,
    write,
)


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A project in a temporary directory, with a fake database, an app with
    commands and models, an app that cannot be imported, and an app with no cli"""
    write(tmp_path, "fakedb/__init__.py", "")
    write(tmp_path, "fakedb/setup.py", FAKE_DB_SETUP)
    write(tmp_path, "fakedb/exposed_functions.py", FAKE_DB_EXPOSED)

    write(tmp_path, "fakeapp/__init__.py", "")
    write(
        tmp_path,
        "fakeapp/cli.py",
        """
        import typer

        cli = typer.Typer(name="fake", help="Fake commands")

        @cli.command()
        def hello(name: str = "world"):
            typer.echo(f"hello {name}")
        """,
    )
    write(
        tmp_path,
        "fakeapp/models.py",
        """
        IMPORTED = True
        """,
    )
    write(tmp_path, "brokenapp/__init__.py", "")
    write(tmp_path, "brokenapp/cli.py", "raise RuntimeError('broken on purpose')")
    write(tmp_path, "plainapp/__init__.py", "")

    write(tmp_path, "myproject/__init__.py", "")
    write(
        tmp_path,
        "myproject/settings.py",
        SETTINGS.format(
            apps=["fakeapp", "brokenapp", "plainapp"], database="fakedb"
        ),
    )
    write(
        tmp_path,
        "pyproject.toml",
        """
        [tool.pangloss]
        settings = "myproject.settings"
        """,
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PANGLOSS_SETTINGS", raising=False)
    saved_path = list(sys.path)
    # (the settings are global, and other packages' tests set and use them: put back
    # whatever was there)
    saved_settings = core_settings.__dict__.get("SETTINGS")
    # (start with none, as a command line starts)
    core_settings.__dict__.pop("SETTINGS", None)
    yield tmp_path
    sys.path[:] = saved_path
    for name in list(sys.modules):
        if name.split(".")[0] in PACKAGES:
            del sys.modules[name]
    if saved_settings is None:
        core_settings.__dict__.pop("SETTINGS", None)
    else:
        core_settings.SETTINGS = saved_settings


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    """An empty directory to work in, as a command line would be run from. Whatever
    is imported from it, and the settings that are made, are forgotten afterwards."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PANGLOSS_SETTINGS", raising=False)
    saved_path = list(sys.path)
    saved_settings = core_settings.__dict__.get("SETTINGS")
    core_settings.__dict__.pop("SETTINGS", None)
    yield tmp_path
    sys.path[:] = saved_path
    root = str(tmp_path.resolve())
    for name, module in list(sys.modules.items()):
        file = getattr(module, "__file__", None)
        if file and str(file).startswith(root):
            del sys.modules[name]
    if saved_settings is None:
        core_settings.__dict__.pop("SETTINGS", None)
    else:
        core_settings.SETTINGS = saved_settings
