"""The blocking database module does the same, with the blocking client"""

from uuid import uuid7

import pangloss_sdk
from pangloss_core.settings import ClientSettings
from pangloss_models import initialise
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_registry import ModelRegistry
from pangloss_sdk.databases.api_sync import exposed_functions as sync_api
from sdk_support import FakeServer, head_json, reference_json, sync_client


def make_sync_models():
    ModelRegistry._reset()
    ClientSettings(INSTALLED_APPS=[], DATABASE_MODULE="pangloss_sdk.databases.api_sync")

    class Person(Entity):
        pass

    initialise()
    return Person


def test_the_functions_are_bound_and_block():
    Person = make_sync_models()
    id = uuid7()
    server = FakeServer(lambda request: (200, head_json(id)))
    sync_client(server)

    person = Person.get(id)  # (no await)

    assert isinstance(person, Person.HeadView)
    assert Person.Create.save is sync_api.create_head_node


def test_a_write_logs_in_and_saves():
    Person = make_sync_models()
    server = FakeServer(lambda request: (201, reference_json(label="Ada")))
    sync_client(server, USERNAME="ada", PASSWORD="secret")

    created = Person.Create(label="Ada").save()

    assert created.label == "Ada"
    assert server.logins == 1


def test_an_expired_token_is_renewed():
    Person = make_sync_models()
    server = FakeServer(lambda request: (200, head_json()))
    sync_client(server, USERNAME="ada", PASSWORD="secret")
    Person.get_for_edit(uuid7())

    server.expire_access_tokens()
    Person.get_for_edit(uuid7())

    assert (server.logins, server.refreshes) == (1, 1)


def test_connect_sync_binds_the_blocking_module(an_app):
    server = FakeServer(lambda request: (200, head_json(label="Ada")))
    pangloss_sdk.connect(
        "http://pangloss.test",
        apps=[an_app],
        sync=True,
        transport=server.sync_transport(),
    )
    from an_sdk_test_app.models import Person  # type: ignore[import-not-found]

    assert Person.get(uuid7()).label == "Ada"  # type: ignore[attr-defined]
    pangloss_sdk.disconnect_sync()


# --- every function of the blocking module (the async ones are in test_operations) ------------


def page_of(*labels, next_page=None):
    return {
        "results": [reference_json(label=label) for label in labels],
        "count": 3,
        "page": 1,
        "pageSize": 2,
        "nextPage": next_page,
        "previousPage": None,
    }


def make_sync_document():
    ModelRegistry._reset()
    ClientSettings(INSTALLED_APPS=[], DATABASE_MODULE="pangloss_sdk.databases.api_sync")
    from pangloss_models.model_bases.document import Document

    class Note(Document):
        text: str

    initialise()
    return Note


def test_list_and_iterate_go_through_the_pages():
    Person = make_sync_models()

    def answer(request):
        page = request.url.params.get("page", "1")
        return 200, page_of("Ada", "Bo", next_page=2) if page == "1" else page_of("Cy")

    server = FakeServer(answer)
    sync_client(server)

    first = Person.list(search_terms="a", page_size=2)
    assert [p.label for p in first.results] == ["Ada", "Bo"] and first.next_page == 2
    assert server.requests[-1].url.params["q"] == "a"

    every = [p.label for p in pangloss_sdk.iterate_sync(Person.list, page_size=2)]
    assert every == ["Ada", "Bo", "Cy"]


def test_update_with_and_without_a_version():
    Person = make_sync_models()
    id = uuid7()
    server = FakeServer(lambda request: (200, reference_json(id, "New")))
    sync_client(server, USERNAME="ada", PASSWORD="secret")

    assert Person.Update(id=id, label="New").save(expected_version=3).label == "New"
    assert server.requests[-1].headers["if-match"] == '"3"'
    Person.Update(id=id, label="New").save()
    assert server.requests[-1].headers["if-match"] == "*"


def test_a_stale_update_raises_the_error_of_the_database_module():
    from pangloss_models.exceptions import PanglossVersionConflictError

    Person = make_sync_models()
    body = {
        "detail": "changed",
        "error": "PanglossVersionConflictError",
        "currentVersion": 4,
    }
    server = FakeServer(lambda request: (412, body))
    sync_client(server, USERNAME="ada", PASSWORD="secret")

    try:
        Person.Update(id=uuid7(), label="x").save(expected_version=3)
    except PanglossVersionConflictError as error:
        assert error.current_version == 4
    else:
        raise AssertionError("no error")


def test_get_for_edit_delete_and_undelete_of_an_entity():
    Person = make_sync_models()
    id = uuid7()
    server = FakeServer(
        lambda request: (204, None) if request.method != "GET" else (200, head_json(id))
    )
    sync_client(server, USERNAME="ada", PASSWORD="secret")

    assert Person.delete(id) is None
    assert Person.undelete(id) is None
    assert [
        (r.method, r.url.path)
        for r in server.requests
        if r.url.path.startswith("/api/Person")
    ] == [
        ("DELETE", f"/api/Person/{id}"),
        ("POST", f"/api/Person/{id}/undelete"),
    ]


