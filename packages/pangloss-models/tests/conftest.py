import sys
import typing
from pathlib import Path

from pangloss_core import BaseSettings, DatabaseSettings
from pangloss_models import ModelRegistry
from pydantic import AnyHttpUrl
from pytest import fixture

# the helpers shared by the tests (`kitchen_sink`, `sample_data`, ...) are imported by name
sys.path.insert(0, str(Path(__file__).parent / "support"))


@fixture(scope="function", autouse=True)
def reset_model_registry():

    ModelRegistry._reset()
    yield
    # (and after: what a test declared, which may be a class it means to fail, is not left for a test of another
    # package that the same worker runs next)
    ModelRegistry._reset()


@fixture(scope="module", autouse=True)
def initialise_database():
    """Creates a Settings instance for testing. Use the SDK api option
    as it doesn't require any actual database connection"""

    class Settings(BaseSettings):
        PROJECT_NAME: str = "Test"
        BACKEND_CORS_ORIGINS: list[typing.Any] = []
        INSTALLED_APPS: list[str] = []
        STORAGE: str | None = "pangloss_sdk.storage:api"
        DATABASE: DatabaseSettings = DatabaseSettings()
        INTERFACE_LANGUAGES: list[str] = []
        DEFAULT_INTERFACE_LANGUAGE: str = "en"
        AUTHJWT_SECRET_KEY: str = "asdf"
        ENTITY_BASE_URL: AnyHttpUrl = AnyHttpUrl("http://test.com/")

    Settings()
    yield
