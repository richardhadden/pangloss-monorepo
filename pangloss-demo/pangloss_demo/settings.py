"""Settings for pangloss_demo.

Values can also be set in the environment, or in the `.env` file next to
`pyproject.toml` (which is not for version control). `AUTHJWT_SECRET_KEY`, which signs
login tokens, is set there.
"""

from pangloss_core.settings import BaseSettings
from pangloss_memgraph.databases.memgraph.settings import MemgraphDatabaseSettings
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
        "demo_app",
        "pangloss_interface",
    ]

    DATABASE_MODULE: str = "pangloss_memgraph.databases.memgraph"
    DATABASE: MemgraphDatabaseSettings = MemgraphDatabaseSettings(
        # (the Memgraph container for the demo: `pangloss-memgraph-demo`; port 7687 is
        # the one the tests of the packages use, and clear)
        DB_URL="bolt://localhost:7688",
        DB_USERNAME="test",
        DB_PASSWORD="test",
        DATABASE_NAME="memgraph",
    )

    INTERFACE_LANGUAGES: list[str] = ["en"]
    ENTITY_BASE_URL: AnyHttpUrl = AnyHttpUrl("http://localhost:8000/entity/")

    # (no default: it is read from the environment or `.env`)
    AUTHJWT_SECRET_KEY: str


Settings()
