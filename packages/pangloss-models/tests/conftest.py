import sys
import typing
from pathlib import Path

from pangloss_core.settings import BaseSettings, DatabaseSettings
from pangloss_models.model_registry import ModelRegistry
from pydantic import AnyHttpUrl
from pytest import fixture

# the helpers shared by the tests (`kitchen_sink`, `sample_data`, ...) are imported by name
sys.path.insert(0, str(Path(__file__).parent / "support"))


@fixture(scope="function", autouse=True)
def reset_model_registry():

    ModelRegistry._reset()
    yield


@fixture(scope="module", autouse=True)
def initialise_database():
    """Creates a Settings instance for testing. Use the SDK api option
    as it doesn't require any actual database connection"""

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
