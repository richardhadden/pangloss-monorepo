# Settings

Defined in `pangloss_core.settings`. Create **one** `BaseSettings` subclass for your project and instantiate it before calling `initialise()`: construction stores the instance in `pangloss_core.settings.SETTINGS`, which the rest of Pangloss reads.

```python
from pangloss_core.settings import BaseSettings
from pangloss_memgraph.databases.memgraph.settings import MemgraphDatabaseSettings

class Settings(BaseSettings[MemgraphDatabaseSettings]):
    PROJECT_NAME: str = "My project"
    BACKEND_CORS_ORIGINS: list = []
    INSTALLED_APPS: list[str] = []
    DATABASE_MODULE: str = "pangloss_memgraph.databases.memgraph"
    DATABASE: MemgraphDatabaseSettings = MemgraphDatabaseSettings(
        DB_URL="bolt://localhost:7687",
        DB_USERNAME="...", DB_PASSWORD="...", DATABASE_NAME="memgraph",
    )
    INTERFACE_LANGUAGES: list[str] = ["en"]
    AUTHJWT_SECRET_KEY: str = "change me"
    ENTITY_BASE_URL: AnyHttpUrl = AnyHttpUrl("https://example.org/")

Settings()
```

Values can also come from environment variables or a `.env` file (`pydantic-settings`, case sensitive).

| Setting | Type | Used by |
|---------|------|---------|
| `PROJECT_NAME` | `str` | Informational |
| `BACKEND_CORS_ORIGINS` | `list` | The origins of the frontends that may use the API from a browser, such as `http://localhost:5173`. Accepts a comma-separated string. See [REST API](api.md#cors-using-the-api-from-a-frontend) |
| `INSTALLED_APPS` | `list[str]` | Packages whose `cli.py` adds commands to `pangloss`, and whose `models` are imported by `pangloss setup-database`. See [Command line](cli.md) |
| `DATABASE_MODULE` | `str` | Dotted path of the backend package; `initialise()` imports `<it>.exposed_functions` |
| `DATABASE` | `DatabaseSettings` subclass | Backend connection details |
| `INTERFACE_LANGUAGES` | `list[str]` | Reserved for i18n ⏳ |
| `DEFAULT_INTERFACE_LANGUAGE` | `str` (`"en"`) | Reserved for i18n ⏳ |
| `AUTHJWT_SECRET_KEY` | `str` | Signs the API's tokens (use 32 characters or more) |
| `AUTH_ACCESS_TOKEN_EXPIRE_MINUTES`, `AUTH_REFRESH_TOKEN_EXPIRE_DAYS` | `int` (`30`, `14`) | How long tokens last |
| `AUTH_COOKIE_SAMESITE`, `AUTH_COOKIE_SECURE` | `"lax"`, `False` | How the session cookies are set. See [REST API](api.md#authentication) |
| `MIGRATION_CHECK` | `"error"`, `"warn"` or `"off"` (`"error"`) | What the API server does as it starts, if the project has migrations and the database has not had them all, a migration was changed after it was applied, or the models are not what the migrations come to: not start, start and warn, or not look. A project with no migrations is not checked. See [Database migrations](migrations.md) |
| `ENTITY_BASE_URL` | `AnyHttpUrl` | Reserved for entity URL generation ⏳ |

## Database settings

| Class | Package | Fields |
|-------|---------|--------|
| `MemgraphDatabaseSettings` | pangloss-memgraph | `DB_URL`, `DB_USERNAME`, `DB_PASSWORD`, `DATABASE_NAME` |
| `LOGIN_MAX_FAILURES`, `LOGIN_FAILURE_WINDOW_SECONDS` | `BaseSettings` | Default 10 and 300: wrong passwords for a username before it is refused (`429`) for the rest of the window. 0 turns it off. Per server process. See [the API](api.md) |
| `SdkSettings` (a `ClientSettings`) | pangloss-sdk | `URL`; optional `USERNAME`, `PASSWORD`, `TOKEN`, `TIMEOUT`, `MAX_CONNECTIONS`, `VERIFY_TLS`, `READ_RETRIES`. Environment prefix `PANGLOSS_`. See [the SDK](sdk.md) |

For the Memgraph backend you also need to construct `Database(settings)` before `initialise()` so that `Database.default` exists; see the test fixture `initialise_settings` in `packages/pangloss-memgraph/tests/conftest.py` for a complete example.
