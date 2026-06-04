import typing

from pangloss_core.settings import BaseSettings, DatabaseSettings
from pangloss_sdk.databases.api.settings import ApiAsDatabaseSettings
from pydantic import AnyHttpUrl
from pytest import fixture


@fixture(scope="session", autouse=True)
def initialise_database():
    """Creates a Settings instance for testing. Use the SDK api option
    as it doesn't require any actual database connection"""

    class Settings(BaseSettings):
        PROJECT_NAME: str = "Test"
        BACKEND_CORS_ORIGINS: list[typing.Any] = []
        INSTALLED_APPS: list[str] = []
        DATABASE_MODULE: str = "pangloss_sdk.databases.api"
        DATABASE: DatabaseSettings = ApiAsDatabaseSettings(
            URL=AnyHttpUrl("http://testing.com"), USERNAME="test", PASSWORD="test"
        )
        INTERFACE_LANGUAGES: list[str] = []
        DEFAULT_INTERFACE_LANGUAGE: str = "en"
        AUTHJWT_SECRET_KEY: str = "asdf"
        INTERFACE_LANGUAGES: list[str] = []
        ENTITY_BASE_URL: AnyHttpUrl = AnyHttpUrl("http://test.com/")

    Settings()
    yield
