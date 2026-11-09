"""The FastAPI application.

`create_app()` builds it from the project's settings: the settings module is the one
already imported, or the one named by the environment variable `PANGLOSS_SETTINGS`
(which is how `pangloss run` and `pangloss dev` pass it to the server). Building the
app imports the models of the installed apps and initialises them, as its routes are
made from them; starting the server (the lifespan) connects to the database through the
`setup` of the storage backend (`STORAGE`).
"""

import importlib
import logging
import os
import warnings
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pangloss_core import check_requirements, storage_of
from pangloss_core import settings as core_settings
from pangloss_core.logs import configure_from_settings
from pangloss_models import ModelRegistry

from pangloss_api.background import Supervisor
from pangloss_api.dependencies import set_visibility
from pangloss_api.errors import ServerErrorResponder, register_error_handlers
from pangloss_api.migration_watch import MigrationGate, MigrationWatch
from pangloss_api.openapi import add_rapidoc, make_openapi_in_a_thread
from pangloss_api.query import QueryNames, known_parameters
from pangloss_api.request_log import RequestLogger
from pangloss_api.routes import (
    autocomplete,
    references,
    search,
    search_everything,
    users,
)
from pangloss_api.routes.models import build_router, routable_models

SETTINGS_ENVIRONMENT_VARIABLE = "PANGLOSS_SETTINGS"

