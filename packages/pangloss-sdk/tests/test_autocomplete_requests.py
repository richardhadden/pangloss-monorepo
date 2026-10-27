"""`Entity.autocomplete` as a request to `/api/autocomplete`"""

from types import SimpleNamespace
from uuid import uuid7

import pytest
from pangloss_models import initialise
from pangloss_models.model_bases.entity import Entity
from pangloss_sdk import protocol
from pangloss_sdk.databases.api_sync import exposed_functions


def models():
    class Person(Entity):
        pass

    class Place(Entity):
        pass

    initialise()
    return Person, Place


def test_the_request_names_the_types_and_the_page():
    Person, Place = models()

    call = protocol.autocomplete("smi", [Person, Place], 2, 5)

    assert (call.method, call.path) == ("GET", "/api/autocomplete")
    assert call.params == {
        "q": "smi",
        "type": ["Person", "Place"],
        "page": 2,
        "page_size": 5,
    }
    assert call.needs_login is False


def test_a_page_not_asked_for_is_left_to_the_server():
    Person, Place = models()

    assert protocol.autocomplete("a", [Person]).params == {"q": "a", "type": ["Person"]}


def test_the_answer_is_read_as_a_page_of_items():
    id_ = uuid7()
    payload = {
        "results": [{"id": str(id_), "type": "Person", "label": "John Smith"}],
        "count": 1,
        "page": 1,
        "pageSize": 10,
        "nextPage": None,
        "previousPage": None,
    }
    response = SimpleNamespace(status_code=200, is_success=True, json=lambda: payload)

    found = protocol.autocompleted(response)

    assert [(i.id, i.type, i.label) for i in found.results] == [
        (id_, "Person", "John Smith")
    ]
    assert found.count == 1


def test_the_class_it_is_called_on_is_the_type_when_none_is_given(monkeypatch):
    Person, Place = models()
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
                    "pageSize": 10,
                    "nextPage": None,
                    "previousPage": None,
                },
            )

    monkeypatch.setattr(exposed_functions, "current_client", lambda: Client())

    exposed_functions.autocomplete(Person, "a")

    assert sent[0].params["type"] == ["Person"]


@pytest.mark.parametrize("module", ["api", "api_sync"])
def test_both_flavours_of_the_sdk_have_it(module):
    import importlib

    functions = importlib.import_module(
        f"pangloss_sdk.databases.{module}.exposed_functions"
    )

    assert callable(functions.autocomplete)
