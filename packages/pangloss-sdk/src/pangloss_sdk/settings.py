"""Settings of a client of the API.

Given to `connect()`, or read from the environment (`PANGLOSS_URL`, `PANGLOSS_USERNAME`,
`PANGLOSS_PASSWORD`, `PANGLOSS_TOKEN`, ...) and a `.env` in the working directory.
"""

from pangloss_core.settings import ClientSettings
from pydantic import AnyHttpUrl, SecretStr
from pydantic_settings import SettingsConfigDict

ASYNC_DATABASE_MODULE = "pangloss_sdk.databases.api"
SYNC_DATABASE_MODULE = "pangloss_sdk.databases.api_sync"


class SdkSettings(ClientSettings):
    URL: AnyHttpUrl
    # Without these, the first request that needs a login asks for them at a terminal
    USERNAME: str | None = None
    PASSWORD: SecretStr | None = None
    # An access token to use as it is (it is not renewed)
    TOKEN: SecretStr | None = None

    # Seconds
    TIMEOUT: float = 30.0
    # The most requests in flight at once
    MAX_CONNECTIONS: int = 10
    VERIFY_TLS: bool = True
    # How many times a read is tried again after a network error. A write never is: it
    # may have been made
    READ_RETRIES: int = 2

    INSTALLED_APPS: list[str] = []
    DATABASE_MODULE: str = ASYNC_DATABASE_MODULE

    model_config = SettingsConfigDict(
        case_sensitive=True, env_file=".env", env_prefix="PANGLOSS_", extra="ignore"
    )
