"""Each model function is one request, and its answer is what the database module gives"""

import json
from uuid import uuid7

import pytest
from pangloss_models.exceptions import (
    PanglossConflictError,
    PanglossEntityInUseError,
    PanglossNotDeletableError,
    PanglossNotFoundError,
    PanglossReadOnlyError,
    PanglossReferenceError,
    PanglossVersionConflictError,
    PanglossWriteError,
)
from pangloss_sdk import (
    PanglossAuthenticationError,
    PanglossPermissionError,
    PanglossRequestError,
    PanglossServerError,
)
from pangloss_sdk.databases.api import exposed_functions as api
from sdk_support import (
    FakeServer,
    async_client,
    head_json,
    make_models,
    reference_json,
)

pytestmark = pytest.mark.asyncio


def logged_in_client(server):
    # (credentials given: a request that needs a login does it at once)
    return async_client(server, USERNAME="ada", PASSWORD="secret")


async def test_get_reads_the_head_view():
    Person = make_models()
    id = uuid7()
    server = FakeServer(lambda request: (200, head_json(id, "Ada")))
    async_client(server)

    person = await Person.get(id)  # (bound once the models are initialised)

    assert isinstance(person, Person.HeadView)
    assert person.label == "Ada"
    request = server.requests[0]
    assert (request.method, request.url.path) == ("GET", f"/api/Person/{id}")
    assert "authorization" not in request.headers  # (a read needs no login)


async def test_get_at_a_url_puts_it_in_the_path_with_its_query_string():
    Person = make_models()
    server = FakeServer(lambda request: (200, head_json()))
    async_client(server)

    await api.get_entity(Person, "https://example.com/people/ada?id=5")  # type: ignore[arg-type]

    request = server.requests[0]
    assert request.url.path == "/api/Person/https://example.com/people/ada"
    assert request.url.query == b"id=5"


async def test_get_of_nothing_is_none():
    Person = make_models()
    server = FakeServer(lambda request: (404, {"detail": "no", "error": "x"}))
    async_client(server)
    assert await Person.get(uuid7()) is None


async def test_get_for_edit_needs_a_login():
    Person = make_models()
    id = uuid7()
    server = FakeServer(lambda request: (200, head_json(id, version=3)))
    logged_in_client(server)

    edit = await Person.get_for_edit(id)

    assert isinstance(edit, Person.EditView)
    assert edit.meta.version == 3
    assert server.logins == 1
    assert server.requests[-1].url.path.endswith("/edit")
    assert server.requests[-1].headers["authorization"].startswith("Bearer ")


async def test_list_sends_its_parameters_and_reads_a_page():
    Person = make_models()
    page = {
        "results": [reference_json(label="Ada"), reference_json(label="Bo")],
        "count": 5,
        "page": 2,
        "pageSize": 2,
        "nextPage": 3,
        "previousPage": 1,
    }
    server = FakeServer(lambda request: (200, page))
    async_client(server)

    result = await Person.list(
        search_terms="a", page_number=2, page_size=2, deep_search=True
    )

    assert dict(server.requests[0].url.params) == {
        "q": "a",
        "page": "2",
        "page_size": "2",
        "deep": "true",
    }
    assert [item.label for item in result.results] == ["Ada", "Bo"]
    assert (result.count, result.page, result.next_page) == (5, 2, 3)
    assert result.results[0].__class__ is Person.ReferenceView


async def test_create_posts_the_create_model_by_alias():
    Person = make_models()
    id = uuid7()
    server = FakeServer(lambda request: (201, reference_json(id, "Ada")))
    logged_in_client(server)

    created = await Person.Create(label="Ada").save()

    assert isinstance(created, Person.ReferenceView)
    assert created.id == id
    request = server.requests[-1]
    assert (request.method, request.url.path) == ("POST", "/api/Person")
    assert json.loads(request.content)["label"] == "Ada"
    assert json.loads(request.content)["type"] == "Person"
    assert "detail" not in request.url.params


async def test_create_with_detail_reads_a_head_view():
    Person = make_models()
    server = FakeServer(lambda request: (201, head_json()))
    logged_in_client(server)

    created = await Person.Create(label="Ada").save(detail=True)

    assert isinstance(created, Person.HeadView)
    assert server.requests[-1].url.params["detail"] == "true"


