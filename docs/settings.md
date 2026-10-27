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
        DB_USERNAME="...",
        DB_PASSWORD="...",
        DATABASE_NAME="memgraph",
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
| `LOG_LEVEL`, `LOG_FORMAT` | `"INFO"`, `"text"` | What is logged under `pangloss`, and whether a line is text or JSON. See [Logging](logging.md) |
| `SEARCH_TIMEOUT_SECONDS` | `float` (`30`) | The most a structured search may take in the database; a longer one is stopped and answered with a `504` (`PanglossSearchTimeoutError`), and not tried again. `0` is no limit. See [Structured search](structured-search.md#step-5-measured) |
| `DATES_DEFAULT_CALENDAR`, `DATES_PADDING_YEARS`, `DATES_PADDING_MONTHS`, `DATES_PADDING_DAYS`, `DATES_OPEN_END_YEAR`, `DATES_EARLIEST_YEAR` | `"gregorian"`, `1`, `1`, `7`, `1600`, `1` | `pangloss_dates` (optional; read from the settings if set): the calendar of a date that does not say, what doubt adds either side of a year, a month and a day, the year an open or unknown end is taken to stop by, and the year an unknown start is taken to be no earlier than. See [Dates](../guide/dates/README.md#settings) |
| `REVIEW_ALLOW_SELF_REVIEW` | `True` | `pangloss_review` (optional): whether a user may check a document they created or last edited. See [Review](../guide/review/README.md) |
| `SLOW_QUERY_MS`, `SLOW_REQUEST_MS` | `int` (`500`, `2000`) | A database transaction, or a request, that takes longer is logged as a warning. See [Logging](logging.md) |
| `ZOTERO_API_KEY`, `ZOTERO_LIBRARIES`, `ZOTERO_WATCH`, `ZOTERO_SKIP_TYPES`, `ZOTERO_SYNC_USER`, `ZOTERO_API_URL`, `ZOTERO_STREAM_URL` | `pangloss_zotero` (optional; read from the settings if set). See [Zotero](zotero.md#commands-and-settings) |
| `ENTITY_BASE_URL` | `AnyHttpUrl` | Reserved for entity URL generation ⏳ |

## Database settings

| Class | Package | Fields |
|-------|---------|--------|
| `MemgraphDatabaseSettings` | pangloss-memgraph | `DB_URL`, `DB_USERNAME`, `DB_PASSWORD`, `DATABASE_NAME` |
| `SDK_TYPECHECK` | `pangloss_sdk_server` (read from the settings if set) | Default `"auto"`: the stubs of the SDK are type-checked with `ty` when a build is made if `ty` is installed beside the server (and a note says if it is not); `"required"` fails the build without it; `"off"` does not look. See [the SDK](sdk.md) |
| `LOGIN_MAX_FAILURES`, `LOGIN_FAILURE_WINDOW_SECONDS` | `BaseSettings` | Default 10 and 300: wrong passwords for a username before it is refused (`429`) for the rest of the window. 0 turns it off. Per server process. See [the API](api.md) |
| `SdkSettings` (a `ClientSettings`) | pangloss-sdk | `URL`; optional `USERNAME`, `PASSWORD`, `TOKEN`, `TIMEOUT`, `MAX_CONNECTIONS`, `VERIFY_TLS`, `READ_RETRIES`. Environment prefix `PANGLOSS_`. See [the SDK](sdk.md) |

For the Memgraph backend you also need to construct `Database(settings)` before `initialise()` so that `Database.default` exists; see the test fixture `initialise_settings` in `packages/pangloss-memgraph/tests/conftest.py` for a complete example.
