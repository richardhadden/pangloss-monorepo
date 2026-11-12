"""`/api/references`"""

from uuid import uuid7

from conftest import PASSWORD  # noqa: F401
from fastapi.testclient import TestClient
from pangloss_api import create_app
from pangloss_api.routes.references import MAX_REFERENCES
from pangloss_models.autocomplete import AutocompleteItem
from pangloss_models import Entity
from test_model_routes import stub


def test_it_asks_the_database_and_needs_no_login(settings, monkeypatch):
    client = TestClient(create_app())
    there, gone = uuid7(), uuid7()
    seen = {}

    async def references(cls, ids):
        seen.update(cls=cls, ids=ids)
        return [AutocompleteItem(id=there, type="Person", label="John Smith")]

    stub(monkeypatch, Entity, "references", references)

    response = client.post("/api/references", json={"ids": [str(there), str(gone)]})

    assert response.status_code == 200, response.text
    assert seen == {"cls": Entity, "ids": [there, gone]}
    assert response.json() == {
        "found": [
            {
                "id": str(there),
                "type": "Person",
                "label": "John Smith",
                # (only what is offered while typing says by which merged label it was found)
                "mergedLabel": None,
            }
        ]
    }


def test_not_an_id_or_too_many_is_a_422(settings, monkeypatch):
    client = TestClient(create_app())

    async def references(cls, ids):
        raise AssertionError("not asked")

    stub(monkeypatch, Entity, "references", references)

    assert client.post("/api/references", json={"ids": ["x"]}).status_code == 422
    many = [str(uuid7()) for _ in range(MAX_REFERENCES + 1)]
    assert client.post("/api/references", json={"ids": many}).status_code == 422
