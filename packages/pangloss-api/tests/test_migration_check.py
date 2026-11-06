"""The server does not start with migrations pending, or models that are not what they say"""

import importlib
import warnings
import sys

import pytest
from conftest import Settings
from fake_api_db import migration_backend
from fastapi.testclient import TestClient
from pangloss_api import create_app
from pangloss_models import PanglossMigrationError
from pangloss_models.migrations import build_snapshot
from pangloss_models.migrations.files import (
    graph_of,
    migrations_directory,
    write,
)
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
    with pytest.raises(
        PanglossMigrationError, match="have not been applied.*pangloss migrate"
    ):
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
    from pangloss_models import ModelRegistry

    ModelRegistry._reset()
    with pytest.raises(PanglossMigrationError, match="not what the migrations come to"):
        start()


def test_a_migration_changed_after_it_was_applied_stops_the_server(project):
    Settings(INSTALLED_APPS=["checkapp"])
    create_app()
    write_migrations()
    mark_applied()
    migration_backend.APPLIED[("checkapp", "0001_initial")]["checksum"] = (
        "something else"
    )
    with pytest.raises(PanglossMigrationError, match="has been changed since"):
        start()


def test_the_check_can_warn_or_be_turned_off(project):
    Settings(INSTALLED_APPS=["checkapp"])
    create_app()
    write_migrations()
    with pytest.warns(UserWarning, match="have not been applied"):
        start("warn")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        start("off")


def test_a_write_during_a_migration_is_answered_with_unavailable_and_when_to_try_again():
    import asyncio

    from pangloss_api.errors import error_handler, status_for
    from pangloss_models import PanglossReadOnlyError, PanglossWriteError

    error = PanglossReadOnlyError("The database is being migrated")
    assert status_for(error) == 503
    assert (
        status_for(PanglossWriteError("x")) == 400
    )  # (an ordinary write error is as it was)

    response = asyncio.run(error_handler(None, error))  # type: ignore[arg-type]
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "30"
    assert b"being migrated" in response.body


def test_the_migration_check_is_logged(settings, caplog):
    import asyncio
    import logging

    from pangloss_api import app as app_module

    caplog.set_level(logging.INFO, logger="pangloss")

    class Migrations:
        pass

    async def problems(apps, migrations):
        return ["the database is behind: 1 migration to apply"]

    def backend_of(module):
        return Migrations()

    import pangloss_models.migrations.startup as startup

    original = (startup.migration_backend_of, startup.migration_problems)
    startup.migration_backend_of, startup.migration_problems = backend_of, problems
    try:
        settings.MIGRATION_CHECK = "warn"
        with pytest.warns(UserWarning):
            asyncio.run(app_module.check_migrations(settings))
        assert any(
            r.levelname == "WARNING" and "1 migration to apply" in r.getMessage()
            for r in caplog.records
        )

        settings.MIGRATION_CHECK = "error"
        with pytest.raises(Exception, match="do not agree"):
            asyncio.run(app_module.check_migrations(settings))
        assert any(r.levelname == "ERROR" for r in caplog.records)

        async def none(apps, migrations):
            return []

        startup.migration_problems = none
        caplog.clear()
        asyncio.run(app_module.check_migrations(settings))
        assert "the database and the models agree" in caplog.text
    finally:
        startup.migration_backend_of, startup.migration_problems = original


# --- a migration made while the server runs --------------------------------------------------------


def running(mode="error", **more):
    Settings(INSTALLED_APPS=["checkapp"], MIGRATION_CHECK=mode, **more)
    return TestClient(create_app())


def apply_one_the_server_does_not_have(name="0002_later") -> None:
    migration_backend.APPLIED[("checkapp", name)] = {"status": "applied"}


