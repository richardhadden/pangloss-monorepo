"""Query parameters are read in either case, and one a route does not have is refused"""

from conftest import PASSWORD  # noqa: F401
from fastapi.testclient import TestClient
from pangloss_api import create_app
from pangloss_api.query import in_snake_case, to_snake
from test_model_routes import make_models, stub


def listing(monkeypatch, model):
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

    stub(monkeypatch, model, "list", list_)
    return seen


def test_names_are_put_in_snake_case_and_values_are_left_alone():
    assert to_snake("pageSize") == "page_size"
    assert to_snake("page_size") == "page_size"
    assert to_snake("includeSubtypes2Deep") == "include_subtypes2_deep"
    assert to_snake("q") == "q"

    assert in_snake_case(b"pageSize=10&q=John+Smith") == b"page_size=10&q=John+Smith"
    # (a value is not a name)
    assert in_snake_case(b"q=camelCase%20Word&reviewStatus=errorsFound") == (
        b"q=camelCase+Word&review_status=errorsFound"
    )
    # (nothing to change: the very same bytes, however they are encoded)
    unchanged = b"q=John%20Smith&page_size=10&q=Mc%C3%81dam"
    assert in_snake_case(unchanged) is unchanged
    assert in_snake_case(b"") == b""


def test_a_parameter_is_read_in_either_case(settings, monkeypatch):
    _, Person, _ = make_models()
    client = TestClient(create_app())
    seen = listing(monkeypatch, Person)

    assert client.get("/api/Person?pageSize=10&page=2").status_code == 200
    assert seen[-1]["page_size"] == 10 and seen[-1]["page_number"] == 2
    assert client.get("/api/Person?page_size=20").status_code == 200
    assert seen[-1]["page_size"] == 20
    assert client.get("/api/Person?reviewStatus=unchecked").status_code == 200
    assert seen[-1]["review_status"] == "unchecked"

    # (and its limits apply in either case)
    assert client.get("/api/Person?pageSize=100000").status_code == 422
    assert client.get("/api/autocomplete?q=jo&pageSize=100000").status_code == 422


def test_a_parameter_a_route_does_not_have_is_refused_with_those_it_has(
    settings, monkeypatch
):
    _, Person, _ = make_models()
    client = TestClient(create_app())
    seen = listing(monkeypatch, Person)

    response = client.get("/api/Person?pagesize=10&q=smith&colour=red")
    assert response.status_code == 422
    assert seen == []
    first, second = response.json()["detail"]
    assert first["type"] == "unknown_parameter"
    assert first["loc"] == ["query", "pagesize"]
    assert first["input"] == "10"
    assert "Unknown query parameter 'pagesize'" in first["msg"]
    for name in ("deep", "page", "page_size", "published", "q", "review_status"):
        assert name in first["msg"]
    assert second["loc"] == ["query", "colour"]

    # a route with no parameters says so
    response = client.get("/api/users/me?x=1")
    assert response.status_code == 422
    assert "This route has: none" in response.json()["detail"][0]["msg"]

    # and what is not a route is still not found
    assert client.get("/api/Nothing?x=1").status_code == 404


def test_the_query_of_a_url_that_names_an_entity_is_the_urls(settings, monkeypatch):
    from pangloss_models import PanglossNotFoundError

    _, Person, _ = make_models()
    client = TestClient(create_app())
    asked = []

    async def get(cls, id, **kwargs):
        asked.append(str(id))
        raise PanglossNotFoundError("Person", id)

    stub(monkeypatch, Person, "get", get)

    # (neither renamed nor refused: it is not a parameter of the route)
    url = "http://example.com/people?personId=5&x=y"
    assert client.get(f"/api/Person/{url}").status_code == 404
    assert asked[-1] == url
