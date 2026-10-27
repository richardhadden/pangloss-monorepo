"""Ending sessions (logout, a password change, logout everywhere) and personal access tokens"""

import asyncio
import datetime

from conftest import PASSWORD
from pangloss_api.dependencies import ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME
from pangloss_users import service
from test_api_users import bearer, login, make_user


def tokens(client, username="john") -> dict:
    return login(client, username).json()


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def me(client, token: str):
    return client.get("/api/users/me", headers=auth(token))


# --- logging out ------------------------------------------------------------------------


def test_revoking_a_refresh_token_ends_it(client):
    make_user()
    given = tokens(client)
    refresh = {"refresh_token": given["refresh_token"]}
    assert client.post("/api/users/token/refresh", json=refresh).status_code == 200

    assert client.post("/api/users/token/revoke", json=refresh).status_code == 204

    assert client.post("/api/users/token/refresh", json=refresh).status_code == 401
    # (the access token made already lasts until it expires)
    assert me(client, given["access_token"]).status_code == 200


def test_revoking_is_for_whoever_has_the_token_and_ignores_what_is_not_good(client):
    assert (
        client.post(
            "/api/users/token/revoke", json={"refresh_token": "nonsense"}
        ).status_code
        == 204
    )
    assert (
        client.post("/api/users/token/revoke", json={"refresh_token": ""}).status_code
        == 204
    )


def test_ending_a_session_revokes_the_tokens_in_its_cookies(client):
    make_user()
    client.post("/api/users/session", data={"username": "john", "password": PASSWORD})
    access = client.cookies[ACCESS_COOKIE_NAME]
    refresh = client.cookies[REFRESH_COOKIE_NAME]

    assert client.delete("/api/users/session").status_code == 200

    assert me(client, access).status_code == 401
    assert (
        client.post(
            "/api/users/token/refresh", json={"refresh_token": refresh}
        ).status_code
        == 401
    )


def test_logout_everywhere_ends_every_token_made_until_then(client):
    make_user()
    first, second = tokens(client), tokens(client)

    assert (
        client.post(
            "/api/users/me/logout-all", headers=auth(first["access_token"])
        ).status_code
        == 204
    )

    for given in (first, second):
        assert me(client, given["access_token"]).status_code == 401
        assert (
            client.post(
                "/api/users/token/refresh",
                json={"refresh_token": given["refresh_token"]},
            ).status_code
            == 401
        )
    # (a new login is fine)
    assert me(client, tokens(client)["access_token"]).status_code == 200


# --- a password change ends sessions -------------------------------------------------------


def test_changing_your_password_ends_your_sessions(client):
    make_user()
    old = tokens(client)
    response = client.put(
        "/api/users/me/password",
        json={"oldPassword": PASSWORD, "newPassword": "a better password"},
        headers=auth(old["access_token"]),
    )
    assert response.status_code == 200

    assert me(client, old["access_token"]).status_code == 401
    assert (
        client.post(
            "/api/users/token/refresh", json={"refresh_token": old["refresh_token"]}
        ).status_code
        == 401
    )
    new = client.post(
        "/api/users/token", data={"username": "john", "password": "a better password"}
    )
    assert me(client, new.json()["access_token"]).status_code == 200


def test_an_admin_setting_a_password_ends_that_users_sessions_not_their_own(client):
    make_user("root", admin=True)
    make_user("jane")
    jane, root = tokens(client, "jane"), tokens(client, "root")

    client.put(
        "/api/users/jane/password",
        json={"password": "another password"},
        headers=auth(root["access_token"]),
    )

    assert me(client, jane["access_token"]).status_code == 401
    assert me(client, root["access_token"]).status_code == 200


# --- personal access tokens --------------------------------------------------------------------


def make_token(client, headers, **body):
    return client.post(
        "/api/users/me/tokens", json={"name": "for scripts", **body}, headers=headers
    )


def test_a_personal_access_token_is_shown_once_and_works_as_a_bearer_token(client):
    make_user()
    headers = bearer(client)

    created = make_token(client, headers, expiresDays=30)
    assert created.status_code == 201
    body = created.json()
    assert body["token"].startswith("pgl_")
    assert body["name"] == "for scripts" and body["scope"] == "write"
    assert body["expiresWhen"] is not None

    listed = client.get("/api/users/me/tokens", headers=headers).json()
    assert [t["id"] for t in listed] == [body["id"]]
    assert "token" not in listed[0] and "tokenHash" not in listed[0]

    # (it works, and it is the user)
    assert me(client, body["token"]).json()["username"] == "john"


def test_a_read_token_can_read_and_not_write(client):
    make_user()
    token = make_token(client, bearer(client), scope="read").json()["token"]

    assert me(client, token).status_code == 200
    changed = client.patch("/api/users/me", json={"fullName": "J"}, headers=auth(token))
    assert changed.status_code == 403
    assert "read" in changed.json()["detail"]