def test_a_document_is_got_deleted_and_undeleted():
    Note = make_sync_document()
    id = uuid7()
    head = {**head_json(id), "type": "Note", "text": "hi"}

    missing = uuid7()

    def answer(request):
        if request.method == "GET":
            if request.url.path.endswith(str(missing)):
                return 404, {"detail": "There is no Note", "error": "HTTPException"}
            return 200, head
        return 204, None

    server = FakeServer(answer)
    sync_client(server, USERNAME="ada", PASSWORD="secret")

    assert Note.get(id).text == "hi"
    assert Note.get(missing) is None  # (as the database module: not found is None)
    assert Note.delete(id) is None and Note.undelete(id) is None
    assert [
        (r.method, r.url.path)
        for r in server.requests
        if r.url.path.startswith("/api/Note")
    ][-2:] == [
        ("DELETE", f"/api/Note/{id}"),
        ("POST", f"/api/Note/{id}/undelete"),
    ]


# --- when things go wrong (the blocking client) -------------------------------------------------


import httpx2 as httpx
import pytest
from pangloss_sdk import client as sdk_client


@pytest.fixture
def no_waiting(monkeypatch):
    monkeypatch.setattr(sdk_client, "BACKOFF_SECONDS", 0)


def test_a_read_is_tried_again_when_the_connection_fails(no_waiting):
    Person = make_sync_models()
    failures = [2]

    def answer(request):
        if failures[0]:
            failures[0] -= 1
            raise httpx.ConnectError("refused")
        return 200, head_json(label="Ada")

    server = FakeServer(answer)
    sync_client(server, READ_RETRIES=2)
    assert Person.get(uuid7()).label == "Ada"


def test_a_server_that_cannot_be_reached_is_an_error_that_says_where(no_waiting):
    Person = make_sync_models()

    def answer(request):
        raise httpx.ConnectError("refused")

    sync_client(FakeServer(answer), READ_RETRIES=1)
    with pytest.raises(pangloss_sdk.PanglossConnectionError, match="pangloss.test"):
        Person.get(uuid7())


def test_a_write_is_not_tried_again(no_waiting):
    Person = make_sync_models()
    tries = []

    def answer(request):
        tries.append(request.method)
        raise httpx.ConnectError("refused")

    sync_client(FakeServer(answer), USERNAME="ada", PASSWORD="secret", READ_RETRIES=3)
    with pytest.raises(pangloss_sdk.PanglossConnectionError):
        Person.Create(label="Ada").save()
    assert tries == ["POST"]


def test_a_login_that_fails_for_another_reason_raises_that():
    Person = make_sync_models()
    server = FakeServer(lambda request: (200, head_json()))
    original = server._respond

    def respond(request):
        if request.url.path == "/api/users/token":
            return httpx.Response(
                503,
                json={
                    "detail": "Down for a migration",
                    "error": "PanglossReadOnlyError",
                },
            )
        return original(request)

    server._respond = respond
    sync_client(server, USERNAME="ada", PASSWORD="secret")
    from pangloss_models.exceptions import PanglossReadOnlyError

    with pytest.raises(PanglossReadOnlyError):
        Person.get_for_edit(uuid7())


def test_when_the_refresh_token_is_no_good_it_logs_in_again():
    Person = make_sync_models()
    server = FakeServer(lambda request: (200, head_json()))
    sync_client(server, USERNAME="ada", PASSWORD="secret")
    Person.get_for_edit(uuid7())

    server.expire_access_tokens()
    server.valid_refresh.clear()
    Person.get_for_edit(uuid7())

    assert server.logins == 2


def test_with_no_connection_the_functions_say_to_connect():
    Person = make_sync_models()
    sdk_client.install(None)
    with pytest.raises(pangloss_sdk.PanglossNotConnected, match="connect"):
        Person.get(uuid7())


def test_calls_and_logins_are_logged_at_debug_without_credentials(caplog):
    import logging

    Person = make_sync_models()
    server = FakeServer(lambda request: (200, head_json()))
    sync_client(server, USERNAME="ada", PASSWORD="secret")
    caplog.set_level(logging.DEBUG, logger="pangloss")

    Person.get_for_edit(uuid7())
    server.expire_access_tokens()
    Person.get_for_edit(uuid7())

    lines = [r.getMessage() for r in caplog.records if r.name == "pangloss.sdk.client"]
    assert any("GET" in line and "-> 200" in line for line in lines)
    assert "Access token refreshed" in lines
    for secret in ("secret", "access-1", "refresh-1"):
        assert secret not in caplog.text
