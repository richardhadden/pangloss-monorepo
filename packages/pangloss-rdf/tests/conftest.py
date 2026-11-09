import typing

from pangloss_core import BaseSettings, DatabaseSettings
from pangloss_models import ModelRegistry
from pydantic import AnyHttpUrl
from pytest import fixture


@fixture(scope="function", autouse=True)
def reset_model_registry():
    ModelRegistry._reset()
    yield
    ModelRegistry._reset()


@fixture(scope="module", autouse=True)
def rdf_settings():
    class Settings(BaseSettings):
        PROJECT_NAME: str = "Test"
        BACKEND_CORS_ORIGINS: list[typing.Any] = []
        INSTALLED_APPS: list[str] = []
        STORAGE: str | None = "pangloss_sdk.storage:api"
        DATABASE: DatabaseSettings = DatabaseSettings()
        INTERFACE_LANGUAGES: list[str] = []
        DEFAULT_INTERFACE_LANGUAGE: str = "en"
        AUTHJWT_SECRET_KEY: str = "asdf"
        ENTITY_BASE_URL: AnyHttpUrl = AnyHttpUrl("https://example.org/")

    Settings()
    yield
