"""What `read_incoming` works out from the models is forgotten when the models are (`ModelRegistry._reset`): the tests
declare models of the same name again and again, and a project's models are made again when they change"""

import typing

import pytest
from pangloss_core import BaseSettings, DatabaseSettings
from pangloss_core import settings as core_settings
from pangloss_cypher.read_incoming import held_fields
from pangloss_models import Document, Entity, ModelRegistry, ReifiedRelation, initialise
from pydantic import AnyHttpUrl


@pytest.fixture(autouse=True)
def models_without_a_database():
    previous = getattr(core_settings, "SETTINGS", None)

    class Settings(BaseSettings):
        PROJECT_NAME: str = "Incoming"
        BACKEND_CORS_ORIGINS: list[typing.Any] = []
        INSTALLED_APPS: list[str] = []
        STORAGE: str | None = "pangloss_sdk.storage:api"
        DATABASE: DatabaseSettings = DatabaseSettings()
        INTERFACE_LANGUAGES: list[str] = []
        DEFAULT_INTERFACE_LANGUAGE: str = "en"
        AUTHJWT_SECRET_KEY: str = "a secret for the tests, of a decent length"
        ENTITY_BASE_URL: AnyHttpUrl = AnyHttpUrl("http://test.com/")

    Settings()
    ModelRegistry._reset()
    yield
    ModelRegistry._reset()
    if previous is not None:
        core_settings.configure(previous)


def test_the_held_fields_of_a_wrapper_are_those_of_the_models_declared_now():
    class Person(Entity):
        pass

    class Finding(Document):
        about: Person

    initialise()
    assert held_fields("Finding") == {}

    ModelRegistry._reset()

    class Person(Entity):  # noqa: F811
        pass

    class Finding[T](ReifiedRelation[T]):  # noqa: F811
        pass

    class Report(Document):
        finding: Finding[Person]

    initialise()
    assert set(held_fields("Finding")) == {"target"}
