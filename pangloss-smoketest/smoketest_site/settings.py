"""Settings for smoketest_site.

Values can also be set in the environment, or in the `.env` file next to
`pyproject.toml` (which is not for version control). `AUTHJWT_SECRET_KEY`, which signs
login tokens, is set there.
"""

from pangloss_core import BaseSettings
from pangloss_memgraph import MemgraphDatabaseSettings
from pydantic import AnyHttpUrl


class Settings(BaseSettings[MemgraphDatabaseSettings]):
    PROJECT_NAME: str = "smoketest_site"
    # The sites that may use the API from a browser: the frontend, here as the dev
    # server of Vite or SvelteKit runs (add the real address when it is deployed)
    BACKEND_CORS_ORIGINS: list = ["http://localhost:5173", "http://localhost:3010"]

    # The packages whose commands and models are used, and your own apps (made with
    # `pangloss new-app <name>`, which adds them here)
    INSTALLED_APPS: list[str] = [
        "pangloss_memgraph",
        "pangloss_users",
        "pangloss_api",
        "pangloss_dates",
        "pangloss_calendar",
        "pangloss_typology",
        "pangloss_review",
        "pangloss_derived",
        "pangloss_library",
        "smoke",
        "pangloss_interface",
        "pangloss_history",
        "pangloss_sdk_server",
        "pangloss_zotero",
    ]

    STORAGE: str | None = "pangloss_memgraph:storage"
    DATABASE: MemgraphDatabaseSettings = MemgraphDatabaseSettings(
        DB_URL="bolt://localhost:7697",
        DB_USERNAME="test",
        DB_PASSWORD="test",
        DATABASE_NAME="memgraph",
    )

    INTERFACE_LANGUAGES: list[str] = ["en"]
    ENTITY_BASE_URL: AnyHttpUrl = AnyHttpUrl("http://localhost:8010/entity/")

    # (no default: it is read from the environment or `.env`)
    AUTHJWT_SECRET_KEY: str

    # The sources are early modern: Gregorian by default, dates not earlier than 1400
    DATES_DEFAULT_CALENDAR: str = "gregorian"
    DATES_EARLIEST_YEAR: int = 1400
    DATES_OPEN_END_YEAR: int = 1700
    CALENDAR_DEFAULT: str = "gregorian"
    CALENDAR_FIRST_YEAR: int = 1450
    CALENDAR_LAST_YEAR: int = 1650

    # (the smoke test logs in with a token as the importer)
    SDK_ACCESS: str = "user"

    ZOTERO_API_KEY: str | None = None
    ZOTERO_LIBRARIES: list[str] = []


Settings()
