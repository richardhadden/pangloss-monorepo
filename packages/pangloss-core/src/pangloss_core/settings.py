import json
import re
import typing

from pydantic import AnyHttpUrl, field_validator
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


class BaseSettings[TDatabaseSettings: DatabaseSettings](PydanticBaseSettings):
    PROJECT_NAME: str
    # The origins (`http://localhost:5173`) of the frontends that may use the API
    # from a browser. A comma-separated string is accepted too, as is `*` (see the API)
    BACKEND_CORS_ORIGINS: typing.Annotated[list[typing.Any], NoDecode]
    INSTALLED_APPS: list[str]
    DATABASE_MODULE: str
    DATABASE: TDatabaseSettings

    INTERFACE_LANGUAGES: list[str] = []
    DEFAULT_INTERFACE_LANGUAGE: str = "en"

    AUTHJWT_SECRET_KEY: str

    # Authentication: how long tokens last, and how the session cookies are set
    AUTH_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    AUTH_REFRESH_TOKEN_EXPIRE_DAYS: int = 14
    AUTH_COOKIE_SAMESITE: typing.Literal["lax", "strict", "none"] = "lax"
    AUTH_COOKIE_SECURE: bool = False

    ENTITY_BASE_URL: AnyHttpUrl

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: typing.Any) -> list[str]:
        return normalise_cors_origins(v)

    model_config = SettingsConfigDict(case_sensitive=True, env_file=".env")

    def __init__(self, *args, **kwargs):
        # When initialising settings, copy it to this global var for access
        # within pangloss_core
        global SETTINGS

        SETTINGS = self
        super().__init__(*args, **kwargs)


SETTINGS: BaseSettings
