import sys
import textwrap

import pytest
from pangloss_core.settings import ClientSettings
from pangloss_models.model_registry import ModelRegistry
from pangloss_sdk import client as sdk_client


@pytest.fixture(autouse=True)
def clean_state():
    ModelRegistry._reset()
    sdk_client.install(None)
    yield
    sdk_client.install(None)
    ModelRegistry._reset()


@pytest.fixture(autouse=True)
def client_settings():
    """Settings for the models; `connect()` makes its own"""
    ClientSettings(INSTALLED_APPS=[], DATABASE_MODULE="pangloss_sdk.databases.api")


@pytest.fixture
def an_app(tmp_path, monkeypatch):
    package = tmp_path / "an_sdk_test_app"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "models.py").write_text(
        textwrap.dedent(
            """
            from pangloss_models.model_bases.entity import Entity

            class Person(Entity):
                pass
            """
        )
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    yield "an_sdk_test_app"
    sys.modules.pop("an_sdk_test_app.models", None)
    sys.modules.pop("an_sdk_test_app", None)


@pytest.fixture(autouse=True)
def credentials_in_a_temporary_file(tmp_path, monkeypatch):
    """A kept login goes to a file in the test's directory, never to the real keyring or home"""
    monkeypatch.setenv("PANGLOSS_CREDENTIALS_FILE", str(tmp_path / "credentials.json"))
    monkeypatch.setenv("PANGLOSS_NO_KEYRING", "1")
