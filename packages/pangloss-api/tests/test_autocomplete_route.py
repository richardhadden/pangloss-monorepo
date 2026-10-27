"""`/api/autocomplete`"""

from uuid import uuid7

from conftest import PASSWORD  # noqa: F401
from fastapi.testclient import TestClient
from pangloss_api.app import create_app
from pangloss_models.autocomplete import AutocompleteItem, AutocompleteResults
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from test_model_routes import stub


def make_models():
    class Person(Entity):
        pass

    class Poet(Person):
        pass

    class Place(Entity):
        pass

    class Note(Document):
        pass

    return Person, Poet, Place, Note


def page(*labels, count=None):
    return AutocompleteResults(
        results=[
            AutocompleteItem(id=uuid7(), type="Person", label=label) for label in labels
        ],
        count=len(labels) if count is None else count,
        page=1,
        page_size=10,
        next_page=None,
        previous_page=None,
    )


def test_it_passes_the_words_the_types_and_the_page_to_the_database(
    settings, monkeypatch
):
    Person, Poet, Place, Note = make_models()
    client = TestClient(create_app())
    seen = {}

    async def autocomplete(
        cls, search_terms, types=None, page_number=None, page_size=None
    ):
        seen.update(
            cls=cls, q=search_terms, types=types, page=page_number, size=page_size
        )
        return page("John Smith", count=21)

    stub(monkeypatch, Entity, "autocomplete", autocomplete)

    response = client.get(
        "/api/autocomplete",
        params={"q": "smi", "type": ["Person", "Place"], "page": 2, "page_size": 5},
    )

    assert response.status_code == 200, response.text
    assert seen == {
        "cls": Entity,
        "q": "smi",
        "types": [Person, Place],
        "page": 2,
        "size": 5,
    }
    body = response.json()
    assert body["count"] == 21
    assert [(i["type"], i["label"]) for i in body["results"]] == [
        ("Person", "John Smith")
    ]


def test_it_needs_no_login(settings, monkeypatch):
    make_models()
    client = TestClient(create_app())

    async def autocomplete(cls, search_terms, types=None, **more):
        return page()

    stub(monkeypatch, Entity, "autocomplete", autocomplete)

    response = client.get("/api/autocomplete", params={"q": "a", "type": "Person"})

    assert response.status_code == 200


def test_the_page_defaults_to_ten_items_of_the_first_page(settings, monkeypatch):
    make_models()
    client = TestClient(create_app())
    seen = {}

    async def autocomplete(
        cls, search_terms, types=None, page_number=None, page_size=None
    ):
        seen.update(page=page_number, size=page_size)
        return page()

    stub(monkeypatch, Entity, "autocomplete", autocomplete)

    client.get("/api/autocomplete", params={"q": "a", "type": "Person"})

    assert seen == {"page": 1, "size": 10}


def test_it_is_refused_without_text_or_type_or_with_too_big_a_page(settings):
    make_models()
    client = TestClient(create_app())

    for params in (
        {"type": "Person"},
        {"q": "", "type": "Person"},
        {"q": "a"},
        {"q": "a", "type": "Person", "page": 0},
        {"q": "a", "type": "Person", "page_size": 51},
    ):
        assert client.get("/api/autocomplete", params=params).status_code == 422, params


def test_a_type_that_is_not_an_entity_is_refused_and_named(settings):
    make_models()
    client = TestClient(create_app())

    for name in ("Note", "Nothing"):
        response = client.get(
            "/api/autocomplete", params={"q": "a", "type": ["Person", name]}
        )
        assert response.status_code == 422
        assert name in response.json()["detail"]


def test_a_model_cannot_take_the_path(settings):
    import pytest
    from pangloss_models.exceptions import PanglossInitialisationError

    class Autocomplete(Entity):
        pass

    with pytest.raises(PanglossInitialisationError, match="Autocomplete"):
        create_app()
