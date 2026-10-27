"""`POST /api/search`"""

from conftest import PASSWORD  # noqa: F401
from fastapi.testclient import TestClient
from pangloss_api.app import create_app
from pangloss_models.exceptions import PanglossSearchError
from pangloss_models.model_bases.base_models import _ListItems
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from test_model_routes import stub


def make_models():
    class Person(Entity):
        pass

    class Letter(Document):
        title: str

    return Person, Letter


def empty():
    return _ListItems(
        results=[], count=0, page=1, page_size=25, next_page=None, previous_page=None
    )


def test_it_passes_the_pattern_and_the_page_to_the_model_searched(
    settings, monkeypatch
):
    Person, Letter = make_models()
    client = TestClient(create_app())
    seen = {}

    async def search(cls, match, page_number=None, page_size=None):
        seen.update(cls=cls, match=match, page=page_number, size=page_size)
        return empty()

    stub(monkeypatch, Document, "search", search)

    response = client.post(
        "/api/search",
        json={
            "type": "Letter",
            "where": {"title": {"contains": "x"}, "pages": {"in": [1]}},
            "page": 2,
            "page_size": 5,
        },
    )

    assert response.status_code == 200, response.text
    assert seen["cls"] is Letter and (seen["page"], seen["size"]) == (2, 5)
    assert seen["match"].type == "Letter"
    assert seen["match"].where["title"].contains == "x"
    assert response.json()["count"] == 0


def test_it_searches_entities_too_and_needs_no_login(settings, monkeypatch):
    Person, Letter = make_models()
    client = TestClient(create_app())
    seen = {}

    async def search(cls, match, **more):
        seen["cls"] = cls
        return empty()

    stub(monkeypatch, Entity, "search", search)

    assert client.post("/api/search", json={"type": "Person"}).status_code == 200
    assert seen["cls"] is Person


def test_a_pattern_that_cannot_be_made_is_a_422_with_the_reason(settings, monkeypatch):
    make_models()
    client = TestClient(create_app())

    async def search(cls, match, **more):
        raise PanglossSearchError("title.gt: not an operator for this field")

    stub(monkeypatch, Document, "search", search)

    response = client.post("/api/search", json={"type": "Letter", "where": {}})

    assert response.status_code == 422
    assert "title.gt" in response.text


def test_it_is_refused_without_a_type_or_for_one_that_cannot_be_searched(settings):
    make_models()
    client = TestClient(create_app())

    for body in (
        {},
        {"type": "Nothing"},
        {"type": "Letter", "page": 0},
        {"type": "Letter", "page_size": 101},
        {"type": "Letter", "where": {"title": {"matches": "x"}}},
        {"type": "Letter", "extra": 1},
    ):
        assert client.post("/api/search", json=body).status_code == 422, body


def test_a_model_cannot_be_called_search(settings):
    from pangloss_models.model_bases.document import Document as Doc

    class Search(Doc):
        pass

    try:
        create_app()
    except Exception as error:
        assert "Search" in str(error)
    else:  # pragma: no cover
        raise AssertionError("a model called Search was accepted")


def test_nested_patterns_and_combinators_reach_the_database_as_they_were_sent(
    settings, monkeypatch
):
    make_models()
    client = TestClient(create_app())
    seen = {}

    async def search(cls, match, **more):
        seen["match"] = match
        return empty()

    stub(monkeypatch, Document, "search", search)

    response = client.post(
        "/api/search",
        json={
            "type": "Letter",
            "where": {
                "sender": {"type": "Person", "where": {"label": {"eq": "x"}}},
                "$not": {"title": {"eq": "y"}},
            },
        },
    )

    assert response.status_code == 200, response.text
    where = seen["match"].where
    assert where["sender"].where["label"].eq == "x"
    assert where["$not"]["title"].eq == "y"


def test_a_search_that_took_too_long_is_a_504_that_names_the_error(
    settings, monkeypatch
):
    from pangloss_models.exceptions import PanglossSearchTimeoutError

    make_models()
    client = TestClient(create_app())

    async def search(cls, match, **more):
        raise PanglossSearchTimeoutError("The search took too long")

    stub(monkeypatch, Document, "search", search)

    response = client.post("/api/search", json={"type": "Letter"})

    assert response.status_code == 504
    assert response.json()["error"] == "PanglossSearchTimeoutError"
