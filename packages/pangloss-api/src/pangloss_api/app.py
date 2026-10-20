"""The FastAPI application.

`create_app()` builds it from the project's settings: the settings module is the one
already imported, or the one named by the environment variable `PANGLOSS_SETTINGS`
(which is how `pangloss run` and `pangloss dev` pass it to the server). Starting the
server (the lifespan) imports the models of the installed apps, initialises them, and
connects to the database through the `setup` module of `DATABASE_MODULE`.
"""

import importlib
import os
import warnings
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pangloss_core import settings as core_settings
from pangloss_users.exceptions import (
    PanglossInvalidUserError,
    PanglossUserDoesNotExistError,
    PanglossUserError,
    PanglossUserExistsError,
)

from pangloss_api.routes import users

SETTINGS_ENVIRONMENT_VARIABLE = "PANGLOSS_SETTINGS"

# How errors about users are reported
USER_ERROR_STATUS = {
    PanglossUserExistsError: 409,
    PanglossUserDoesNotExistError: 404,
    PanglossInvalidUserError: 422,
}


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


async def user_error_handler(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, PanglossUserError)
    status_code = next(
        (code for kind, code in USER_ERROR_STATUS.items() if isinstance(error, kind)),
        400,
    )
    return JSONResponse(status_code=status_code, content={"detail": str(error)})


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = ensure_settings()

    backend = importlib.import_module(f"{settings.DATABASE_MODULE}.setup")
    backend.create_database(settings)

    from pangloss_models import initialise

    for installed_app in settings.INSTALLED_APPS:
        try:
            importlib.import_module(f"{installed_app}.models")
        except ModuleNotFoundError as error:
            if error.name != f"{installed_app}.models":
                raise
    initialise()

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

    app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

    app.add_exception_handler(PanglossUserError, user_error_handler)
    app.include_router(users.router)
    return app
