import pytest
from fake_api_db import exposed_functions
from fastapi.testclient import TestClient
from pangloss_api.app import create_app
from pangloss_core import settings as core_settings
from pangloss_core.settings import BaseSettings, DatabaseSettings
from pangloss_models.model_registry import ModelRegistry
from pydantic import AnyHttpUrl

PASSWORD = "correct horse"


class Settings(BaseSettings[DatabaseSettings]):
    PROJECT_NAME: str = "Test"
    BACKEND_CORS_ORIGINS: list = []
    INSTALLED_APPS: list[str] = []
    DATABASE_MODULE: str = "fake_api_db"
    DATABASE: DatabaseSettings = DatabaseSettings()
    INTERFACE_LANGUAGES: list[str] = []
    AUTHJWT_SECRET_KEY: str = "a secret for the tests, of a decent length"
    ENTITY_BASE_URL: AnyHttpUrl = AnyHttpUrl("http://test.com/")


@pytest.fixture(autouse=True)
def reset_model_registry():
    ModelRegistry._reset()
    yield


@pytest.fixture
def settings():
    # (the settings are global, and other packages' tests use them: put them back)
    saved = core_settings.__dict__.get("SETTINGS")
    exposed_functions.USERS.clear()
    exposed_functions.REVOKED.clear()
    exposed_functions.ACCESS_TOKENS.clear()
    yield Settings()
    exposed_functions.USERS.clear()
    exposed_functions.REVOKED.clear()
    exposed_functions.ACCESS_TOKENS.clear()
    if saved is None:
        core_settings.__dict__.pop("SETTINGS", None)
    else:
        core_settings.SETTINGS = saved


@pytest.fixture
def app(settings):
    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app)
