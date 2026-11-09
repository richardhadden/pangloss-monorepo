"""Settings for pangloss_demo.

Values can also be set in the environment, or in the `.env` file next to
`pyproject.toml` (which is not for version control). `AUTHJWT_SECRET_KEY`, which signs
login tokens, is set there.
"""

from pangloss_core import BaseSettings
from pangloss_memgraph import MemgraphDatabaseSettings
from pydantic import AnyHttpUrl


class Settings(BaseSettings[MemgraphDatabaseSettings]):
    PROJECT_NAME: str = "pangloss_demo"
    # The sites that may use the API from a browser: the frontend, here as the dev
    # server of Vite or SvelteKit runs (add the real address when it is deployed)
    BACKEND_CORS_ORIGINS: list = ["http://localhost:5173"]

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
        "demo_app",
        "pangloss_interface",
        "pangloss_history",
        "pangloss_sdk_server",
        "pangloss_zotero",
        "pangloss_rdf",
    ]

    STORAGE: str | None = "pangloss_memgraph:storage"
    DATABASE: MemgraphDatabaseSettings = MemgraphDatabaseSettings(
        # (the Memgraph container for the demo: `pangloss-memgraph-demo`; port 7687 is
        # the one the tests of the packages use, and clear)
        DB_URL="bolt://localhost:7688",
        DB_USERNAME="test",
        DB_PASSWORD="test",
        DATABASE_NAME="memgraph",
    )

    # The sources are medieval: Julian dates, and a start that is not known is not earlier than 700
    DATES_DEFAULT_CALENDAR: str = "julian"
    DATES_EARLIEST_YEAR: int = 700
    CALENDAR_DEFAULT: str = "julian"
    CALENDAR_FIRST_YEAR: int = 730
    CALENDAR_LAST_YEAR: int = 830

    INTERFACE_LANGUAGES: list[str] = ["en", "de", "fr"]
    ENTITY_BASE_URL: AnyHttpUrl = AnyHttpUrl("http://pangloss-demo-rdf.com/entity/")

    # (no default: it is read from the environment or `.env`)
    AUTHJWT_SECRET_KEY: str

    # Zotero (`pangloss_zotero`): an API key from https://www.zotero.org/settings/keys, read
    # from the environment or `.env`, and the libraries to keep, as "users/N" or "groups/N".
    # With no key or no library the server does not watch Zotero
    ZOTERO_API_KEY: str | None = None
    ZOTERO_LIBRARIES: list[str] = []


Settings()
