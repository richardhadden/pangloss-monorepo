"""The migrations that library packages ship cover their models (a project that installs them is not asked for more)"""

import subprocess
import sys
import textwrap

from pangloss_models.migrations.files import graph_of

SHIPPED = {
    "pangloss_neo4j": ["0001_initial", "0002", "0003"],
    "pangloss_dates": ["0001_initial"],
    "pangloss_calendar": ["0001_initial", "0002"],
    "pangloss_zotero": ["0001_initial"],
}

# (run alone: the models of this test session are not those of a project)
CHECK = textwrap.dedent(
    """
    import asyncio, sys
    from types import SimpleNamespace
    from pangloss_models import initialise
    from pangloss_models.migrations import build_snapshot
    from pangloss_models.migrations.files import graph_of
    from pangloss_models.migrations.planner import plan
    from pangloss_models.migrations.startup import structure_of
    from pangloss_neo4j.databases.neo4j import migration_backend
    import pangloss_calendar.models, pangloss_zotero.models

    from pangloss_core.settings import BaseSettings
    from pangloss_neo4j.databases.neo4j.settings import Neo4jDatabaseSettings

    class Settings(BaseSettings[Neo4jDatabaseSettings]):
        PROJECT_NAME: str = "Shipped"
        BACKEND_CORS_ORIGINS: list = []
        INSTALLED_APPS: list[str] = sys.argv[1:]
        DATABASE_MODULE: str = "pangloss_neo4j.databases.neo4j"
        DATABASE: Neo4jDatabaseSettings = Neo4jDatabaseSettings(
            DB_URL="bolt://localhost:1", DB_USERNAME="x", DB_PASSWORD="x", DATABASE_NAME="x"
        )
        INTERFACE_LANGUAGES: list[str] = []
        DEFAULT_INTERFACE_LANGUAGES: str = "en"
        AUTHJWT_SECRET_KEY: str = "a secret for the tests, of a decent length"
        ENTITY_BASE_URL: str = "http://test.com/"

    from pangloss_neo4j.databases.neo4j.database import Database

    Database(settings=Settings())  # (it does not connect)
    apps = sys.argv[1:]
    initialise()
    snapshot = build_snapshot(structure_of(migration_backend))
    result = plan(graph_of(apps), snapshot, apps)
    print("CHANGES", [c.describe() for c in result.changes])
    """
)


def test_each_library_package_ships_its_migrations():
    graph = graph_of(list(SHIPPED))
    for app, prefixes in SHIPPED.items():
        names = [m.name for m in graph.order() if m.app == app]
        assert len(names) == len(prefixes), (app, names)
        for name, prefix in zip(sorted(names), prefixes):
            assert name.startswith(prefix)


def test_nothing_is_left_for_makemigrations_to_write_into_a_package(tmp_path):
    script = tmp_path / "check.py"
    script.write_text(CHECK)
    done = subprocess.run(
        [sys.executable, str(script), *SHIPPED],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        check=False,
    )
    assert done.returncode == 0, done.stderr[-2000:]
    assert "CHANGES []" in done.stdout, done.stdout
