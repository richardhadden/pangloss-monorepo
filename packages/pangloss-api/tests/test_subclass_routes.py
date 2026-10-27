"""A class's routes with an item that is a subclass: read as the subclass, edited at the subclass's route"""

from uuid import uuid7

from conftest import PASSWORD  # noqa: F401
from fastapi.testclient import TestClient
from pangloss_api.app import create_app
from pangloss_models.model_bases.entity import Entity, _EntityUpdateBase
from test_model_routes import META, login, stub


def make_models():
    class Base(Entity):
        pass

    class Sub(Base):
        extra: str | None = None

    return Base, Sub


def test_get_by_the_parent_gives_the_view_of_the_subclass_and_says_where_it_is(
    settings, monkeypatch
):
    Base, Sub = make_models()
    client = TestClient(create_app())
    item_id = uuid7()

    async def get(cls, id):
        return Sub.HeadView(
            type="Sub",
            id=item_id,
            label="s",
            extra="x",
            urls=[],
            meta={
                **META,
                "version": 1,
                "head_node_id": item_id,
                "head_node_type": "Sub",
            },
        )

    stub(monkeypatch, Base, "get", get)

    response = client.get(f"/api/Base/{item_id}")

    assert response.status_code == 200, response.text
    assert response.json()["type"] == "Sub"
    assert response.json()["extra"] == "x"
    assert response.headers["Content-Location"] == f"/api/Sub/{item_id}"


def test_get_by_the_class_itself_has_no_content_location(settings, monkeypatch):
    Base, Sub = make_models()
    client = TestClient(create_app())
    item_id = uuid7()

    async def get(cls, id):
        return Base.HeadView(
            type="Base",
            id=item_id,
            label="b",
            urls=[],
            meta={
                **META,
                "version": 1,
                "head_node_id": item_id,
                "head_node_type": "Base",
            },
        )

    stub(monkeypatch, Base, "get", get)

    response = client.get(f"/api/Base/{item_id}")

    assert response.status_code == 200
    assert "Content-Location" not in response.headers


def test_edit_by_the_parent_redirects_to_the_subclass(settings, monkeypatch):
    Base, Sub = make_models()
    client = TestClient(create_app())
    headers = login(client)
    item_id = uuid7()

    async def get_for_edit(cls, id):
        return Sub.EditView(
            type="Sub",
            id=item_id,
            label="s",
            extra="x",
            urls=[],
            meta={
                **META,
                "version": 4,
                "head_node_id": item_id,
                "head_node_type": "Sub",
            },
        )

    stub(monkeypatch, Base, "get_for_edit", get_for_edit)

    response = client.get(
        f"/api/Base/{item_id}/edit", headers=headers, follow_redirects=False
    )

    assert response.status_code == 308
    assert response.headers["location"] == f"/api/Sub/{item_id}/edit"


def test_updating_a_subclass_item_as_its_parent_is_refused(settings, monkeypatch):
    Base, Sub = make_models()
    client = TestClient(create_app())
    headers = {**login(client), "If-Match": "*"}
    item_id = uuid7()
    saved = []

    async def get_for_edit(cls, id):
        return Sub.EditView(
            type="Sub",
            id=item_id,
            label="s",
            urls=[],
            meta={
                **META,
                "version": 1,
                "head_node_id": item_id,
                "head_node_type": "Sub",
            },
        )

    async def save(self, detail=False, expected_version=None):
        saved.append(self)

    stub(monkeypatch, Base, "get_for_edit", get_for_edit)
    monkeypatch.setattr(_EntityUpdateBase, "save", save)

    response = client.put(
        f"/api/Base/{item_id}",
        json={"type": "Base", "id": str(item_id), "label": "x"},
        headers=headers,
    )

    assert response.status_code == 409
    assert f"/api/Sub/{item_id}" in response.json()["detail"]
    assert saved == []


def test_a_class_without_subclasses_is_updated_without_the_extra_read(
    settings, monkeypatch
):
    class Plain(Entity):
        pass

    client = TestClient(create_app())
    headers = {**login(client), "If-Match": "*"}
    item_id = uuid7()
    reads = []

    async def get_for_edit(cls, id):
        reads.append(id)

    async def save(self, detail=False, expected_version=None):
        return Plain.ReferenceView(id=self.id, label=self.label)

    stub(monkeypatch, Plain, "get_for_edit", get_for_edit)
    monkeypatch.setattr(_EntityUpdateBase, "save", save)

    response = client.put(
        f"/api/Plain/{item_id}",
        json={"type": "Plain", "id": str(item_id), "label": "x"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert reads == []
