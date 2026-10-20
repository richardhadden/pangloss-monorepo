"""Routes made from the models, with the database functions replaced"""

import asyncio
import datetime
from uuid import uuid7

import pytest
from conftest import PASSWORD
from pangloss_api.app import create_app
from pangloss_models.exceptions import (
    PanglossConflictError,
    PanglossEntityInUseError,
    PanglossNotDeletableError,
    PanglossNotDeletedError,
    PanglossNotFoundError,
    PanglossReferenceError,
    PanglossWriteError,
)
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from pangloss_users import service

META = {
    "created_by": "john",
    "created_when": datetime.datetime(2020, 1, 1),
    "updated_by": None,
    "updated_when": None,
}


def make_models():
    class Place(Entity):
        pass

    class Person(Entity):
        born_in: Place

    class Statement(Document):
        text: str
        about: Person

    return Place, Person, Statement


def login(client, username="john") -> dict:
    asyncio.run(service.create_user(username, f"{username}@example.com", PASSWORD))
    token = client.post(
        "/api/users/token", data={"username": username, "password": PASSWORD}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def stub(monkeypatch, model, name, function):
    """Replace a function the backend binds to a model (as a class method)"""
    monkeypatch.setattr(model, name, classmethod(function))


# ---------------------------------------------------------------------------
# Which routes there are
# ---------------------------------------------------------------------------


def test_routes_are_made_for_concrete_documents_and_entities(settings):
    class Person(Entity):
        pass

    class Poet(Person):
        pass

    class Base(Document):
        _meta = Document.Meta(abstract=True)

    class Statement(Base):
        pass

    from fastapi.testclient import TestClient

    client = TestClient(create_app())
    paths = set(client.get("/openapi.json").json()["paths"])

    for kind, name in (("entities", "Person"), ("entities", "Poet"), ("documents", "Statement")):
        assert f"/api/{kind}/{name}" in paths
        assert f"/api/{kind}/{name}/{{id}}" in paths
        assert f"/api/{kind}/{name}/{{id}}/edit" in paths
        assert f"/api/{kind}/{name}/{{id}}/undelete" in paths
    assert not any("Base" in path for path in paths)
    # (the users' routes are still there)
    assert "/api/users/me" in paths


def test_no_models_no_model_routes(settings):
    from fastapi.testclient import TestClient

    paths = set(TestClient(create_app()).get("/openapi.json").json()["paths"])
    assert all(path.startswith("/api/users") for path in paths)


# ---------------------------------------------------------------------------
# Who can do what
# ---------------------------------------------------------------------------


def test_reading_is_open_and_changing_needs_a_login(settings, monkeypatch):
    from fastapi.testclient import TestClient

    _, Person, Statement = make_models()
    client = TestClient(create_app())

    async def get(cls, id):
        return None

    async def list_(cls, **kwargs):
        raise AssertionError("called")

    some_id = str(uuid7())
    stub(monkeypatch, Person, "get", get)
    stub(monkeypatch, Statement, "get", get)

    # Reading does not ask who you are (the 404 is from the stub)
    assert client.get(f"/api/entities/Person/{some_id}").status_code == 404
    assert client.get(f"/api/documents/Statement/{some_id}").status_code == 404

    # Changing does, and nothing has been called without it
    for method, url, body in (
        ("POST", "/api/entities/Person", {"type": "Person", "label": "x"}),
        ("POST", "/api/documents/Statement", {"type": "Statement", "label": "x"}),
        ("GET", f"/api/entities/Person/{some_id}/edit", None),
        ("GET", f"/api/documents/Statement/{some_id}/edit", None),
        ("PUT", f"/api/entities/Person/{some_id}", {"type": "Person", "id": some_id}),
        ("DELETE", f"/api/entities/Person/{some_id}", None),
        ("POST", f"/api/entities/Person/{some_id}/undelete", None),
        ("DELETE", f"/api/documents/Statement/{some_id}", None),
        ("POST", f"/api/documents/Statement/{some_id}/undelete", None),
    ):
        response = client.request(method, url, json=body)
        assert response.status_code == 401, (method, url)
        assert response.headers["www-authenticate"] == "Bearer"


# ---------------------------------------------------------------------------
# What is passed on
# ---------------------------------------------------------------------------


def test_list_parameters(settings, monkeypatch):
    from fastapi.testclient import TestClient

    _, Person, _ = make_models()
    client = TestClient(create_app())
    seen = []

    async def list_(cls, **kwargs):
        seen.append(kwargs)
        return {
            "results": [],
            "count": 0,
            "page": kwargs["page_number"] or 1,
            "page_size": kwargs["page_size"] or 50,
            "next_page": None,
            "previous_page": None,
        }

    stub(monkeypatch, Person, "list", list_)

    assert client.get("/api/entities/Person").status_code == 200
    assert seen[-1] == {
        "search_terms": None,
        "page_number": None,
        "page_size": None,
        "deep_search": False,
    }

    response = client.get(
        "/api/entities/Person",
        params={"q": "smith", "deep": "true", "page": 2, "page_size": 10},
    )
    assert response.status_code == 200
    assert seen[-1] == {
        "search_terms": "smith",
        "page_number": 2,
        "page_size": 10,
        "deep_search": True,
    }
    assert response.json()["page"] == 2

    for bad in ({"page": 0}, {"page_size": 0}, {"page_size": 100000}, {"page": "x"}):
        assert client.get("/api/entities/Person", params=bad).status_code == 422


def test_get_returns_the_head_view_in_camel_case(settings, monkeypatch):
    from fastapi.testclient import TestClient

    Place, Person, _ = make_models()
    client = TestClient(create_app())
    place_id, person_id = uuid7(), uuid7()

    async def get(cls, id):
        assert id == person_id
        return Person.HeadView(
            id=person_id,
            label="John",
            meta=META,
            born_in=[{"type": "Place", "id": place_id, "label": "Paris"}],
        )

    stub(monkeypatch, Person, "get", get)
    response = client.get(f"/api/entities/Person/{person_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["bornIn"]["label"] == "Paris"
    assert body["meta"]["createdBy"] == "john"
    assert "born_in" not in body
    assert "created_by" not in body["meta"]

    def keys(value):
        if isinstance(value, dict):
            for key, item in value.items():
                yield key
                yield from keys(item)
        elif isinstance(value, list):
            for item in value:
                yield from keys(item)

    assert not [key for key in keys(body) if "_" in key]


def test_create_passes_detail_and_accepts_either_naming(settings, monkeypatch):
    from fastapi.testclient import TestClient
    from pangloss_models.model_bases.entity import _EntityCreateBase

    Place, Person, _ = make_models()
    client = TestClient(create_app())
    headers = login(client)
    saved = []
    place_id = str(uuid7())

    async def save(self, detail=False):
        saved.append((self, detail))
        return Person.ReferenceView(id=uuid7(), label=self.label)

    monkeypatch.setattr(_EntityCreateBase, "save", save)

    for key in ("born_in", "bornIn"):
        response = client.post(
            "/api/entities/Person",
            json={"type": "Person", "label": "John", key: {"type": "Place", "id": place_id}},
            headers=headers,
        )
        assert response.status_code == 201, response.text
        assert response.json()["label"] == "John"

    assert [detail for _, detail in saved] == [False, False]
    assert str(saved[0][0].born_in.id) == place_id

    # (what is not valid never gets to the database)
    for body in (
        {"type": "Person"},
        {"type": "Person", "label": "x", "born_in": {"type": "Person", "id": place_id}},
        {"type": "Statement", "label": "x"},
    ):
        response = client.post("/api/entities/Person", json=body, headers=headers)
        assert response.status_code == 422
    assert len(saved) == 2


def test_update_needs_the_same_id_in_the_path_and_the_body(settings, monkeypatch):
    from fastapi.testclient import TestClient
    from pangloss_models.model_bases.entity import _EntityUpdateBase

    _, Person, _ = make_models()
    client = TestClient(create_app())
    headers = login(client)
    saved = []

    async def save(self, detail=False):
        saved.append((self.id, detail))
        return Person.ReferenceView(id=self.id, label=self.label)

    monkeypatch.setattr(_EntityUpdateBase, "save", save)

    person_id = uuid7()
    body = {
        "type": "Person",
        "id": str(person_id),
        "label": "John",
        "bornIn": {"type": "Place", "id": str(uuid7())},
    }

    response = client.put(
        f"/api/entities/Person/{person_id}", json=body, headers=headers, params={"detail": "true"}
    )
    assert response.status_code == 200, response.text
    assert saved == [(person_id, True)]

    response = client.put(f"/api/entities/Person/{uuid7()}", json=body, headers=headers)
    assert response.status_code == 400
    assert len(saved) == 1


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (PanglossNotFoundError("gone"), 404),
        (PanglossConflictError("clash"), 409),
        (PanglossNotDeletedError("not deleted"), 409),
        (PanglossReferenceError("no such entity"), 422),
        (PanglossNotDeletableError("nested"), 400),
        (PanglossWriteError("rejected"), 400),
    ],
)
def test_errors_from_the_database_become_statuses(settings, monkeypatch, error, status_code):
    from fastapi.testclient import TestClient

    _, Person, _ = make_models()
    client = TestClient(create_app())
    headers = login(client)

    async def delete(cls, id):
        raise error

    stub(monkeypatch, Person, "delete", delete)
    response = client.delete(f"/api/entities/Person/{uuid7()}", headers=headers)
    assert response.status_code == status_code
    assert response.json() == {"detail": str(error)}


