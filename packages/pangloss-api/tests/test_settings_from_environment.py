"""The app finds the project's settings: those already made, or the module `PANGLOSS_SETTINGS` names"""

import sys
import textwrap

import pytest
from pangloss_api import app as app_module
from pangloss_core import settings as core_settings


@pytest.fixture
def no_settings(monkeypatch):
    saved = core_settings.__dict__.pop("SETTINGS", None)
    yield
    if saved is not None:
        core_settings.SETTINGS = saved
    else:
        core_settings.__dict__.pop("SETTINGS", None)


def test_settings_already_made_are_used(settings):
    assert app_module.ensure_settings() is settings


def test_without_settings_or_the_variable_it_says_what_to_do(no_settings, monkeypatch):
    monkeypatch.delenv("PANGLOSS_SETTINGS", raising=False)
    with pytest.raises(RuntimeError, match="PANGLOSS_SETTINGS"):
        app_module.ensure_settings()


def test_the_module_the_variable_names_is_imported(no_settings, monkeypatch, tmp_path):
    (tmp_path / "env_settings_ok.py").write_text(textwrap.dedent("""
        from pangloss_core.settings import BaseSettings, DatabaseSettings
        from pydantic import AnyHttpUrl

        class Settings(BaseSettings[DatabaseSettings]):
            PROJECT_NAME: str = "From the environment"
            BACKEND_CORS_ORIGINS: list = []
            INSTALLED_APPS: list[str] = []
            DATABASE_MODULE: str = "fake_api_db"
            DATABASE: DatabaseSettings = DatabaseSettings()
            AUTHJWT_SECRET_KEY: str = "a secret for the tests, of a decent length"
            ENTITY_BASE_URL: AnyHttpUrl = AnyHttpUrl("http://test.com/")

        Settings()
    """))
    (tmp_path / "env_settings_empty.py").write_text("X = 1\n")
    monkeypatch.syspath_prepend(str(tmp_path))

    monkeypatch.setenv("PANGLOSS_SETTINGS", "env_settings_ok")
    assert app_module.ensure_settings().PROJECT_NAME == "From the environment"

    core_settings.__dict__.pop("SETTINGS", None)
    monkeypatch.setenv("PANGLOSS_SETTINGS", "env_settings_empty")
    with pytest.raises(RuntimeError, match="did not create the settings"):
        app_module.ensure_settings()
    for name in ("env_settings_ok", "env_settings_empty"):
        sys.modules.pop(name, None)
