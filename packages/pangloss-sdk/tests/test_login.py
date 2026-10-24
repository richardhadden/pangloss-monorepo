"""Logging in: the tokens held, the settings, the prompt, and no way to ask"""

import asyncio
from uuid import uuid7

import httpx2 as httpx
import pytest
from pangloss_sdk import (
    PanglossAuthenticationError,
    PanglossAuthenticationRequired,
    PanglossConnectionError,
    auth,
)
from pangloss_sdk import (
    client as sdk_client,
)
from sdk_support import (
    FakeServer,
    async_client,
    head_json,
    make_models,
    reference_json,
    settings,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def no_terminal(monkeypatch):
    monkeypatch.setattr(auth, "can_prompt", lambda: False)


def edit_server():
    return FakeServer(lambda request: (200, head_json()))


async def test_a_read_does_not_log_in():
    Person = make_models()
    server = edit_server()
    async_client(server)
    await Person.get(uuid7())
    assert server.logins == 0


async def test_the_settings_log_in_and_the_token_is_kept():
    Person = make_models()
    server = edit_server()
    client = async_client(server, USERNAME="ada", PASSWORD="secret")

    await Person.get_for_edit(uuid7())
    await Person.get_for_edit(uuid7())

    assert server.logins == 1
    assert client.session.access_token == "access-1"
    # (a password is used for the login and not kept as a token or on the request)
    assert b"secret" not in b"".join(r.content for r in server.requests[1:])


async def test_without_credentials_and_without_a_terminal_it_says_so():
    Person = make_models()
    async_client(edit_server())
    with pytest.raises(PanglossAuthenticationRequired, match="PANGLOSS_USERNAME"):
        await Person.get_for_edit(uuid7())


async def test_a_wrong_password_in_the_settings_is_refused():
    Person = make_models()
    async_client(edit_server(), USERNAME="ada", PASSWORD="wrong")
    with pytest.raises(PanglossAuthenticationError, match="refused") as error:
        await Person.get_for_edit(uuid7())
    assert not isinstance(error.value, PanglossAuthenticationRequired)


async def test_the_prompt_is_used_when_there_are_no_credentials():
    Person = make_models()
    asked = []

    def prompt(url, username):
        asked.append(url)
        return "ada", "secret"

    server = edit_server()
    async_client(server, prompt=prompt)

    await Person.get_for_edit(uuid7())
    await Person.get_for_edit(uuid7())

    assert asked == ["http://pangloss.test"]  # once


async def test_a_wrong_password_at_the_prompt_is_asked_for_again_three_times():
    Person = make_models()
    answers = iter([("ada", "no"), ("ada", "nope"), ("ada", "still")])
    asked = []

    def prompt(url, username):
        asked.append(username)
        return next(answers)

    async_client(edit_server(), prompt=prompt)
    with pytest.raises(PanglossAuthenticationError, match="Too many"):
        await Person.get_for_edit(uuid7())
    assert len(asked) == 3


async def test_a_right_password_after_a_wrong_one():
    Person = make_models()
    answers = iter([("ada", "no"), ("ada", "secret")])
    server = edit_server()
    async_client(server, prompt=lambda url, username: next(answers))
    await Person.get_for_edit(uuid7())
    assert server.logins == 2


async def test_an_expired_access_token_is_renewed_with_the_refresh_token():
    Person = make_models()
    server = edit_server()
    client = async_client(server, USERNAME="ada", PASSWORD="secret")
    await Person.get_for_edit(uuid7())

    server.expire_access_tokens()
    await Person.get_for_edit(uuid7())

    assert (server.logins, server.refreshes) == (1, 1)
    assert client.session.refresh_token == "refresh-1"


async def test_requests_refused_together_renew_the_token_once():
    Person = make_models()
    server = edit_server()
    async_client(server, USERNAME="ada", PASSWORD="secret")
    await Person.get_for_edit(uuid7())

    server.expire_access_tokens()
    await asyncio.gather(*(Person.get_for_edit(uuid7()) for _ in range(5)))

    assert server.refreshes == 1


async def test_when_the_refresh_token_is_refused_it_logs_in_again():
    Person = make_models()
    server = edit_server()
    async_client(server, USERNAME="ada", PASSWORD="secret")
    await Person.get_for_edit(uuid7())

    server.expire_access_tokens()
    server.valid_refresh.clear()
    await Person.get_for_edit(uuid7())

    assert server.logins == 2


async def test_a_read_with_a_dead_token_is_made_again_without_it():
    Person = make_models()
    server = edit_server()
    client = async_client(server, USERNAME="ada", PASSWORD="secret")
    await Person.get_for_edit(uuid7())

    server.expire_access_tokens()
    server.valid_refresh.clear()
    assert await Person.get(uuid7()) is not None

    assert server.logins == 1  # (no prompt for what anyone may read)
    assert client.session.access_token is None


async def test_a_given_token_is_used_as_it_is():
    Person = make_models()
    server = edit_server()
    server.valid_tokens.add("mine")
    async_client(server, TOKEN="mine")

    await Person.get_for_edit(uuid7())

    assert server.logins == 0
    assert server.requests[0].headers["authorization"] == "Bearer mine"


# --- the network ----------------------------------------------------------------------


class Flaky:
    """A transport that fails a number of times, then answers"""

    def __init__(self, failures: int, body):
        self.failures = failures
        self.calls = 0
        self.body = body

    async def handle_async_request(self, request):
        self.calls += 1
        if self.calls <= self.failures:
            raise httpx.ConnectError("down")
        return httpx.Response(200, json=self.body, request=request)


async def test_a_read_is_tried_again_after_a_network_error(monkeypatch):
    Person = make_models()
    monkeypatch.setattr(sdk_client, "BACKOFF_SECONDS", 0)
    transport = Flaky(2, head_json())
    sdk_client.install(sdk_client.AsyncClient(settings(), transport))  # type: ignore[arg-type]

    assert await Person.get(uuid7()) is not None
    assert transport.calls == 3


async def test_a_read_gives_up_after_its_retries(monkeypatch):
    Person = make_models()
    monkeypatch.setattr(sdk_client, "BACKOFF_SECONDS", 0)
    transport = Flaky(99, head_json())
    sdk_client.install(sdk_client.AsyncClient(settings(), transport))  # type: ignore[arg-type]

    with pytest.raises(PanglossConnectionError, match="pangloss.test"):
        await Person.get(uuid7())
    assert transport.calls == 3


async def test_a_write_is_never_tried_again(monkeypatch):
    Person = make_models()
    monkeypatch.setattr(sdk_client, "BACKOFF_SECONDS", 0)
    transport = Flaky(1, reference_json())
    sdk_client.install(
        sdk_client.AsyncClient(settings(TOKEN="t"), transport)  # type: ignore[arg-type]
    )

    with pytest.raises(PanglossConnectionError):
        await Person.Create(label="Ada").save()
    assert transport.calls == 1