def test_a_server_whose_database_is_migrated_under_it_says_so(project, monkeypatch):
    import asyncio

    from pangloss_api import migration_watch
    from test_model_routes import login

    Settings(INSTALLED_APPS=["checkapp"])
    create_app()
    write_migrations()
    mark_applied()
    # (the watch's own loop is not waited for here: it looks before a write, and when it is asked to)
    with running(MIGRATION_WATCH_SECONDS=0) as client:
        john = login(client)
        watch = client.app.state.migration_watch
        assert client.get("/api/Person").status_code != 503
        assert watch.moved is None

        # a migration that is running (not applied yet) changes nothing here
        migration_backend.APPLIED[("checkapp", "0002_later")] = {"status": "running"}
        assert asyncio.run(watch.look()) is None

        apply_one_the_server_does_not_have()
        # (a read is not looked into: within a second of the last look it is answered as before)
        assert client.get("/api/Person").status_code != 503
        # ... a write looks first, once the last look is not fresh
        monkeypatch.setattr(migration_watch, "FRESH", 0)
        refused = client.post(
            "/api/Person",
            headers=john,
            json={"type": "Person", "label": "x", "name": "x"},
        )
        assert refused.status_code == 503
        assert "has been migrated since this server started" in refused.json()["detail"]
        assert "checkapp.0002_later applied" in refused.json()["detail"]
        assert "Restart the server" in refused.json()["detail"]
        # and from then on everything under /api is, reads too; what is not the API is not
        assert client.get("/api/Person").status_code == 503
        assert client.get("/api/users/me", headers=john).status_code == 503
        assert client.get("/openapi.json").status_code == 200

        # (it stays so: taking the record away again does not make the models right)
        del migration_backend.APPLIED[("checkapp", "0002_later")]
        assert client.get("/api/Person").status_code == 503


def test_a_request_that_fails_after_a_migration_is_a_503_not_a_500(
    project, monkeypatch
):
    from pangloss_api import migration_watch
    from pangloss_models import ModelRegistry
    from test_model_routes import stub

    Settings(INSTALLED_APPS=["checkapp"])
    create_app()
    write_migrations()
    mark_applied()
    with running(MIGRATION_WATCH_SECONDS=0) as client:
        Person = ModelRegistry.all_models()["Person"]

        async def list_(cls, **kwargs):
            raise ValueError("the data is not what the models say")

        stub(monkeypatch, Person, "list", list_)
        monkeypatch.setattr(migration_watch, "FRESH", 0)
        # a bug is a 500
        assert client.get("/api/Person").status_code == 500
        # ... but not when the database has moved on: that is why it failed
        apply_one_the_server_does_not_have()
        failed = client.get("/api/Person")
        assert failed.status_code == 503
        assert "Restart the server" in failed.json()["detail"]


def test_migrating_back_is_noticed_and_applying_what_the_server_has_is_not(project):
    import asyncio

    Settings(INSTALLED_APPS=["checkapp"])
    create_app()
    write_migrations()
    # (started with its migrations pending: applying them later is what its models already are)
    with pytest.warns(UserWarning, match="have not been applied"):
        client = running("warn", MIGRATION_WATCH_SECONDS=0)
        client.__enter__()
    try:
        watch = client.app.state.migration_watch
        mark_applied()
        assert asyncio.run(watch.look()) is None
    finally:
        client.__exit__(None, None, None)

    with running(MIGRATION_WATCH_SECONDS=0) as client:
        watch = client.app.state.migration_watch
        migration_backend.APPLIED.clear()
        assert "checkapp.0001_initial taken back" in asyncio.run(watch.look())


def test_the_watch_looks_by_itself_and_not_when_the_check_is_off(project):
    import time

    Settings(INSTALLED_APPS=["checkapp"])
    create_app()
    write_migrations()
    mark_applied()
    with running(MIGRATION_WATCH_SECONDS=0.05) as client:
        assert client.get("/api/Person").status_code != 503
        apply_one_the_server_does_not_have()
        deadline = time.monotonic() + 5
        while client.get("/api/Person").status_code != 503:
            assert time.monotonic() < deadline, "the watch did not look"
            time.sleep(0.05)

    migration_backend.APPLIED.pop(("checkapp", "0002_later"))
    with running("off") as client:
        assert client.app.state.migration_watch is None
        apply_one_the_server_does_not_have()
        assert client.get("/api/Person").status_code != 503
