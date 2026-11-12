import json
import re
import typing

from pydantic import AnyHttpUrl, field_validator, model_validator
from pydantic_settings import BaseSettings as PydanticBaseSettings
from pydantic_settings import NoDecode, SettingsConfigDict

# An origin is a scheme, host and (maybe) port, and no more
CORS_ORIGIN = re.compile(r"^https?://[^/\s?#]+$")


def normalise_cors_origins(value: typing.Any) -> list[str]:
    """The origins that may use the API from a browser, from a list or a string of
    them (comma separated, or a JSON list): as a browser sends them, without a
    trailing `/`. `*` allows any."""
    if isinstance(value, str):
        value = value.strip()
        value = json.loads(value) if value.startswith("[") else value.split(",")
    if not isinstance(value, list | tuple | set):
        raise ValueError(f"Not a list of origins: {value!r}")

    origins = []
    for item in value:
        origin = str(item).strip().rstrip("/").lower()
        if not origin:
            continue
        if origin != "*" and not CORS_ORIGIN.match(origin):
            raise ValueError(
                f"'{item}' is not an origin: it should be like 'https://example.com' "
                "or 'http://localhost:5173' (no path), or '*'"
            )
        origins.append(origin)
    return origins


class DatabaseSettings(PydanticBaseSettings):
    pass


class ClientSettings(PydanticBaseSettings):
    """What the models need of the settings: which apps declare them, and which storage
    backend `save`, `get` and so on are bound to. A client of the API (the SDK) has no
    more than this; the server's `BaseSettings` adds the rest.

    Making settings makes them the project's (`SETTINGS`), once they are valid: `configure`
    does the same for settings that were made before."""

    INSTALLED_APPS: list[str]
    # The storage backend, as `module:attribute`: "pangloss_memgraph:storage" (see `pangloss_core.storage`)
    STORAGE: str | None = None
    # (what came before `STORAGE`: the module path of the backend. Still read, with a warning)
    DATABASE_MODULE: str | None = None
    # The server's values of the settings that the models are made from (`model_settings`), for a client that has
    # not got the server's settings: the SDK of a project fills it in
    MODEL_SETTINGS: dict[str, typing.Any] = {}

    model_config = SettingsConfigDict(case_sensitive=True, env_file=".env")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        configure(self)

    @model_validator(mode="after")
    def storage_is_named(self) -> typing.Self:
        if not self.STORAGE and not self.DATABASE_MODULE:
            raise ValueError(
                "STORAGE is required: the storage backend, like 'pangloss_memgraph:storage'"
            )
        if not self.STORAGE and self.DATABASE_MODULE:
            from pangloss_core.storage import warn_database_module

            warn_database_module(self.DATABASE_MODULE)
        return self


class BaseSettings[TDatabaseSettings: DatabaseSettings](ClientSettings):
    PROJECT_NAME: str
    # The origins (`http://localhost:5173`) of the frontends that may use the API
    # from a browser. A comma-separated string is accepted too, as is `*` (see the API)
    BACKEND_CORS_ORIGINS: typing.Annotated[list[typing.Any], NoDecode]
    DATABASE: TDatabaseSettings

    INTERFACE_LANGUAGES: list[str] = []
    DEFAULT_INTERFACE_LANGUAGE: str = "en"

    AUTHJWT_SECRET_KEY: str

    # Authentication: how long tokens last, and how the session cookies are set
    AUTH_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    AUTH_REFRESH_TOKEN_EXPIRE_DAYS: int = 14
    AUTH_COOKIE_SAMESITE: typing.Literal["lax", "strict", "none"] = "lax"
    AUTH_COOKIE_SECURE: bool = False

    # After this many wrong passwords for a username within the window, it is refused
    # (`429`) until they are out of it. 0 turns it off. Kept per server process
    LOGIN_MAX_FAILURES: int = 10
    LOGIN_FAILURE_WINDOW_SECONDS: int = 300

    ENTITY_BASE_URL: AnyHttpUrl

    # Logging (see `pangloss_core.logs`): what is logged under `pangloss`, and how: a line of
    # text, or of JSON. Over `SLOW_QUERY_MS` a database transaction, and over `SLOW_REQUEST_MS` a
    # request, is logged as a warning
    LOG_LEVEL: typing.Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    LOG_FORMAT: typing.Literal["text", "json"] = "text"
    SLOW_QUERY_MS: int = 500
    SLOW_REQUEST_MS: int = 2000

    # The most a structured search (`/api/search`) may take, in the database; one that takes longer is
    # stopped and answered with a `504`, and is not tried again. 0 is no limit
    SEARCH_TIMEOUT_SECONDS: float = 30

    # The most hits the text index gives for each word of a search of a list (`?q=`, with or without `deep`):
    # more than this are not looked at, and the page says `truncated`. (The index gives 1000 unless asked for more)
    SEARCH_HIT_LIMIT: int = 100_000

    # A merge of two entities (`Entity.merge`; implementation_docs/entity-identity.md) that would write more documents and entities than
    # this is made only when asked for as a large one (by an admin), in batches; up to it, a merge is one transaction
    MERGE_LIMIT: int = 1000
    # How many seconds after a merge the references that writes under way left on the absorbed entity are looked for
    # again (0: not again). None: what the database needs (Memgraph 0, Neo4j 5)
    MERGE_SECOND_PASS_SECONDS: float | None = None
    # Who may merge two entities, and undo a merge, without anyone else: "admin" (admins), "any" (every logged-in
    # user) or "none" (nobody). Everyone else proposes it, and a second, different user carries it out
    MERGE_DIRECTLY: typing.Literal["admin", "any", "none"] = "admin"

    # What the server does at start-up if the project has migrations and the database is not
    # what they say, or the models are not what they come to: "error" does not start, "warn"
    # starts and says so, "off" does not look
    MIGRATION_CHECK: typing.Literal["error", "warn", "off"] = "error"
    # How often (seconds) a running server looks whether the database has been migrated under it, after
    # which it answers 503 until it is restarted; 0: only before a write and after a failure
    MIGRATION_WATCH_SECONDS: float = 10.0

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: typing.Any) -> list[str]:
        return normalise_cors_origins(v)


# (a client has only the `ClientSettings` part: the server code that uses the rest runs
# only where there is a `BaseSettings`)
SETTINGS: BaseSettings


def configure(settings: ClientSettings) -> None:
    """Make these the project's settings"""
    global SETTINGS
    SETTINGS = typing.cast("BaseSettings", settings)


# The names of the settings that change what the models are, not only how a server runs (the languages that a type of
# `pangloss-typology` has a label in). A package that reads one while the models are made adds its name here and reads
# it with `model_setting`: the SDK of a project is built with their values, so that a client makes the server's models
model_settings: set[str] = set()


def model_setting(name: str, default: typing.Any = None) -> typing.Any:
    """A setting that the models are made from: the project's, or on a client what its SDK says the server's is"""
    settings = globals().get("SETTINGS")
    if settings is None:
        return default
    if hasattr(settings, name):
        return getattr(settings, name)
    return settings.MODEL_SETTINGS.get(name, default)


def get_settings() -> BaseSettings:
    """The project's settings: an error that says so if there are none yet"""
    settings = globals().get("SETTINGS")
    if settings is None:
        raise RuntimeError(
            "There are no settings yet: import the project's settings module (which makes them) first"
        )
    return settings
