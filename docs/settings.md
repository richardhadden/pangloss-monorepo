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
| `BACKEND_CORS_ORIGINS` | `list` | Accepts a comma-separated string. Reserved for CORS in the web API ⏳ (not read yet) |
| `INSTALLED_APPS` | `list[str]` | Packages whose `cli.py` adds commands to `pangloss`, and whose `models` are imported by `pangloss setup-database`. See [Command line](cli.md) |
| `DATABASE_MODULE` | `str` | Dotted path of the backend package; `initialise()` imports `<it>.exposed_functions` |
| `DATABASE` | `DatabaseSettings` subclass | Backend connection details |
| `INTERFACE_LANGUAGES` | `list[str]` | Reserved for i18n ⏳ |
| `DEFAULT_INTERFACE_LANGUAGE` | `str` (`"en"`) | Reserved for i18n ⏳ |
| `AUTHJWT_SECRET_KEY` | `str` | Signs the API's tokens (use 32 characters or more) |
| `AUTH_ACCESS_TOKEN_EXPIRE_MINUTES`, `AUTH_REFRESH_TOKEN_EXPIRE_DAYS` | `int` (`30`, `14`) | How long tokens last |
| `AUTH_COOKIE_SAMESITE`, `AUTH_COOKIE_SECURE` | `"lax"`, `False` | How the session cookies are set. See [REST API](api.md#authentication) |
| `ENTITY_BASE_URL` | `AnyHttpUrl` | Reserved for entity URL generation ⏳ |

## Database settings

| Class | Package | Fields |
|-------|---------|--------|
| `MemgraphDatabaseSettings` | pangloss-memgraph | `DB_URL`, `DB_USERNAME`, `DB_PASSWORD`, `DATABASE_NAME` |
| `ApiAsDatabaseSettings` | pangloss-sdk | `URL`, `USERNAME`, `PASSWORD` |

For the Memgraph backend you also need to construct `Database(settings)` before `initialise()` so that `Database.default` exists; see the test fixture `initialise_settings` in `packages/pangloss-memgraph/tests/conftest.py` for a complete example.
