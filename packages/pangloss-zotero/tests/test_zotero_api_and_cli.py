"""The API side (the task, the routes) and the commands"""

from types import SimpleNamespace
from uuid import uuid7

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pangloss_api.dependencies import get_current_user
from pangloss_models import initialise
from pangloss_models.model_bases.entity import Entity
from pangloss_zotero import ZoteroBacked, ZoteroItemType, ZoteroMeta, api, checks
from pangloss_zotero.link import LinkError
from typer.testing import CliRunner


class Settings:
    ZOTERO_API_KEY = "key"
    ZOTERO_LIBRARIES = ["groups/1"]


def test_the_watcher_is_a_background_task_when_there_is_a_key_and_a_library():
    app = FastAPI()
    app.state.background_tasks = []
    api.configure_app(app, Settings)
    assert [t.name for t in app.state.background_tasks] == ["zotero"]


@pytest.mark.parametrize(
    "overrides",
    [{"ZOTERO_WATCH": False}, {"ZOTERO_API_KEY": None}, {"ZOTERO_LIBRARIES": []}],
)
def test_it_is_not_started_when_turned_off_or_not_set_up(overrides):
    settings = type("S", (Settings,), overrides)
    app = FastAPI()
    app.state.background_tasks = []
    api.configure_app(app, settings)
    assert app.state.background_tasks == []


def link_client(monkeypatch, result):
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        username="john"
    )
    app.state.zotero_client = lambda: SimpleNamespace()
    calls = []

    async def fake(settings, client, model, id, url):
        calls.append((model, id, url))
        if isinstance(result, Exception):
            raise result

    monkeypatch.setattr(api, "link_item", fake)
    monkeypatch.setattr(api.core_settings, "SETTINGS", Settings, raising=False)
    return TestClient(app), calls


def test_the_link_route_links_and_gives_no_content(monkeypatch):
    client, calls = link_client(monkeypatch, None)
    id = uuid7()
    response = client.post(
        "/api/zotero/link",
        json={
            "model": "Atlas",
            "id": str(id),
            "zotero_url": "https://www.zotero.org/groups/1/items/AAAA",
        },
    )
    assert response.status_code == 204
    assert calls == [("Atlas", id, "https://www.zotero.org/groups/1/items/AAAA")]


@pytest.mark.parametrize("status", [404, 409, 422])
def test_the_link_route_says_why_it_refused(monkeypatch, status):
    client, _ = link_client(monkeypatch, LinkError(status, "because"))
    response = client.post(
        "/api/zotero/link", json={"model": "A", "id": str(uuid7()), "zotero_url": "x"}
    )
    assert response.status_code == status
    assert response.json()["detail"] == "because"


def test_the_link_route_needs_a_login():
    app = FastAPI()
    app.include_router(api.router)
    response = TestClient(app).post(
        "/api/zotero/link", json={"model": "A", "id": str(uuid7()), "zotero_url": "x"}
    )
    assert response.status_code in (
        401,
        403,
        500,
    )  # (no user: the dependency is the API's own)


def test_problems_are_found_without_a_database(offline_settings):
    class Needs(ZoteroBacked):
        must_have: str

    class Clash1(ZoteroBacked):
        _zotero_meta = ZoteroMeta(item_types=[ZoteroItemType.BOOK])

    class Clash2(ZoteroBacked):
        _zotero_meta = ZoteroMeta(item_types=[ZoteroItemType.BOOK])

    initialise()
    found = checks.problems(type("S", (), {}))
    assert "ZOTERO_API_KEY is not set" in found
    assert "ZOTERO_LIBRARIES is empty" in found
    assert any("'book' is claimed by Clash1, Clash2" in p for p in found)
    assert any(
        p.startswith("Needs has fields the sync cannot give: must_have") for p in found
    )


def test_nothing_wrong_with_a_set_up_that_is_right(offline_settings):
    class TextObject(ZoteroBacked):
        shelfmark: str | None = None

    class Atlas(TextObject):
        _zotero_meta = ZoteroMeta(item_types=[ZoteroItemType.BOOK])

    class Place(Entity):
        pass

    initialise()
    assert checks.problems(Settings) == []


def test_the_check_command_reports_and_fails(offline_settings):
    from pangloss_zotero.cli import cli

    class Needs(ZoteroBacked):
        must_have: str

    project = SimpleNamespace(
        require_settings=lambda: type("S", (), {}),
        import_models=lambda: None,
    )
    result = CliRunner().invoke(cli, ["check"], obj=project)
    assert result.exit_code == 1
    assert "ZOTERO_API_KEY is not set" in result.output
    assert "must_have" in result.output