logger = logging.getLogger("pangloss.api.app")


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
    initialise them (which binds the database's functions to them). Refused if the backend cannot do what an installed
    app needs"""
    check_requirements(settings)
    storage_of(settings).setup.create_database(settings)

    for installed_app in settings.INSTALLED_APPS:
        try:
            importlib.import_module(f"{installed_app}.models")
        except ModuleNotFoundError as error:
            if error.name != f"{installed_app}.models":
                raise

    from pangloss_models import initialise

    initialise()


async def check_migrations(
    settings: core_settings.BaseSettings,
) -> MigrationWatch | None:
    """If the project has migrations, the database must be what they say and the models what
    they come to: `MIGRATION_CHECK` says what to do if not (see `docs/migrations.md`). The answer is
    a watch for a migration made while the server runs, to be started (`None` if nothing is checked)"""
    from pangloss_models import PanglossMigrationError
    from pangloss_models.migrations.startup import (
        migration_backend_of,
        migration_problems,
    )

    if settings.MIGRATION_CHECK == "off":
        return None
    migrations = migration_backend_of(storage_of(settings))
    if migrations is None:
        return None
    watch = MigrationWatch(
        migrations, settings.INSTALLED_APPS, settings.MIGRATION_WATCH_SECONDS
    )
    found = await migration_problems(settings.INSTALLED_APPS, migrations)
    if not found:
        logger.info("Migrations: the database and the models agree with them")
        return watch
    message = (
        "The database and the models do not agree with the migrations:\n  "
        + "\n  ".join(found)
    )
    if settings.MIGRATION_CHECK == "error":
        logger.error("%s", message)
        raise PanglossMigrationError(message)
    logger.warning("%s", message)
    warnings.warn(message, stacklevel=2)
    return watch


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings = ensure_settings()
    storage = storage_of(settings)
    backend = storage.setup
    logger.info(
        "Starting %s: %s, %s models, apps %s",
        settings.PROJECT_NAME,
        storage.name,
        len(ModelRegistry.all_models()),
        ", ".join(settings.INSTALLED_APPS) or "(none)",
    )
    await backend.connect()
    watch = None
    try:
        watch = app.state.migration_watch = await check_migrations(settings)
        if watch is not None:
            await watch.start()
        # (what installed apps asked to be done when the server starts; see `configure_apps`)
        for hook in app.state.startup_hooks:
            await hook()
        # (what installed apps keep running as long as the server does: see `background.py`)
        supervisor = Supervisor(settings, list(app.state.background_tasks))
        app.state.supervisor = supervisor
        supervisor.start()
        logger.info("%s is ready", settings.PROJECT_NAME)
        try:
            yield
        finally:
            await supervisor.stop()
    finally:
        if watch is not None:
            await watch.stop()
        await backend.disconnect()
        logger.info("%s stopped", settings.PROJECT_NAME)


MIN_SECRET_LENGTH = 32
# (smaller answers are sent as they are: compressing them saves nothing worth the time)
GZIP_MINIMUM_SIZE = 1000

CORS_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]


def app_routers(apps: list[str]) -> list[APIRouter]:
    """The `router` of the `api` module of each installed app that has one (as an app
    adds commands with `cli.py`). An error inside a module that exists is not hidden."""
    routers = []
    for app in apps:
        try:
            module = importlib.import_module(f"{app}.api")
        except ModuleNotFoundError as error:
            if error.name in (app, f"{app}.api") or (
                error.name and app.startswith(f"{error.name}.")
            ):
                continue
            raise
        router = getattr(module, "router", None)
        if router is None:
            continue
        if not isinstance(router, APIRouter):
            raise TypeError(f"{app}.api has a 'router' that is not a FastAPI APIRouter")
        routers.append(router)
    return routers


def configure_apps(app: FastAPI, settings: core_settings.BaseSettings) -> None:
    """Let each installed app that has a `configure_app(app, settings)` in its `api` module
    set up the app: add middleware, add a function to `app.state.startup_hooks` (async,
    called as the server starts, after the migrations are checked), or a `BackgroundTask` to
    `app.state.background_tasks` (kept running as long as the server does)"""
    for installed_app in settings.INSTALLED_APPS:
        try:
            module = importlib.import_module(f"{installed_app}.api")
        except ModuleNotFoundError as error:
            if error.name in (installed_app, f"{installed_app}.api"):
                continue
            raise
        configure = getattr(module, "configure_app", None)
        if configure is not None:
            configure(app, settings)


def add_cors(app: FastAPI, origins: list[str]) -> None:
    """Let a browser use the API from a page on one of the origins.

    Cookies (the session) are sent with a request from those origins, which is what
    `credentials: "include"` is for in the frontend. Not with `*`: any site could
    then use the cookies of whoever visits it; so with `*`, only the `Authorization`
    header can be used to log in."""
    if not origins:
        return
    anyone = "*" in origins
    if anyone:
        warnings.warn(
            "BACKEND_CORS_ORIGINS has '*': any site can use the API from a browser "
            "(though not with the session cookies)",
            stacklevel=3,
        )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if anyone else origins,
        allow_credentials=not anyone,
        allow_methods=CORS_METHODS,
        allow_headers=["Authorization", "Content-Type", "Accept", "If-Match"],
        expose_headers=["ETag"],
        max_age=600,
    )


def create_app() -> FastAPI:
    settings = ensure_settings()
    configure_from_settings(settings)

    # (refused, not warned of: a server whose tokens can be forged should not start)
    if len(settings.AUTHJWT_SECRET_KEY) < MIN_SECRET_LENGTH:
        raise RuntimeError(
            f"AUTHJWT_SECRET_KEY is shorter than {MIN_SECRET_LENGTH} characters: tokens "
            "signed with it are easy to forge. Set a long random one in .env (as "
            "`pangloss new` does)"
        )

    # (the models are needed now, as the routes are made from them; the connection
    # to the database is made when the server starts)
    prepare_models(settings)

    app = FastAPI(
        title=settings.PROJECT_NAME,
        lifespan=lifespan,
        # (RapiDoc instead: see `add_rapidoc`)
        docs_url=None,
        dependencies=[Depends(set_visibility), Depends(known_parameters)],
    )
    app.state.startup_hooks = []
    app.state.background_tasks = []

    # (added first, so inside the CORS middleware: a 500 then has the CORS headers)
    app.add_middleware(ServerErrorResponder)
    # (once the database has been migrated under the server, nothing is answered but that: see `migration_watch`)
    app.add_middleware(MigrationGate)
    add_cors(app, settings.BACKEND_CORS_ORIGINS)
    # (compressed when the client accepts it: the JSON of an entity with many references, the calendar and
    # /openapi.json run to megabytes and shrink by 90% or more; event streams are left alone by the middleware)
    app.add_middleware(GZipMiddleware, minimum_size=GZIP_MINIMUM_SIZE)
    # (outside all but what the installed apps add: the request id is on everything logged for the request)
    app.add_middleware(RequestLogger)
    register_error_handlers(app)
    configure_apps(app, settings)
    # (added last, so outermost: everything else, an app's middleware too, reads the parameters in snake_case)
    app.add_middleware(QueryNames)
    app.include_router(users.router)
    app.include_router(autocomplete.router)
    app.include_router(references.router)
    app.include_router(search.router)
    app.include_router(search_everything.router)
    for router in app_routers(settings.INSTALLED_APPS):
        app.include_router(router)
    for model in routable_models():
        app.include_router(build_router(model))
    # (the document of all those routes takes seconds to make for a large project: not on the event loop)
    make_openapi_in_a_thread(app)
    add_rapidoc(app)
    return app
