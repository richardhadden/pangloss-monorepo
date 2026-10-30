import sys
from pathlib import Path

import pytest
from pangloss_models.model_registry import ModelRegistry

sys.path.insert(0, str(Path(__file__).parent))


@pytest.fixture(autouse=True)
def reset_model_registry():
    ModelRegistry._reset()
    yield


@pytest.fixture
def offline_settings():
    """Settings with a database module that needs no connection (for `initialise()`)"""
    from pangloss_core import settings as core_settings
    from pangloss_core.settings import BaseSettings, DatabaseSettings
    from pydantic import AnyHttpUrl

    class Settings(BaseSettings):
        PROJECT_NAME: str = "Test"
        BACKEND_CORS_ORIGINS: list = []
        INSTALLED_APPS: list[str] = []
        DATABASE_MODULE: str = "pangloss_sdk.databases.api"
        DATABASE: DatabaseSettings = DatabaseSettings()
        INTERFACE_LANGUAGES: list[str] = []
        DEFAULT_INTERFACE_LANGUAGE: str = "en"
        AUTHJWT_SECRET_KEY: str = "asdf"
        ENTITY_BASE_URL: AnyHttpUrl = AnyHttpUrl("http://test.com/")

    saved = core_settings.__dict__.get("SETTINGS")
    made = Settings()
    yield made
    if saved is None:
        core_settings.__dict__.pop("SETTINGS", None)
    else:
        core_settings.SETTINGS = saved
