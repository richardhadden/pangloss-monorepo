"""The instructions of one write over the API (`hooks.declare_write_instruction`): the create, update and
with-companions routes of a model take the declared ones as query parameters, in either case, and give them to the
save; any other parameter is refused as before; no other route takes them"""

from uuid import uuid7

import pytest
from conftest import PASSWORD  # noqa: F401
from fastapi.testclient import TestClient
from pangloss_api import create_app
from pangloss_api.routes import models as model_routes
from pangloss_models import Companion, Document, Entity, hooks
from test_model_routes import login

NAME = "test_suggest"


@pytest.fixture
def declared(monkeypatch):
    monkeypatch.setattr(hooks, "write_instructions", {})
    hooks.declare_write_instruction(
        hooks.WriteInstruction(NAME, ("true", "false"), "Whether to suggest")
    )


def make_models():
    class Person(Entity):
        _meta = Entity.Meta(
            companions=[
                Companion(name="naming", document="Naming", entity_field="named")
            ]
        )

    class Naming(Document):
        named: Person

    return Person, Naming


def saving(monkeypatch) -> list[tuple[str, dict]]:
    """What each save is given (as the storage's save does, it checks the instructions first). After the app is
    made: `initialise()` binds the storage's save"""
    from pangloss_models.model_bases.entity import _EntityCreateBase, _EntityUpdateBase

    given: list[tuple[str, dict]] = []

    def answer(self):
        return self._owner.ReferenceView(id=getattr(self, "id", uuid7()), label="x")

    async def create(self, detail=False, instructions=None):
        given.append(("create", hooks.checked_instructions(instructions)))
        return answer(self)

    async def update(self, detail=False, expected_version=None, instructions=None):
        given.append(("update", hooks.checked_instructions(instructions)))
        return answer(self)

    async def heads(*instances, detail=False, instructions=None):
        given.append(("heads", hooks.checked_instructions(instructions)))
        return [
            instance._owner.ReferenceView(
                id=getattr(instance, "id", uuid7()), label="x"
            )
            for instance in instances
        ]

    monkeypatch.setattr(_EntityCreateBase, "save", create)
    monkeypatch.setattr(_EntityUpdateBase, "save", update)
    monkeypatch.setattr(model_routes, "create_heads", heads)
    return given


def writes(client, headers, query: str) -> list[int]:
    """The three write routes, with the query given: their statuses"""
    person_id = uuid7()
    return [
        client.post(
            f"/api/Person{query}",
            json={"type": "Person", "label": "A"},
            headers=headers,
        ).status_code,
        client.put(
            f"/api/Person/{person_id}{query}",
            json={"type": "Person", "id": str(person_id), "label": "A"},
            headers={**headers, "If-Match": '"1"'},
        ).status_code,
        client.post(
            f"/api/Person/with-companions{query}",
            json={
                "item": {"type": "Person", "label": "A"},
                "companions": [{"name": "naming", "document": {"label": "A named"}}],
            },
            headers=headers,
        ).status_code,
    ]


def test_each_write_route_takes_a_declared_instruction_in_either_case(
    settings, declared, monkeypatch
):
    make_models()
    client = TestClient(create_app())
    headers = login(client)
    saved = saving(monkeypatch)

    assert writes(client, headers, "?testSuggest=true") == [201, 200, 201]
    assert writes(client, headers, "?test_suggest=false") == [201, 200, 201]
    assert writes(client, headers, "") == [201, 200, 201]
    assert saved == [
        ("create", {NAME: "true"}),
        ("update", {NAME: "true"}),
        ("heads", {NAME: "true"}),
        ("create", {NAME: "false"}),
        ("update", {NAME: "false"}),
        ("heads", {NAME: "false"}),
        ("create", {}),
        ("update", {}),
        ("heads", {}),
    ]


def test_an_undeclared_parameter_and_a_bad_value_are_refused(
    settings, declared, monkeypatch
):
    make_models()
    client = TestClient(create_app())
    headers = login(client)
    saved = saving(monkeypatch)

    assert writes(client, headers, "?colour=red") == [422, 422, 422]
    response = client.post(
        "/api/Person?colour=red", json={"type": "Person", "label": "A"}, headers=headers
    )
    (refused,) = response.json()["detail"]
    assert refused["type"] == "unknown_parameter"
    assert refused["loc"] == ["query", "colour"]
    # (the instruction is among what the route has)
    assert NAME in refused["msg"] and "detail" in refused["msg"]

    assert writes(client, headers, "?testSuggest=maybe") == [422, 422, 422]
    response = client.post(
        "/api/Person?testSuggest=maybe",
        json={"type": "Person", "label": "A"},
        headers=headers,
    )
    assert response.json() == {
        "detail": f"The instruction '{NAME}' of a write is one of true, false, not 'maybe'",
        "error": "PanglossInstructionError",
    }
    # (what was refused before the save never reached it; a bad value is the save's to refuse)
    assert [op for op, _ in saved] == []


def test_with_no_instruction_declared_it_is_an_unknown_parameter(settings, monkeypatch):
    make_models()
    client = TestClient(create_app())
    headers = login(client)
    saved = saving(monkeypatch)
    assert writes(client, headers, "?testSuggest=true") == [422, 422, 422]
    assert saved == []


def test_no_other_route_takes_an_instruction(settings, declared, monkeypatch):
    make_models()
    client = TestClient(create_app())
    headers = login(client)
    saving(monkeypatch)
    person_id = uuid7()
    for response in (
        client.get(f"/api/Person?{NAME}=true"),
        client.get(f"/api/Person/{person_id}?{NAME}=true"),
        client.delete(f"/api/Person/{person_id}?{NAME}=true", headers=headers),
        client.post(f"/api/Person/{person_id}/undelete?{NAME}=true", headers=headers),
    ):
        assert response.status_code == 422, response.text
        assert response.json()["detail"][0]["type"] == "unknown_parameter"


def test_the_declared_instructions_are_parameters_of_the_write_routes_in_openapi(
    settings, declared
):
    make_models()
    document = create_app().openapi()
    by_id = {
        operation["operationId"]: operation
        for path in document["paths"].values()
        for operation in path.values()
    }
    for operation_id in (
        "create_Person",
        "update_Person",
        "create_Person_with_companions",
    ):
        (parameter,) = [
            p for p in by_id[operation_id]["parameters"] if p["name"] == NAME
        ]
        assert parameter["in"] == "query"
        assert parameter["schema"] == {"type": "string", "enum": ["true", "false"]}
        assert parameter["description"] == "Whether to suggest"
    for operation_id in ("list_Person", "delete_Person"):
        assert NAME not in [
            p["name"] for p in by_id[operation_id].get("parameters", [])
        ]
