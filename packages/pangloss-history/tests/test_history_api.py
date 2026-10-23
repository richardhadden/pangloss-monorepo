from uuid import uuid7

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from history_support import record
from pangloss_api.dependencies import get_current_user
from pangloss_history import api
from pangloss_history.store import SqliteStore


class Statement:
    pass


class Person:
    pass


@pytest.fixture
def client(tmp_path, monkeypatch):
    store = SqliteStore(tmp_path / "h.sqlite3")
    api.set_store(store)
    monkeypatch.setattr(api, "routable_models", lambda: [Statement, Person])
    versions = {"now": 3}

    async def current_version(model, id):
        return versions["now"]

    monkeypatch.setattr(api, "current_version", current_version)

    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_current_user] = lambda: object()
    client = TestClient(app)
    client.store = store
    client.versions = versions
    yield client
    api.set_store(None)


def seed(client):
    id = uuid7()
    client.store.append(
        [
            record(id, 1, content={"text": "one", "parts": [{"id": "a", "n": 1}]}),
            record(id, 3, "update", content={"text": "three", "parts": [{"id": "a", "n": 2}]}),
            record(id, 3, "delete"),
        ]
    )
    return id


def test_the_versions_are_listed_with_the_ones_that_were_not_recorded(client):
    id = seed(client)
    body = client.get(f"/api/Statement/{id}/history").json()
    assert [(v["version"], v["op"]) for v in body["versions"]] == [
        (1, "create"),
        (3, "update"),
        (3, "delete"),
    ]
    assert body["versions"][0]["schemaPosition"] == {"letters": "0001_initial"}
    assert body["currentVersion"] == 3 and body["missing"] == [2]


def test_a_version_is_given_as_it_was_written(client):
    id = seed(client)
    body = client.get(f"/api/Statement/{id}/history/1").json()
    assert body["content"]["text"] == "one" and body["op"] == "create"


def test_the_difference_between_two_versions(client):
    id = seed(client)
    body = client.get(f"/api/Statement/{id}/history/1/diff", params={"to": 3}).json()
    assert body["changes"] == [
        {"path": "parts[a].n", "kind": "changed", "old": 1, "new": 2},
        {"path": "text", "kind": "changed", "old": "one", "new": "three"},
    ]
    # (to the latest, if `to` is not given)
    assert client.get(f"/api/Statement/{id}/history/1/diff").json()["to"] == 3


def test_what_is_not_there_is_not_found(client):
    id = seed(client)
    assert client.get(f"/api/Nothing/{id}/history").status_code == 404
    assert client.get(f"/api/Statement/{uuid7()}/history").status_code == 404
    assert client.get(f"/api/Person/{id}/history").status_code == 404  # (it is a Statement)
    assert client.get(f"/api/Statement/{id}/history/2").status_code == 404
    assert client.get(f"/api/Statement/{id}/history/1/diff?to=2").status_code == 404


def test_a_node_that_is_not_in_the_graph_still_has_its_history(client):
    id = seed(client)

    async def gone(model, id):
        return None

    api.current_version = gone
    body = client.get(f"/api/Statement/{id}/history").json()
    assert body["currentVersion"] is None and body["missing"] == []


def test_it_needs_a_logged_in_user(client):
    client.app.dependency_overrides.clear()
    assert client.get(f"/api/Statement/{seed(client)}/history").status_code == 401
