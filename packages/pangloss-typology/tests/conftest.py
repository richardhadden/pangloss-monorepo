import typing

import pytest
from pangloss_core.settings import BaseSettings, DatabaseSettings
from pangloss_models.model_registry import ModelRegistry
from pangloss_typology.typology import Typology
from pydantic import AnyHttpUrl


@pytest.fixture(autouse=True)
def reset_models():
    ModelRegistry._reset()
    Typology.registry.clear()
    yield


@pytest.fixture(scope="module", autouse=True)
def settings():
    """Settings for the models alone (the SDK database module needs no connection)"""

    class Settings(BaseSettings):
        PROJECT_NAME: str = "Test"
        BACKEND_CORS_ORIGINS: list[typing.Any] = []
        INSTALLED_APPS: list[str] = []
        DATABASE_MODULE: str = "pangloss_sdk.databases.api"
        DATABASE: DatabaseSettings = DatabaseSettings()
        INTERFACE_LANGUAGES: list[str] = ["en", "de", "pt-BR"]
        DEFAULT_INTERFACE_LANGUAGE: str = "en"
        AUTHJWT_SECRET_KEY: str = "asdf"
        ENTITY_BASE_URL: AnyHttpUrl = AnyHttpUrl("http://test.com/")

    yield Settings()
