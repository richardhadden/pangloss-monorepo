import typing

from pangloss_core.settings import BaseSettings, DatabaseSettings
from pangloss_models.model_registry import ModelRegistry
from pydantic import AnyHttpUrl
from pytest import fixture


@fixture(scope="function", autouse=True)
def reset_model_registry():
    ModelRegistry._reset()
    yield


@fixture(scope="module", autouse=True)
def initialise_database():
    """Settings for testing, with the SDK's api module so that no database is needed"""

    class Settings(BaseSettings):
        PROJECT_NAME: str = "Test"
        BACKEND_CORS_ORIGINS: list[typing.Any] = []
        INSTALLED_APPS: list[str] = []
        DATABASE_MODULE: str = "pangloss_sdk.databases.api"
        DATABASE: DatabaseSettings = DatabaseSettings()
        INTERFACE_LANGUAGES: list[str] = []
        DEFAULT_INTERFACE_LANGUAGE: str = "en"
        AUTHJWT_SECRET_KEY: str = "asdf"
        ENTITY_BASE_URL: AnyHttpUrl = AnyHttpUrl("http://test.com/")

    Settings()
    yield