@pytest.mark.parametrize(("expected_version", "if_match"), [(None, "*"), (3, '"3"')])
async def test_update_says_which_version_it_is_based_on(expected_version, if_match):
    Person = make_models()
    id = uuid7()
    server = FakeServer(lambda request: (200, reference_json(id, "New")))
    logged_in_client(server)

    updated = await Person.Update(id=id, label="New").save(
        expected_version=expected_version
    )

    assert updated.label == "New"
    request = server.requests[-1]
    assert (request.method, request.url.path) == ("PUT", f"/api/Person/{id}")
    assert request.headers["if-match"] == if_match


async def test_delete_and_undelete():
    Person = make_models()
    id = uuid7()
    server = FakeServer(lambda request: (204, None))
    logged_in_client(server)

    assert await Person.delete(id) is None
    assert await Person.undelete(id) is None

    assert [(r.method, r.url.path) for r in server.requests[-2:]] == [
        ("DELETE", f"/api/Person/{id}"),
        ("POST", f"/api/Person/{id}/undelete"),
    ]


# --- errors: the exceptions of the database module are raised again ----------------------


@pytest.mark.parametrize(
    ("status", "body", "raised"),
    [
        (
            404,
            {"detail": "no", "error": "PanglossNotFoundError"},
            PanglossNotFoundError,
        ),
        (404, {"detail": "no"}, PanglossNotFoundError),
        (
            409,
            {"detail": "used", "error": "PanglossConflictError"},
            PanglossConflictError,
        ),
        (409, {"detail": "used"}, PanglossConflictError),
        (
            400,
            {"detail": "part", "error": "PanglossNotDeletableError"},
            PanglossNotDeletableError,
        ),
        (
            422,
            {"detail": "bad ref", "error": "PanglossReferenceError"},
            PanglossReferenceError,
        ),
        (400, {"detail": "no", "error": "PanglossWriteError"}, PanglossWriteError),
        (
            503,
            {"detail": "migrating", "error": "PanglossReadOnlyError"},
            PanglossReadOnlyError,
        ),
        (403, {"detail": "Not authorised"}, PanglossPermissionError),
        (400, {"detail": "bad"}, PanglossRequestError),
        (422, {"detail": [{"loc": ["body"], "msg": "x"}]}, PanglossRequestError),
        (500, {"detail": "Internal server error"}, PanglossServerError),
    ],
)
async def test_errors_are_raised_as_the_database_module_raises_them(
    status, body, raised
):
    Person = make_models()
    server = FakeServer(lambda request: (status, body))
    logged_in_client(server)

    with pytest.raises(raised):
        await Person.delete(uuid7())


async def test_a_version_conflict_has_the_current_version():
    Person = make_models()
    id = uuid7()
    body = {
        "detail": "updated since",
        "error": "PanglossVersionConflictError",
        "currentVersion": 4,
    }
    server = FakeServer(lambda request: (412, body))
    logged_in_client(server)

    with pytest.raises(PanglossVersionConflictError) as error:
        await Person.Update(id=id, label="x").save(expected_version=3)

    assert error.value.current_version == 4


async def test_an_entity_in_use_says_what_refers_to_it():
    Person = make_models()
    body = {
        "detail": "in use",
        "error": "PanglossEntityInUseError",
        "referencedBy": [{"id": "1", "type": "Statement", "label": "S"}],
    }
    server = FakeServer(lambda request: (409, body))
    logged_in_client(server)

    with pytest.raises(PanglossEntityInUseError) as error:
        await Person.delete(uuid7())

    assert error.value.referenced_by == [{"id": "1", "type": "Statement", "label": "S"}]


async def test_a_refused_login_is_an_authentication_error():
    Person = make_models()
    server = FakeServer(lambda request: (401, {"detail": "Not logged in"}))
    logged_in_client(server)
    server.valid_tokens.clear()

    # (the server refuses every token it gives, and the retry is refused too)
    server.answer = lambda request: (401, {"detail": "Not logged in"})
    with pytest.raises(PanglossAuthenticationError):
        await Person.delete(uuid7())