def test_a_token_stops_when_revoked_when_expired_or_when_the_user_is_disabled(client):
    make_user()
    make_user("root", admin=True)
    headers = bearer(client)

    first = make_token(client, headers).json()
    assert (
        client.delete(
            f"/api/users/me/tokens/{first['id']}", headers=headers
        ).status_code
        == 204
    )
    assert me(client, first["token"]).status_code == 401
    assert (
        client.delete(
            f"/api/users/me/tokens/{first['id']}", headers=headers
        ).status_code
        == 404
    )

    expiring = make_token(client, headers, expiresDays=1).json()
    from fake_api_db import exposed_functions

    record = exposed_functions.ACCESS_TOKENS[expiring["id"]]
    exposed_functions.ACCESS_TOKENS[expiring["id"]] = record.model_copy(
        update={
            "expires_when": datetime.datetime.now(datetime.UTC)
            - datetime.timedelta(seconds=1)
        }
    )
    assert me(client, expiring["token"]).status_code == 401

    disabled = make_token(client, headers).json()
    asyncio.run(service.set_disabled("john", True))
    assert me(client, disabled["token"]).status_code == 401


def test_a_token_belongs_to_its_user(client):
    make_user()
    make_user("jane")
    mine = make_token(client, bearer(client, "john")).json()

    assert (
        client.get("/api/users/me/tokens", headers=bearer(client, "jane")).json() == []
    )
    assert (
        client.delete(
            f"/api/users/me/tokens/{mine['id']}", headers=bearer(client, "jane")
        ).status_code
        == 404
    )
    assert me(client, mine["token"]).status_code == 200


def test_tokens_are_not_made_with_a_token_and_need_a_login(client):
    make_user()
    token = make_token(client, bearer(client)).json()["token"]

    assert make_token(client, auth(token)).status_code == 403
    assert make_token(client, {}).status_code == 401
    assert make_token(client, bearer(client), scope="admin").status_code == 422
    assert (
        client.post(
            "/api/users/me/tokens", json={"name": " "}, headers=bearer(client)
        ).status_code
        == 422
    )


def test_logout_everywhere_leaves_personal_access_tokens(client):
    make_user()
    headers = bearer(client)
    token = make_token(client, headers).json()["token"]
    client.post("/api/users/me/logout-all", headers=headers)
    assert me(client, token).status_code == 200


# --- when a token was last used -------------------------------------------------------------


def test_a_token_notes_when_it_was_last_used_not_on_every_request(client):
    make_user()
    headers = bearer(client)
    created = make_token(client, headers).json()
    assert created["lastUsedWhen"] is None

    assert me(client, created["token"]).status_code == 200
    first = client.get("/api/users/me/tokens", headers=headers).json()[0][
        "lastUsedWhen"
    ]
    assert first is not None

    # (a second use soon after is not written)
    assert me(client, created["token"]).status_code == 200
    assert (
        client.get("/api/users/me/tokens", headers=headers).json()[0]["lastUsedWhen"]
        == first
    )


# --- guessing at a password -------------------------------------------------------------------


def attempt(client, password, username="john"):
    return client.post(
        "/api/users/token", data={"username": username, "password": password}
    )


def test_a_username_is_refused_after_too_many_wrong_passwords(client, settings):
    make_user()
    for _ in range(settings.LOGIN_MAX_FAILURES):
        assert attempt(client, "wrong").status_code == 401

    refused = attempt(client, PASSWORD)  # (even the right one: that is the point)
    assert refused.status_code == 429
    assert int(refused.headers["Retry-After"]) > 0
    # (the session login is refused too; another username is not affected)
    session = client.post(
        "/api/users/session", data={"username": "john", "password": PASSWORD}
    )
    assert session.status_code == 429
    assert attempt(client, "x", username="nobody").status_code == 401


def test_a_right_password_clears_the_count(client, settings):
    make_user()
    for _ in range(settings.LOGIN_MAX_FAILURES - 1):
        attempt(client, "wrong")
    assert attempt(client, PASSWORD).status_code == 200
    for _ in range(settings.LOGIN_MAX_FAILURES - 1):
        assert attempt(client, "wrong").status_code == 401
    assert attempt(client, PASSWORD).status_code == 200


def test_failures_out_of_the_window_do_not_count(client, settings, monkeypatch):
    from pangloss_api import throttle

    make_user()
    for _ in range(settings.LOGIN_MAX_FAILURES):
        attempt(client, "wrong")
    assert attempt(client, PASSWORD).status_code == 429

    now = throttle.time.monotonic()
    later = now + settings.LOGIN_FAILURE_WINDOW_SECONDS + 1
    monkeypatch.setattr(throttle.time, "monotonic", lambda: later)
    assert attempt(client, PASSWORD).status_code == 200


def test_limiting_can_be_turned_off(client, settings):
    make_user()
    settings.LOGIN_MAX_FAILURES = 0
    for _ in range(15):
        assert attempt(client, "wrong").status_code == 401
    assert attempt(client, PASSWORD).status_code == 200


def test_guesses_at_many_usernames_do_not_grow_the_record_without_end(monkeypatch):
    from collections import defaultdict, deque

    from pangloss_api import throttle

    monkeypatch.setattr(throttle, "MAX_USERNAMES", 3)
    # (the record is shared by every test of the process: start from an empty one)
    monkeypatch.setattr(throttle, "FAILURES", defaultdict(deque))
    now = [1000.0]
    monkeypatch.setattr(throttle.time, "monotonic", lambda: now[0])
    for name in ("a", "b", "c"):
        throttle.failed(name)
    # (once the window has passed, the old ones are dropped to make room)
    now[0] += 301
    throttle.failed("d")
    assert set(throttle.FAILURES) == {"d"}
