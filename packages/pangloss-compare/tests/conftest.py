import typing

import pytest
from pangloss_core import BaseSettings, DatabaseSettings
from pangloss_models import ModelRegistry
from pydantic import AnyHttpUrl, create_model

# (the apps `pangloss_testing.similar_models` is declared with)
APPS = ["pangloss_derived", "pangloss_library", "pangloss_criteria"]


def make_settings(**more: typing.Any) -> typing.Any:
    """Settings for the models alone (the SDK database module needs no connection)"""
    fields: dict[str, typing.Any] = {
        "PROJECT_NAME": (str, "Test"),
        "BACKEND_CORS_ORIGINS": (list[typing.Any], []),
        "INSTALLED_APPS": (list[str], APPS),
        "STORAGE": (str | None, "pangloss_sdk.storage:api"),
        "DATABASE": (DatabaseSettings, DatabaseSettings()),
        "INTERFACE_LANGUAGES": (list[str], ["en"]),
        "DEFAULT_INTERFACE_LANGUAGE": (str, "en"),
        "AUTHJWT_SECRET_KEY": (str, "asdf"),
        "ENTITY_BASE_URL": (AnyHttpUrl, AnyHttpUrl("http://test.com/")),
    }
    fields |= {name: (typing.Any, value) for name, value in more.items()}
    Settings: typing.Any = create_model("Settings", __base__=BaseSettings, **fields)
    return Settings()


@pytest.fixture(autouse=True)
def reset_models():
    ModelRegistry._reset()
    yield
    # (and after: a class a test means to fail is not left for a test of another package in this worker)
    ModelRegistry._reset()


@pytest.fixture(scope="module", autouse=True)
def settings():
    yield make_settings()
