"""`save(instructions={...})` through the SDK: each instruction is a query parameter of the create, update or
with-companions request, the value as text; nothing is checked by the client (the server refuses what no app of its
declares), and the server's refusal is raised as the database module raises it"""

from types import SimpleNamespace
from urllib.parse import parse_qs
from uuid import uuid4, uuid7

import pytest
from pangloss_core import ClientSettings
from pangloss_models import (
    Entity,
    ModelRegistry,
    PanglossInstructionError,
    initialise,
)
from pangloss_sdk import protocol
from pangloss_sdk.databases.api import exposed_functions as api
from pangloss_sdk.databases.api_sync import exposed_functions as sync_api
from sdk_support import FakeServer, async_client, reference_json, sync_client


class Letter:
    pass


def instance():
    return SimpleNamespace(
        _owner=Letter, id=uuid4(), model_dump=lambda **_: {"type": "Letter"}
    )


def test_the_instructions_are_in_the_query_of_each_write_call():
    said = {"suggest": False, "mode": "fast"}
    params = {"suggest": "false", "mode": "fast"}
    assert protocol.create(instance(), instructions=said).params == params
    assert protocol.update(instance(), instructions=said).params == params
    assert (
        protocol.create_with_companions(instance(), {}, instructions=said).params
        == params
    )
    # (with the others)
    assert protocol.create(
        instance(), detail=True, instructions={"suggest": True}
    ).params == {"detail": "true", "suggest": "true"}
    assert protocol.update(instance()).params is None


def query_of(request) -> dict[str, list[str]]:
    return parse_qs(request.url.query.decode())


def writes(server):
    return [
        r
        for r in server.requests
        if r.method in ("POST", "PUT") and "/api/users" not in r.url.path
    ]


@pytest.mark.asyncio
async def test_the_async_functions_send_them():
    ModelRegistry._reset()

    class Person(Entity):
        pass

    initialise()
    server = FakeServer(lambda request: (201, reference_json(label="Ada")))
    async_client(server, USERNAME="ada", PASSWORD="secret")
    # (no app of the client declares it: sent all the same)
    await api.create_head_node(
        Person.Create(label="Ada"), instructions={"suggest": False}
    )
    await api.update_head_node(
        Person.Update(id=uuid7(), label="Ada"), instructions={"suggest": True}
    )
    assert [query_of(r).get("suggest") for r in writes(server)] == [["false"], ["true"]]


def test_the_blocking_functions_send_them():
    ModelRegistry._reset()
    ClientSettings(INSTALLED_APPS=[], STORAGE="pangloss_sdk.storage:api_sync")

    class Person(Entity):
        pass

    initialise()
    server = FakeServer(lambda request: (201, reference_json(label="Ada")))
    sync_client(server, USERNAME="ada", PASSWORD="secret")
    Person.Create(label="Ada").save(instructions={"suggest": False})
    sync_api.update_head_node(
        Person.Update(id=uuid7(), label="Ada"), instructions={"suggest": True}
    )
    assert [query_of(r).get("suggest") for r in writes(server)] == [["false"], ["true"]]


def test_the_servers_refusal_is_raised_as_the_same_error():
    body = {
        "detail": "The instruction 'suggest' of a write is one of true, false, not 'maybe'",
        "error": "PanglossInstructionError",
    }
    response = SimpleNamespace(
        status_code=422, is_success=False, json=lambda: body, text=""
    )
    error = protocol.error_for(response)
    assert isinstance(error, PanglossInstructionError)
    assert str(error) == body["detail"]
