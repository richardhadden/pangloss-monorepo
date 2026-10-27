"""`Document.search` and `Entity.search` as a request to `/api/search`"""

from types import SimpleNamespace

from pangloss_models import initialise
from pangloss_models.model_bases.document import Document
from pangloss_models.search import Match
from pangloss_sdk import protocol
from pangloss_sdk.databases.api_sync import exposed_functions


def models():
    class Letter(Document):
        title: str

    initialise()
    return Letter


def test_the_request_is_a_post_of_the_pattern_and_the_page():
    models()
    match = Match.model_validate(
        {"type": "Letter", "where": {"title": {"in": ["a"], "contains": "b"}}}
    )

    call = protocol.search(match, 2, 5)

    assert (call.method, call.path) == ("POST", "/api/search")
    assert call.json == {
        "type": "Letter",
        "where": {"title": {"in": ["a"], "contains": "b"}},
        "page": 2,
        "page_size": 5,
    }
    assert call.is_read is False


def test_a_page_not_asked_for_is_left_to_the_server():
    models()

    call = protocol.search(Match(type="Letter"))

    assert call.json == {"type": "Letter"}


def test_the_class_called_on_is_the_type_when_the_pattern_has_none(monkeypatch):
    Letter = models()
    sent = []

    class Client:
        def send(self, call):
            sent.append(call)
            return SimpleNamespace(
                status_code=200,
                is_success=True,
                json=lambda: {
                    "results": [],
                    "count": 0,
                    "page": 1,
                    "pageSize": 25,
                    "nextPage": None,
                    "previousPage": None,
                },
            )

    monkeypatch.setattr(exposed_functions, "current_client", lambda: Client())

    found = exposed_functions.search(
        Letter, Match.model_validate({"where": {"title": {"eq": "x"}}})
    )

    assert sent[0].json["type"] == "Letter"
    assert found.count == 0


def test_a_504_that_names_the_error_is_a_search_timeout():
    from pangloss_models.exceptions import PanglossSearchTimeoutError

    response = SimpleNamespace(
        status_code=504,
        is_success=False,
        json=lambda: {"detail": "too long", "error": "PanglossSearchTimeoutError"},
    )

    assert isinstance(protocol.error_for(response), PanglossSearchTimeoutError)
    # (and another server error is still one)
    other = SimpleNamespace(
        status_code=502, is_success=False, json=lambda: {}, text="bad gateway"
    )
    assert type(protocol.error_for(other)).__name__ == "PanglossServerError"