def test_an_entity_in_use_says_what_refers_to_it(settings, monkeypatch):
    from fastapi.testclient import TestClient

    _, Person, _ = make_models()
    client = TestClient(create_app())
    headers = login(client)
    referrer = uuid7()

    async def delete(cls, id):
        raise PanglossEntityInUseError(
            "in use",
            entity_id=id,
            referenced_by=[{"id": referrer, "type": "Statement", "label": "S"}],
        )

    stub(monkeypatch, Person, "delete", delete)
    response = client.delete(f"/api/entities/Person/{uuid7()}", headers=headers)
    assert response.status_code == 409
    assert response.json() == {
        "detail": "in use",
        "referencedBy": [{"id": str(referrer), "type": "Statement", "label": "S"}],
    }


def test_delete_and_undelete_give_no_content(settings, monkeypatch):
    from fastapi.testclient import TestClient

    _, _, Statement = make_models()
    client = TestClient(create_app())
    headers = login(client)
    calls = []

    async def delete(cls, id):
        calls.append(("delete", id))

    async def undelete(cls, id):
        calls.append(("undelete", id))

    stub(monkeypatch, Statement, "delete", delete)
    stub(monkeypatch, Statement, "undelete", undelete)

    document_id = uuid7()
    response = client.delete(f"/api/documents/Statement/{document_id}", headers=headers)
    assert response.status_code == 204
    assert response.content == b""
    response = client.post(f"/api/documents/Statement/{document_id}/undelete", headers=headers)
    assert response.status_code == 204
    assert calls == [("delete", document_id), ("undelete", document_id)]


def test_a_synchronous_backend_works_too(settings, monkeypatch):
    """(the database functions of the SDK stubs are not async)"""
    from fastapi.testclient import TestClient

    _, Person, _ = make_models()
    client = TestClient(create_app())
    headers = login(client)
    deleted = []

    def delete(cls, id):
        deleted.append(id)

    stub(monkeypatch, Person, "delete", delete)
    person_id = uuid7()
    response = client.delete(f"/api/entities/Person/{person_id}", headers=headers)
    assert response.status_code == 204
    assert deleted == [person_id]
