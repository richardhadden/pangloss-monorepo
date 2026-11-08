import typing

import pytest
from pangloss_core import BaseSettings, DatabaseSettings
from pangloss_models import ModelRegistry
from pydantic import AnyHttpUrl


@pytest.fixture(autouse=True)
def reset_models():
    ModelRegistry._reset()
    yield
    # (and after: a class a test means to fail, `Wrong`, is not left for a test of another package in this worker)
    ModelRegistry._reset()


@pytest.fixture(scope="module", autouse=True)
def settings():
    """Settings for the models alone (the SDK database module needs no connection)"""

    class Settings(BaseSettings):
        PROJECT_NAME: str = "Test"
        BACKEND_CORS_ORIGINS: list[typing.Any] = []
        INSTALLED_APPS: list[str] = []
        STORAGE: str | None = "pangloss_sdk.storage:api"
        DATABASE: DatabaseSettings = DatabaseSettings()
        INTERFACE_LANGUAGES: list[str] = ["en"]
        DEFAULT_INTERFACE_LANGUAGE: str = "en"
        AUTHJWT_SECRET_KEY: str = "asdf"
        ENTITY_BASE_URL: AnyHttpUrl = AnyHttpUrl("http://test.com/")

    yield Settings()
