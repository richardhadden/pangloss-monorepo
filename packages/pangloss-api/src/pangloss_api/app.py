"""The FastAPI application.

`create_app()` builds it from the project's settings: the settings module is the one
already imported, or the one named by the environment variable `PANGLOSS_SETTINGS`
(which is how `pangloss run` and `pangloss dev` pass it to the server). Building the
app imports the models of the installed apps and initialises them, as its routes are
made from them; starting the server (the lifespan) connects to the database through the
`setup` module of `DATABASE_MODULE`.
"""

import importlib
import os
import warnings
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pangloss_core import settings as core_settings

from pangloss_api.errors import register_error_handlers
from pangloss_api.routes import users
from pangloss_api.routes.models import build_router, routable_models

SETTINGS_ENVIRONMENT_VARIABLE = "PANGLOSS_SETTINGS"


def ensure_settings() -> core_settings.BaseSettings:
    settings = core_settings.__dict__.get("SETTINGS")
    if settings is not None:
        return settings

    module = os.environ.get(SETTINGS_ENVIRONMENT_VARIABLE)
    if not module:
        raise RuntimeError(
            "No settings: import the project's settings before creating the app, or "
            f"set {SETTINGS_ENVIRONMENT_VARIABLE} to the settings module"
        )
    importlib.import_module(module)
    settings = core_settings.__dict__.get("SETTINGS")
    if settings is None:
        raise RuntimeError(f"'{module}' did not create the settings")
    return settings


def prepare_models(settings: core_settings.BaseSettings) -> None:
    """Make the database object, import the models of the installed apps and
    initialise them (which binds the database's functions to them)"""
    backend = importlib.import_module(f"{settings.DATABASE_MODULE}.setup")
    backend.create_database(settings)

    for installed_app in settings.INSTALLED_APPS:
        try:
            importlib.import_module(f"{installed_app}.models")
        except ModuleNotFoundError as error:
            if error.name != f"{installed_app}.models":
                raise

    from pangloss_models import initialise

    initialise()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    backend = importlib.import_module(
        f"{ensure_settings().DATABASE_MODULE}.setup"
    )
    await backend.connect()
    try:
        yield
    finally:
        await backend.disconnect()


MIN_SECRET_LENGTH = 32


def create_app() -> FastAPI:
    settings = ensure_settings()

    if len(settings.AUTHJWT_SECRET_KEY) < MIN_SECRET_LENGTH:
        warnings.warn(
            f"AUTHJWT_SECRET_KEY is shorter than {MIN_SECRET_LENGTH} characters: "
            "tokens signed with it are easy to forge",
            stacklevel=2,
        )

    # (the models are needed now, as the routes are made from them; the connection
    # to the database is made when the server starts)
    prepare_models(settings)

    app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

    register_error_handlers(app)
    app.include_router(users.router)
    for model in routable_models():
        app.include_router(build_router(model))
    return app
