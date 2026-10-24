"""A login kept between runs (`pangloss-sdk login`): where it is kept, how it is used, the command"""

import io
import stat
from uuid import uuid7

import pytest
from pangloss_sdk import auth, credentials
from pangloss_sdk import cli as sdk_cli
from sdk_support import FakeServer, async_client, head_json, make_models

URL = "http://pangloss.test"


@pytest.fixture(autouse=True)
def no_terminal(monkeypatch):
    monkeypatch.setattr(auth, "can_prompt", lambda: False)


# --- the store -----------------------------------------------------------------------------


def test_a_login_is_kept_in_a_file_only_the_user_can_read():
    where = credentials.save(URL, {"refresh_token": "r", "username": "ada"})

    path = credentials.credentials_file()
    assert where == str(path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert credentials.load(URL) == {"refresh_token": "r", "username": "ada"}
    # (the key is the URL, without a trailing slash or a capital)
    assert credentials.load("HTTP://Pangloss.test/") == credentials.load(URL)
    assert credentials.load("http://other.test") is None


def test_the_directory_is_private_too(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "PANGLOSS_CREDENTIALS_FILE", str(tmp_path / "config/pangloss/credentials.json")
    )
    credentials.save(URL, {"token": "t"})
    assert stat.S_IMODE((tmp_path / "config/pangloss").stat().st_mode) == 0o700


def test_a_file_others_can_read_is_not_used():
    credentials.save(URL, {"refresh_token": "r"})
    credentials.credentials_file().chmod(0o644)

    with pytest.warns(UserWarning, match="can be read by others"):
        assert credentials.load(URL) is None


def test_forget_removes_only_that_server():
    credentials.save(URL, {"refresh_token": "r"})
    credentials.save("http://other.test", {"refresh_token": "o"})

    assert credentials.forget(URL) is True
    assert credentials.forget(URL) is False
    assert credentials.load(URL) is None
    assert credentials.load("http://other.test") == {"refresh_token": "o"}


def test_a_broken_file_is_as_empty():
    credentials.credentials_file().write_text("not json")
    credentials.credentials_file().chmod(0o600)
    assert credentials.load(URL) is None


def test_the_keyring_is_used_when_there_is_one(monkeypatch):
    kept: dict = {}

    class FakeKeyring:
        def get_password(self, service, key):
            return kept.get((service, key))

        def set_password(self, service, key, value):
            kept[(service, key)] = value

        def delete_password(self, service, key):
            del kept[(service, key)]

    monkeypatch.setattr(credentials, "keyring_module", lambda: FakeKeyring())

    assert credentials.save(URL, {"refresh_token": "r"}) == "the keyring"
    assert not credentials.credentials_file().exists()
    assert credentials.load(URL) == {"refresh_token": "r"}
    assert credentials.forget(URL) is True
    assert kept == {}


# --- using it ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_kept_refresh_token_gets_the_access_token_with_no_prompt():
    Person = make_models()
    server = FakeServer(lambda request: (200, head_json()))
    server.valid_refresh.add("kept")
    credentials.save(
        "http://pangloss.test/", {"refresh_token": "kept", "username": "ada"}
    )
    client = async_client(server)

    await Person.get_for_edit(uuid7())

    assert (server.logins, server.refreshes) == (0, 1)
    assert client.session.username == "ada"


@pytest.mark.asyncio
async def test_a_refresh_token_that_is_no_good_falls_back_to_a_login():
    Person = make_models()
    server = FakeServer(lambda request: (200, head_json()))
    credentials.save("http://pangloss.test/", {"refresh_token": "revoked"})
    async_client(server, USERNAME="ada", PASSWORD="secret")

    await Person.get_for_edit(uuid7())

    assert server.logins == 1


@pytest.mark.asyncio
async def test_settings_credentials_are_preferred_to_a_kept_login():
    Person = make_models()
    server = FakeServer(lambda request: (200, head_json()))
    server.valid_refresh.add("kept")
    credentials.save("http://pangloss.test/", {"refresh_token": "kept"})
    async_client(server, USERNAME="ada", PASSWORD="secret")

    await Person.get_for_edit(uuid7())

    assert (server.logins, server.refreshes) == (1, 0)


@pytest.mark.asyncio
async def test_a_kept_personal_access_token_is_used_as_it_is():
    Person = make_models()
    server = FakeServer(lambda request: (200, head_json()))
    server.valid_tokens.add("pgl_kept")
    credentials.save("http://pangloss.test/", {"token": "pgl_kept", "username": "ada"})
    async_client(server)

    await Person.get_for_edit(uuid7())

    assert server.requests[0].headers["authorization"] == "Bearer pgl_kept"
    assert (server.logins, server.refreshes) == (0, 0)


@pytest.mark.asyncio
async def test_the_kept_login_can_be_turned_off():
    Person = make_models()
    server = FakeServer(lambda request: (200, head_json()))
    credentials.save("http://pangloss.test/", {"token": "pgl_kept"})
    async_client(server, USE_STORED_LOGIN=False)
    from pangloss_sdk import PanglossAuthenticationRequired

    with pytest.raises(PanglossAuthenticationRequired):
        await Person.get_for_edit(uuid7())


# --- the command ---------------------------------------------------------------------------


def run(server, *argv, prompt=None):
    out = io.StringIO()
    code = sdk_cli.main(
        list(argv), transport=server.sync_transport(), prompt=prompt, out=out
    )
    return code, out.getvalue()


def test_login_keeps_a_refresh_token_and_not_the_password():
    server = FakeServer()
    code, output = run(
        server, "login", URL, prompt=lambda url, username: ("ada", "secret")
    )

    assert code == 0 and "Logged in" in output and "as ada" in output
    stored = credentials.load(URL)
    assert stored is not None and stored["refresh_token"] in server.valid_refresh
    assert "secret" not in credentials.credentials_file().read_text()


def test_login_asks_again_for_a_wrong_password_and_gives_up_after_three():
    answers = iter([("ada", "no"), ("ada", "secret")])
    code, _ = run(
        FakeServer(), "login", URL, prompt=lambda url, username: next(answers)
    )
    assert code == 0

    code, _ = run(
        FakeServer(),
        "login",
        "http://other.test",
        prompt=lambda url, username: ("ada", "never"),
    )
    assert code == 1
    assert credentials.load("http://other.test") is None


def test_login_with_a_token_checks_it_and_keeps_it(monkeypatch):
    server = FakeServer()
    server.valid_tokens.add("pgl_good")

    monkeypatch.setattr("getpass.getpass", lambda prompt: "pgl_bad")
    assert run(server, "login", URL, "--token")[0] == 1
    assert credentials.load(URL) is None

    monkeypatch.setattr("getpass.getpass", lambda prompt: "pgl_good")
    code, output = run(server, "login", URL, "--token")
    assert code == 0 and "with a token" in output
    assert credentials.load(URL) == {"token": "pgl_good", "username": "ada"}


def test_logout_revokes_the_token_on_the_server_and_forgets_it():
    server = FakeServer()
    run(server, "login", URL, prompt=lambda url, username: ("ada", "secret"))
    stored = credentials.load(URL)
    assert stored is not None
    kept = stored["refresh_token"]

    code, output = run(server, "logout", URL)

    assert code == 0 and "revoked on the server" in output
    assert server.revoked == [kept]
    assert credentials.load(URL) is None
    assert "no login kept" in run(server, "logout", URL)[1]


def test_status_says_where_you_are():
    server = FakeServer(
        lambda request: (200, {"distribution": "shop-sdk", "version": "0.1"})
    )
    assert "none kept" in run(server, "status", URL)[1]

    run(server, "login", URL, prompt=lambda url, username: ("ada", "secret"))
    _, output = run(server, "status", URL)
    assert "ada" in output and "refresh token" in output and "still good" in output

    server.valid_refresh.clear()
    assert "NOT good" in run(server, "status", URL)[1]


def test_the_url_can_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("PANGLOSS_URL", URL)
    server = FakeServer()
    assert run(server, "login", prompt=lambda url, username: ("ada", "secret"))[0] == 0
    assert credentials.load(URL) is not None
