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

    # (no matter whether they are entities or documents; an entity is found by its
    # id or a URL)
    for name, item in (("Person", "ref"), ("Poet", "ref"), ("Statement", "id")):
        assert f"/api/{name}" in paths
        assert f"/api/{name}/{{{item}}}" in paths
        assert f"/api/{name}/{{{item}}}/edit" in paths
        assert f"/api/{name}/{{{item}}}/undelete" in paths
    assert not any("Base" in path for path in paths)

    # The kind of the model is not in the path
    assert client.get("/api/entities/Person").status_code in (404, 422)
    assert client.get("/api/documents/Statement").status_code in (404, 422)
    # (the users' routes are still there)
    assert "/api/users/me" in paths


def test_no_models_no_model_routes(settings):
    from fastapi.testclient import TestClient

    paths = set(TestClient(create_app()).get("/openapi.json").json()["paths"])
    assert all(path.startswith(("/api/users", "/api/autocomplete", "/api/search")) for path in paths)


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
    assert client.get(f"/api/Person/{some_id}").status_code == 404
    assert client.get(f"/api/Statement/{some_id}").status_code == 404

    # Changing does, and nothing has been called without it
    for method, url, body in (
        ("POST", "/api/Person", {"type": "Person", "label": "x"}),
        ("POST", "/api/Statement", {"type": "Statement", "label": "x"}),
        ("GET", f"/api/Person/{some_id}/edit", None),
        ("GET", f"/api/Statement/{some_id}/edit", None),
        ("PUT", f"/api/Person/{some_id}", {"type": "Person", "id": some_id}),
        ("DELETE", f"/api/Person/{some_id}", None),
        ("POST", f"/api/Person/{some_id}/undelete", None),
        ("DELETE", f"/api/Statement/{some_id}", None),
        ("POST", f"/api/Statement/{some_id}/undelete", None),
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

    assert client.get("/api/Person").status_code == 200
    assert seen[-1] == {
        "search_terms": None,
        "page_number": None,
        "page_size": None,
        "deep_search": False,
    }

    response = client.get(
        "/api/Person",
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
        assert client.get("/api/Person", params=bad).status_code == 422


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
    response = client.get(f"/api/Person/{person_id}")
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
            "/api/Person",
            json={
                "type": "Person",
                "label": "John",
                key: {"type": "Place", "id": place_id},
            },
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
        response = client.post("/api/Person", json=body, headers=headers)
        assert response.status_code == 422
    assert len(saved) == 2


def test_update_needs_the_same_id_in_the_path_and_the_body(settings, monkeypatch):
    from fastapi.testclient import TestClient
    from pangloss_models.model_bases.entity import _EntityUpdateBase

    _, Person, _ = make_models()
    client = TestClient(create_app())
    headers = login(client)
    saved = []

    async def save(self, detail=False, expected_version=None):
        saved.append((self.id, detail, expected_version))
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
        f"/api/Person/{person_id}",
        json=body,
        headers={**headers, "If-Match": '"2"'},
    )
    assert response.status_code == 200, response.text
    assert saved == [(person_id, False, 2)]

    response = client.put(
        f"/api/Person/{uuid7()}", json=body, headers={**headers, "If-Match": '"2"'}
    )
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
def test_errors_from_the_database_become_statuses(
    settings, monkeypatch, error, status_code
):
    from fastapi.testclient import TestClient

    _, Person, _ = make_models()
    client = TestClient(create_app())
    headers = login(client)

    async def delete(cls, id):
        raise error

    stub(monkeypatch, Person, "delete", delete)
    response = client.delete(f"/api/Person/{uuid7()}", headers=headers)
    assert response.status_code == status_code
    assert response.json() == {"detail": str(error), "error": type(error).__name__}


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
    response = client.delete(f"/api/Person/{uuid7()}", headers=headers)
    assert response.status_code == 409
    assert response.json() == {
        "detail": "in use",
        "error": "PanglossEntityInUseError",
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
    response = client.delete(f"/api/Statement/{document_id}", headers=headers)
    assert response.status_code == 204
    assert response.content == b""
    response = client.post(f"/api/Statement/{document_id}/undelete", headers=headers)
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
    response = client.delete(f"/api/Person/{person_id}", headers=headers)
    assert response.status_code == 204
    assert deleted == [person_id]


def test_entities_are_found_by_url_as_well_as_by_id(settings, monkeypatch):
    from fastapi.testclient import TestClient

    Place, Person, Statement = make_models()
    client = TestClient(create_app())
    headers = login(client)
    person_id, place_id = uuid7(), uuid7()
    url = "http://example.com/people/john"
    asked = []

    def head_view():
        return Person.HeadView(
            id=person_id,
            label="John",
            meta=META,
            born_in=[{"type": "Place", "id": place_id, "label": "Paris"}],
        )

    async def get(cls, id):
        asked.append(("get", id))
        return head_view() if str(id) in (url, str(person_id)) else None

    async def get_for_edit(cls, id):
        asked.append(("edit", id))
        return Person.EditView(
            id=person_id,
            label="John",
            meta=META,
            born_in=[{"type": "Place", "id": place_id, "label": "Paris"}],
        )

    async def delete(cls, id):
        asked.append(("delete", id))

    async def undelete(cls, id):
        asked.append(("undelete", id))

    stub(monkeypatch, Person, "get", get)
    stub(monkeypatch, Person, "get_for_edit", get_for_edit)
    stub(monkeypatch, Person, "delete", delete)
    stub(monkeypatch, Person, "undelete", undelete)

    # By the URL, as it is: no login, as for reading by id
    response = client.get(f"/api/Person/{url}")
    assert response.status_code == 200, response.text
    assert response.json()["id"] == str(person_id)
    assert response.json()["bornIn"]["label"] == "Paris"
    # (what is passed on is a URL, which is what tells the database not to use an id)
    kind, passed = asked[-1]
    assert str(passed) == url
    assert not isinstance(passed, str | type(person_id))

    # By the id, as before
    assert client.get(f"/api/Person/{person_id}").status_code == 200
    assert asked[-1] == ("get", person_id)

    # A server may have merged the slashes of "http://"
    assert client.get("/api/Person/http:/example.com/people/john").status_code == 200
    assert str(asked[-1][1]) == url
    assert client.get("/api/Person/HTTP://example.com/people/john").status_code == 200

    # A URL with a query string: it is the URL's
    client.get(f"/api/Person/{url}?id=5&x=y")
    assert str(asked[-1][1]) == f"{url}?id=5&x=y"

    # Not found
    missing = client.get("/api/Person/http://example.com/people/jane")
    assert missing.status_code == 404
    assert "URL http://example.com/people/jane" in missing.json()["detail"]
    assert "with id" in client.get(f"/api/Person/{uuid7()}").json()["detail"]

    # Neither an id nor a URL
    for bad in ("john", "ftp://example.com/john", "http://"):
        assert client.get(f"/api/Person/{bad}").status_code == 422, bad

    # Loading to edit, and changes, are only ever at an id: at a URL they are refused
    # (and nothing is called), at the id they are done
    body = {
        "type": "Person",
        "id": str(person_id),
        "label": "John",
        "bornIn": {"type": "Place", "id": str(place_id)},
    }
    before = len(asked)
    for method, suffix, json in (
        ("GET", "/edit", None),
        ("PUT", "", body),
        ("DELETE", "", None),
        ("POST", "/undelete", None),
    ):
        path = f"/api/Person/{url}{suffix}"
        assert client.request(method, path, json=json).status_code == 401
        response = client.request(method, path, json=json, headers=headers)
        assert response.status_code == 400, (method, suffix)
        assert "at the id of an entity" in response.json()["detail"]
    assert len(asked) == before

    for method, suffix, expected in (
        ("GET", "/edit", "edit"),
        ("DELETE", "", "delete"),
        ("POST", "/undelete", "undelete"),
    ):
        path = f"/api/Person/{person_id}{suffix}"
        response = client.request(method, path, headers=headers)
        assert response.status_code in (200, 204), (method, suffix)
        assert asked[-1] == (expected, person_id)

    # (what is neither is not valid)
    assert client.delete("/api/Person/john", headers=headers).status_code == 422

    # A document is found by its id only
    assert client.get(f"/api/Statement/{url}").status_code == 404
    assert client.get("/api/Statement/not-an-id").status_code == 422


@pytest.mark.parametrize("name", ["users", "Users", "docs", "Docs", "redoc"])
def test_a_model_cannot_have_the_name_of_other_routes(settings, name):
    from pangloss_models.exceptions import PanglossInitialisationError

    type(name, (Entity,), {"__module__": __name__})
    with pytest.raises(PanglossInitialisationError, match="cannot be called"):
        create_app()


# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------


def person_body(person_id):
    return {
        "type": "Person",
        "id": str(person_id),
        "label": "John",
        "bornIn": {"type": "Place", "id": str(uuid7())},
    }


def test_an_update_must_say_which_version_it_is_based_on(settings, monkeypatch):
    from fastapi.testclient import TestClient
    from pangloss_models.model_bases.entity import _EntityUpdateBase

    _, Person, _ = make_models()
    client = TestClient(create_app())
    headers = login(client)
    saved = []

    async def save(self, detail=False, expected_version=None):
        saved.append(expected_version)
        return Person.ReferenceView(id=self.id, label=self.label)

    monkeypatch.setattr(_EntityUpdateBase, "save", save)
    person_id = uuid7()
    url = f"/api/Person/{person_id}"

    # Without it: refused, and nothing is called
    response = client.put(url, json=person_body(person_id), headers=headers)
    assert response.status_code == 428
    assert "If-Match" in response.json()["detail"]
    assert saved == []

    # The ETag of the edit view, in quotes or not
    for header, expected in (('"1"', 1), ('"12"', 12), ("3", 3), (' "4" ', 4)):
        response = client.put(
            url, json=person_body(person_id), headers={**headers, "If-Match": header}
        )
        assert response.status_code == 200, (header, response.text)
        assert saved[-1] == expected

    # `*` updates whatever the version is
    response = client.put(
        url, json=person_body(person_id), headers={**headers, "If-Match": "*"}
    )
    assert response.status_code == 200
    assert saved[-1] is None

    # Not a version
    before = len(saved)
    for header in ('"x"', '"0"', '"-1"', '"1', 'W/"1"', '"1", "2"', ""):
        response = client.put(
            url, json=person_body(person_id), headers={**headers, "If-Match": header}
        )
        assert response.status_code == 400, header
    assert len(saved) == before


def test_etags_are_the_versions(settings, monkeypatch):
    from fastapi.testclient import TestClient
    from pangloss_models.model_bases.entity import _EntityCreateBase, _EntityUpdateBase

    Place, Person, Statement = make_models()
    client = TestClient(create_app())
    headers = login(client)
    person_id = uuid7()

    async def get_for_edit(cls, id):
        return Person.EditView(
            id=person_id,
            label="John",
            meta={**META, "version": 7},
            born_in=[{"type": "Place", "id": uuid7(), "label": "Paris"}],
        )

    async def get_statement(cls, id):
        return Statement.HeadView(
            id=id,
            label="S",
            text="x",
            about=[{"type": "Person", "id": person_id, "label": "John"}],
            meta={**META, "version": 3},
        )

    async def save_new(self, detail=False):
        return Person.ReferenceView(id=person_id, label=self.label)

    async def save_update(self, detail=False, expected_version=None):
        if detail:
            return Person.HeadView(
                id=person_id,
                label=self.label,
                meta={**META, "version": 99},
                born_in=[{"type": "Place", "id": uuid7(), "label": "Paris"}],
            )
        return Person.ReferenceView(id=person_id, label=self.label)

    stub(monkeypatch, Person, "get_for_edit", get_for_edit)
    stub(monkeypatch, Statement, "get", get_statement)
    monkeypatch.setattr(_EntityCreateBase, "save", save_new)
    monkeypatch.setattr(_EntityUpdateBase, "save", save_update)

    # The edit view says the version it has (of an entity, or of a document)
    response = client.get(f"/api/Person/{person_id}/edit", headers=headers)
    assert response.headers["etag"] == '"7"'
    assert response.json()["meta"]["version"] == 7
    response = client.get(f"/api/Statement/{uuid7()}/edit", headers=headers)
    assert response.headers["etag"] == '"3"'

    # A new one is at version 1
    response = client.post(
        "/api/Person",
        json={
            "type": "Person",
            "label": "J",
            "bornIn": {"type": "Place", "id": str(uuid7())},
        },
        headers=headers,
    )
    assert response.status_code == 201
    assert response.headers["etag"] == '"1"'

    # An update gives the version it made, to go on from
    url = f"/api/Person/{person_id}"
    response = client.put(
        url, json=person_body(person_id), headers={**headers, "If-Match": '"7"'}
    )
    assert response.headers["etag"] == '"8"'
    # ... from the whole thing, if that is returned
    response = client.put(
        url,
        json=person_body(person_id),
        params={"detail": "true"},
        headers={**headers, "If-Match": '"7"'},
    )
    assert response.headers["etag"] == '"99"'
    # ... and not known after an update of whatever version it was
    response = client.put(
        url, json=person_body(person_id), headers={**headers, "If-Match": "*"}
    )
    assert response.status_code == 200
    assert "etag" not in response.headers


def test_an_update_of_an_old_version_is_refused_with_the_new_one(settings, monkeypatch):
    from fastapi.testclient import TestClient
    from pangloss_models.exceptions import PanglossVersionConflictError
    from pangloss_models.model_bases.entity import _EntityUpdateBase

    _, Person, _ = make_models()
    client = TestClient(create_app())
    headers = login(client)

    async def save(self, detail=False, expected_version=None):
        raise PanglossVersionConflictError("it has been updated", current_version=5)

    monkeypatch.setattr(_EntityUpdateBase, "save", save)
    person_id = uuid7()
    response = client.put(
        f"/api/Person/{person_id}",
        json=person_body(person_id),
        headers={**headers, "If-Match": '"4"'},
    )
    assert response.status_code == 412
    assert response.json() == {
        "detail": "it has been updated",
        "error": "PanglossVersionConflictError",
        "currentVersion": 5,
    }
    assert response.headers["etag"] == '"5"'
