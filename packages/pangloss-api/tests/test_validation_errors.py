"""What a 422 says: the path in what was sent, what it was read as, and not the input again if it is long"""

import json

from conftest import PASSWORD  # noqa: F401
from fastapi.testclient import TestClient
from pangloss_api import create_app
from pangloss_api.validation import located, short
from pangloss_models import Conjunction, Document, Entity, SemanticSpace
from test_model_routes import login


def make_models():
    class Person(Entity):
        pass

    class Statement(Document):
        _meta = Document.Meta(abstract=True, create_directly=False)

        text: str

    class Death(Statement):
        deceased: Person

    class Birth(Statement):
        born: Person

    class Burial(Statement):
        buried: Person

    class Marriage(Statement):
        spouses: list[Person]

    class Hypothetical[T](SemanticSpace[T]):
        pass

    class Causes[TCause, TResult](Conjunction):
        cause: TCause
        result: TResult

    class Factoid(Document):
        statements: list[
            Statement | Hypothetical[Statement] | Causes[Statement, Statement]
        ]

    return Factoid


def problems_of(response):
    assert response.status_code == 422, response.text
    return {
        (tuple(found["loc"]), found["type"]): found
        for found in response.json()["detail"]
    }


def test_the_location_is_the_path_in_what_was_sent(settings):
    make_models()
    client = TestClient(create_app())
    john = login(client)
    person = {"type": "Person", "id": "01a1b046-aaa8-7133-971e-35700aa21c79"}
    body = {
        "type": "Factoid",
        "label": "F",
        "statements": [
            {"type": "Death", "label": "d"},
            {
                "type": "Causes",
                "cause": {"type": "Birth", "label": "b", "text": "t", "born": person},
                "result": {"type": "Burial", "label": "u", "text": 5},
            },
            {
                "type": "Hypothetical",
                "contents": [{"type": "Marriage", "label": "m", "spouses": [person]}],
            },
            "not an object",
        ],
    }
    response = client.post("/api/Factoid", headers=john, json=body)
    found = problems_of(response)

    # (not `["body", "statements", 0, "DeathCreate", "text"]`)
    missing = found[("body", "statements", 0, "text"), "missing"]
    assert missing["model"] == "DeathCreate"
    assert missing["msg"] == "Field required"
    assert (("body", "statements", 0, "deceased"), "missing") in found

    # inside a generic class: its name is not every type it takes, and what is in it is found by its keys
    wrong = found[("body", "statements", 1, "result", "text"), "string_type"]
    assert wrong["model"] == "BurialCreate"
    assert wrong["input"] == 5
    assert (("body", "statements", 1, "result", "buried"), "missing") in found
    assert (("body", "statements", 2, "contents", 0, "text"), "missing") in found

    # what is not an object at all
    (_, kind), unreadable = next(
        item for item in found.items() if item[0][0] == ("body", "statements", 3)
    )
    assert kind == "union_tag_not_found"
    assert unreadable["msg"].startswith("Input should be an object")
    assert unreadable["input"] == "not an object" and "ctx" not in unreadable

    # no name of a class in any location, and nothing long
    for (loc, _), problem in found.items():
        assert all(isinstance(part, int) or part.islower() for part in loc), loc
        assert len(json.dumps(problem)) < 400, problem
    assert len(response.content) < 3000


def test_an_input_is_given_only_when_it_is_short(settings):
    make_models()
    client = TestClient(create_app())
    john = login(client)
    person = {"type": "Person", "id": "01a1b046-aaa8-7133-971e-35700aa21c79"}
    long_text = "x" * 5000
    statement = {"type": "Death", "label": long_text, "deceased": person}
    response = client.post(
        "/api/Factoid",
        headers=john,
        json={"type": "Factoid", "label": 7, "statements": [statement] * 20},
    )
    found = problems_of(response)
    # (the statement a field is missing from is not sent back, twenty times over)
    assert "input" not in found[("body", "statements", 0, "text"), "missing"]
    assert found[("body", "label"), "string_type"]["input"] == 7
    assert len(response.content) < 5000


def test_a_key_that_is_the_name_of_a_model_is_a_key(settings):
    # (a part is a member of a union only where it is not a key of what was sent)
    make_models()
    create_app()
    body = {"statements": [{"Person": {"x": 1}}]}
    assert located(("body", "statements", 0, "Person", "x"), body) == (
        ["body", "statements", 0, "Person", "x"],
        None,
    )
    assert located(("body", "statements", 0, "Person", "y"), {"statements": [{}]}) == (
        ["body", "statements", 0, "y"],
        "Person",
    )
    # what is not in the body is as it was
    assert located(("query", "page_size"), None) == (["query", "page_size"], None)
    assert located((), None) == ([], None)


def test_the_types_of_a_generic_class_are_left_out_of_its_name():
    assert short("DeathCreate") == "DeathCreate"
    assert short("Causes[Accusation, Appointment, Baptism, Birth]Create") == (
        "Causes[…]Create"
    )
    assert short("Negative[Death]Create") == "Negative[Death]Create"
    assert len(short("x" * 500)) == 80
