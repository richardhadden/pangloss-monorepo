"""The server does not start with migrations pending, or models that are not what they say"""

import importlib
import sys

import pytest
from conftest import Settings
from fake_api_db import migration_backend
from fastapi.testclient import TestClient
from pangloss_api.app import create_app
from pangloss_models.exceptions import PanglossMigrationError
from pangloss_models.migrations import build_snapshot
from pangloss_models.migrations.files import MigrationGraph, graph_of, migrations_directory, write
from pangloss_models.migrations.planner import plan


@pytest.fixture
def project(settings, tmp_path, monkeypatch):
    """An app, `checkapp`, with models, and a function to write its migrations"""
    package = tmp_path / "checkapp"
    package.mkdir()
    (package / "__init__.py").write_text("")
    models = package / "models.py"
    models.write_text(
        "from pangloss_models.model_bases.entity import Entity\n\n\nclass Person(Entity):\n    name: str\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()
    migration_backend.APPLIED.clear()
    yield models
    migration_backend.APPLIED.clear()
    for name in [n for n in sys.modules if n.split(".")[0] == "checkapp"]:
        del sys.modules[name]


def write_migrations() -> None:
    graph = graph_of(["checkapp"])
    for migration in plan(graph, build_snapshot(), ["checkapp"]).migrations:
        write(migration, migrations_directory(migration.app))


def start(mode="error"):
    Settings(INSTALLED_APPS=["checkapp"], MIGRATION_CHECK=mode)
    app = create_app()
    with TestClient(app):  # (the server starts)
        pass


def mark_applied() -> None:
    for migration in graph_of(["checkapp"]).order():
        migration_backend.APPLIED[migration.key] = {
            "status": "applied",
            "checksum": migration.checksum,
        }


def test_a_project_without_migrations_is_not_checked(project):
    start()


def test_migrations_that_have_not_been_applied_stop_the_server(project):
    Settings(INSTALLED_APPS=["checkapp"])
    create_app()
    write_migrations()
    with pytest.raises(PanglossMigrationError, match="have not been applied.*pangloss migrate"):
        start()


def test_a_database_that_has_them_all_starts(project):
    Settings(INSTALLED_APPS=["checkapp"])
    create_app()
    write_migrations()
    mark_applied()
    start()


def test_models_that_have_changed_since_the_migrations_stop_the_server(project):
    Settings(INSTALLED_APPS=["checkapp"])
    create_app()
    write_migrations()
    mark_applied()
    project.write_text(project.read_text() + "    born: int\n")
    for name in [n for n in sys.modules if n.startswith("checkapp.models")]:
        del sys.modules[name]
    from pangloss_models.model_registry import ModelRegistry

    ModelRegistry._reset()
    with pytest.raises(PanglossMigrationError, match="not what the migrations come to"):
        start()


def test_a_migration_changed_after_it_was_applied_stops_the_server(project):
    Settings(INSTALLED_APPS=["checkapp"])
    create_app()
    write_migrations()
    mark_applied()
    migration_backend.APPLIED[("checkapp", "0001_initial")]["checksum"] = "something else"
    with pytest.raises(PanglossMigrationError, match="has been changed since"):
        start()


def test_the_check_can_warn_or_be_turned_off(project):
    Settings(INSTALLED_APPS=["checkapp"])
    create_app()
    write_migrations()
    with pytest.warns(UserWarning, match="have not been applied"):
        start("warn")
    start("off")


def test_a_write_during_a_migration_is_answered_with_unavailable_and_when_to_try_again():
    import asyncio

    from pangloss_api.errors import error_handler, status_for
    from pangloss_models.exceptions import PanglossReadOnlyError, PanglossWriteError

    error = PanglossReadOnlyError("The database is being migrated")
    assert status_for(error) == 503
    assert status_for(PanglossWriteError("x")) == 400  # (an ordinary write error is as it was)

    response = asyncio.run(error_handler(None, error))  # type: ignore[arg-type]
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "30"
    assert b"being migrated" in response.body
