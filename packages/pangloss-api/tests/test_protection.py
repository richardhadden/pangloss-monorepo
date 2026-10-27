"""Fields that something other than a person keeps up to date (`pangloss_models.protection`)"""

from types import SimpleNamespace
from uuid import uuid7

from fastapi.testclient import TestClient
from pangloss_api.app import create_app
from pangloss_models.model_bases.entity import Entity, _EntityUpdateBase
from pangloss_models.protection import Protection, protection_of
from test_model_routes import login, stub


def make_models():
    class Source(Entity):
        _protect_meta = Protection(read_only=("citation",), delete_only_if="gone")

        citation: str | None = None
        gone: bool | None = None
        notes: str | None = None

    class Letter(Source):
        _protect_meta = Protection(read_only=("shelfmark",))

        shelfmark: str | None = None

    return Source, Letter


def test_a_subclass_adds_to_the_protection_of_its_parents():
    Source, Letter = make_models()
    assert protection_of(Source) == Protection(("citation",), "gone")
    assert protection_of(Letter) == Protection(("shelfmark", "citation"), "gone")


def test_a_protected_field_cannot_be_set_when_creating(settings, monkeypatch):
    make_models()
    client = TestClient(create_app())
    headers = login(client)
    saved = []

    async def save(self, detail=False):
        saved.append(self)
        return type(self).__mro__[0]

    from pangloss_models.model_bases.entity import _EntityCreateBase

    monkeypatch.setattr(_EntityCreateBase, "save", save)

    response = client.post(
        "/api/Source",
        json={"type": "Source", "label": "x", "citation": "Smith"},
        headers=headers,
    )
    assert response.status_code == 403
    assert "citation" in response.json()["detail"]
    assert saved == []

    # (not set: allowed)
    client.post(
        "/api/Source",
        json={"type": "Source", "label": "x", "notes": "n"},
        headers=headers,
    )
    assert len(saved) == 1


def test_an_update_may_not_change_a_protected_field_but_may_change_the_rest(
    settings, monkeypatch
):
    make_models()
    client = TestClient(create_app())
    headers = {**login(client), "If-Match": "*"}
    saved = []
    Source = __import__(
        "pangloss_models.model_registry", fromlist=["x"]
    ).ModelRegistry.all_models()["Source"]

    async def get_for_edit(cls, id):
        return SimpleNamespace(citation="Smith 1999", meta=SimpleNamespace(version=1))

    async def save(self, detail=False, expected_version=None):
        saved.append(self.notes)
        return Source.ReferenceView(id=self.id, label=self.label)

    stub(monkeypatch, Source, "get_for_edit", get_for_edit)
    monkeypatch.setattr(_EntityUpdateBase, "save", save)

    source_id = uuid7()
    url = f"/api/Source/{source_id}"
    body = {
        "type": "Source",
        "id": str(source_id),
        "label": "x",
        "citation": "Smith 1999",
        "notes": "mine",
    }

    assert client.put(url, json=body, headers=headers).status_code == 200
    assert saved == ["mine"]

    response = client.put(url, json={**body, "citation": "Changed"}, headers=headers)
    assert response.status_code == 403
    assert "citation" in response.json()["detail"]
    response = client.put(
        url, json={k: v for k, v in body.items() if k != "citation"}, headers=headers
    )
    assert response.status_code == 403  # (leaving it out would clear it)
    assert saved == ["mine"]


def test_an_entity_is_deleted_only_when_its_field_says_so(settings, monkeypatch):
    make_models()
    client = TestClient(create_app())
    headers = login(client)
    Source = __import__(
        "pangloss_models.model_registry", fromlist=["x"]
    ).ModelRegistry.all_models()["Source"]
    deleted = []
    state = {"gone": False}

    async def get(cls, id):
        return SimpleNamespace(gone=state["gone"])

    async def delete(cls, id):
        deleted.append(id)

    stub(monkeypatch, Source, "get", get)
    stub(monkeypatch, Source, "delete", delete)

    source_id = uuid7()
    response = client.delete(f"/api/Source/{source_id}", headers=headers)
    assert response.status_code == 403
    assert "gone" in response.json()["detail"]
    assert deleted == []

    state["gone"] = True
    assert client.delete(f"/api/Source/{source_id}", headers=headers).status_code == 204
    assert deleted == [source_id]
