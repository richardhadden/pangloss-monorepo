import asyncio

from conftest import PASSWORD
from pangloss_api.dependencies import (
    ACCESS_COOKIE_NAME,
    REFRESH_COOKIE_NAME,
    CurrentUser,
)
from pangloss_api.tokens import create_token
from pangloss_users import current_request_username, service


def make_user(username="john", email=None, admin=False, **kwargs):
    return asyncio.run(
        service.create_user(
            username=username,
            email=email or f"{username}@example.com",
            password=PASSWORD,
            admin=admin,
            **kwargs,
        )
    )


def login(client, username="john", password=PASSWORD):
    return client.post(
        "/api/users/token", data={"username": username, "password": password}
    )


def bearer(client, username="john") -> dict:
    token = login(client, username).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Logging in
# ---------------------------------------------------------------------------


def test_get_tokens(client):
    make_user()
    response = login(client)
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 30 * 60
    assert body["access_token"] and body["refresh_token"]
    assert body["access_token"] != body["refresh_token"]


def test_bad_logins_all_look_the_same(client):
    make_user()
    make_user("jane")
    asyncio.run(service.set_disabled("jane", True))

    responses = [
        login(client, password="wrong password"),
        login(client, username="nobody"),
        login(client, username="jane"),
    ]
    assert {r.status_code for r in responses} == {401}
    assert len({r.json()["detail"] for r in responses}) == 1


def test_current_user_with_a_bearer_token(client):
    make_user(full_name="John Smith")
    response = client.get("/api/users/me", headers=bearer(client))
    assert response.status_code == 200
    assert response.json()["username"] == "john"
    assert response.json()["fullName"] == "John Smith"
    # never the password, or its hash
    assert "password" not in str(response.json()).lower()


def test_no_token_or_a_bad_one(client):
    make_user()
    assert client.get("/api/users/me").status_code == 401
    for header in ("Bearer nonsense", "Basic am9objpwYXNz", "nonsense"):
        response = client.get("/api/users/me", headers={"Authorization": header})
        assert response.status_code == 401


def test_a_refresh_token_is_not_an_access_token(client):
    make_user()
    refresh = login(client).json()["refresh_token"]
    response = client.get(
        "/api/users/me", headers={"Authorization": f"Bearer {refresh}"}
    )
    assert response.status_code == 401


def test_an_expired_token(client, settings):
    make_user()
    settings.AUTH_ACCESS_TOKEN_EXPIRE_MINUTES = -1
    response = client.get("/api/users/me", headers=bearer(client))
    assert response.status_code == 401


def test_a_token_for_a_user_who_no_longer_exists(client):
    token = create_token("ghost", "access")
    response = client.get("/api/users/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_disabling_a_user_stops_their_token_at_once(client):
    make_user()
    headers = bearer(client)
    assert client.get("/api/users/me", headers=headers).status_code == 200
    asyncio.run(service.set_disabled("john", True))
    assert client.get("/api/users/me", headers=headers).status_code == 401


def test_refresh_token(client):
    make_user()
    tokens = login(client).json()

    response = client.post(
        "/api/users/token/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert response.status_code == 200
    new = response.json()
    assert new["token_type"] == "bearer"
    me = client.get(
        "/api/users/me", headers={"Authorization": f"Bearer {new['access_token']}"}
    )
    assert me.status_code == 200

    # an access token is not a refresh token
    response = client.post(
        "/api/users/token/refresh", json={"refresh_token": tokens["access_token"]}
    )
    assert response.status_code == 401

    # nor does a disabled user get a new one
    asyncio.run(service.set_disabled("john", True))
    response = client.post(
        "/api/users/token/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert response.status_code == 401


def test_the_user_is_recorded_as_the_one_making_the_request(app, client):
    make_user()

    @app.get("/test/whoami")
    async def whoami(user: CurrentUser):
        return {"recorded": current_request_username.get()}

    response = client.get("/test/whoami", headers=bearer(client))
    assert response.json() == {"recorded": "john"}


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


def test_session(client):
    make_user()
    response = client.post(
        "/api/users/session", data={"username": "john", "password": PASSWORD}
    )
    assert response.status_code == 200
    set_cookies = response.headers.get_list("set-cookie")
    assert len(set_cookies) == 2
    for cookie in set_cookies:
        assert "HttpOnly" in cookie
        assert "SameSite=lax" in cookie

    # (the client keeps the cookies)
    assert client.get("/api/users/me").json()["username"] == "john"

    assert client.post("/api/users/session/refresh").status_code == 200
    assert client.get("/api/users/me").status_code == 200

    assert client.delete("/api/users/session").status_code == 200
    client.cookies.clear()
    assert client.get("/api/users/me").status_code == 401


def test_session_with_wrong_password(client):
    make_user()
    response = client.post(
        "/api/users/session", data={"username": "john", "password": "wrong password"}
    )
    assert response.status_code == 401
    assert not response.headers.get_list("set-cookie")


def test_session_refresh_needs_the_refresh_cookie(client):
    make_user()
    assert client.post("/api/users/session/refresh").status_code == 401

    # an access token in its place is no good
    client.cookies.set(REFRESH_COOKIE_NAME, create_token("john", "access"))
    assert client.post("/api/users/session/refresh").status_code == 401


def test_secure_cookies(client, settings):
    make_user()
    settings.AUTH_COOKIE_SAMESITE = "none"
    response = client.post(
        "/api/users/session", data={"username": "john", "password": PASSWORD}
    )
    for cookie in response.headers.get_list("set-cookie"):
        assert "SameSite=none" in cookie
        assert "Secure" in cookie
    assert ACCESS_COOKIE_NAME in response.headers["set-cookie"]


# ---------------------------------------------------------------------------
# The user themselves
# ---------------------------------------------------------------------------


def test_update_me(client):
    make_user()
    response = client.patch(
        "/api/users/me",
        json={"fullName": "John Smith", "email": "js@example.com"},
        headers=bearer(client),
    )
    assert response.status_code == 200
    assert response.json()["fullName"] == "John Smith"
    assert response.json()["email"] == "js@example.com"

    # (can't make oneself an admin this way)
    response = client.patch(
        "/api/users/me", json={"admin": True}, headers=bearer(client)
    )
    assert response.json()["admin"] is False


def test_update_me_with_an_email_in_use(client):
    make_user()
    make_user("jane")
    response = client.patch(
        "/api/users/me", json={"email": "jane@example.com"}, headers=bearer(client)
    )
    assert response.status_code == 409


def test_change_my_password(client):
    make_user()
    headers = bearer(client)

    response = client.put(
        "/api/users/me/password",
        json={"oldPassword": "wrong password", "newPassword": "a new password"},
        headers=headers,
    )
    assert response.status_code == 422

    response = client.put(
        "/api/users/me/password",
        json={"oldPassword": PASSWORD, "newPassword": "short"},
        headers=headers,
    )
    assert response.status_code == 422

    response = client.put(
        "/api/users/me/password",
        json={"oldPassword": PASSWORD, "newPassword": "a new password"},
        headers=headers,
    )
    assert response.status_code == 200
    assert login(client).status_code == 401
    assert login(client, password="a new password").status_code == 200


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------


def test_only_admins_manage_users(client):
    make_user()
    make_user("root", admin=True)
    headers = bearer(client)

    assert client.get("/api/users", headers=headers).status_code == 403
    assert (
        client.post(
            "/api/users",
            json={"username": "x", "email": "x@example.com", "password": PASSWORD},
            headers=headers,
        ).status_code
        == 403
    )
    for path, body in (("/api/users/root", {"fullName": "Root"}),):
        assert client.patch(path, json=body, headers=headers).status_code == 403
    assert (
        client.put(
            "/api/users/root/password", json={"password": PASSWORD}, headers=headers
        ).status_code
        == 403
    )
    assert (
        client.put(
            "/api/users/john/admin", json={"admin": True}, headers=headers
        ).status_code
        == 403
    )
    assert (
        client.put(
            "/api/users/root/disabled", json={"disabled": True}, headers=headers
        ).status_code
        == 403
    )

    # (nor without logging in)
    assert client.get("/api/users").status_code == 401


def test_list_and_read_users(client):
    make_user()
    make_user("root", admin=True)
    admin = bearer(client, "root")

    users = client.get("/api/users", headers=admin).json()
    assert [u["username"] for u in users] == ["john", "root"]
    assert "hashed_password" not in str(users)

    assert client.get("/api/users/john", headers=admin).json()["username"] == "john"
    assert client.get("/api/users/nobody", headers=admin).status_code == 404

    # An ordinary user can read their own, and nobody else's
    john = bearer(client)
    assert client.get("/api/users/john", headers=john).status_code == 200
    assert client.get("/api/users/root", headers=john).status_code == 403


def test_create_user(client):
    make_user("root", admin=True)
    admin = bearer(client, "root")

    response = client.post(
        "/api/users",
        json={
            "username": "jane",
            "email": "jane@example.com",
            "password": PASSWORD,
            "fullName": "Jane Doe",
        },
        headers=admin,
    )
    assert response.status_code == 201
    assert response.json()["username"] == "jane"
    assert response.json()["admin"] is False
    assert "password" not in str(response.json()).lower()
    assert login(client, "jane").status_code == 200

    response = client.post(
        "/api/users",
        json={
            "username": "boss",
            "email": "boss@example.com",
            "password": PASSWORD,
            "admin": True,
        },
        headers=admin,
    )
    assert response.json()["admin"] is True

    taken = client.post(
        "/api/users",
        json={"username": "jane", "email": "other@example.com", "password": PASSWORD},
        headers=admin,
    )
    assert taken.status_code == 409

    for bad in (
        {"username": "x y", "email": "x@example.com", "password": PASSWORD},
        {"username": "x", "email": "not an email", "password": PASSWORD},
        {"username": "x", "email": "x@example.com", "password": "short"},
    ):
        assert client.post("/api/users", json=bad, headers=admin).status_code == 422


def test_admin_changes_another_user(client):
    make_user()
    make_user("root", admin=True)
    admin = bearer(client, "root")

    response = client.patch(
        "/api/users/john", json={"fullName": "John Smith"}, headers=admin
    )
    assert response.json()["fullName"] == "John Smith"
    assert (
        client.patch(
            "/api/users/nobody", json={"fullName": "N"}, headers=admin
        ).status_code
        == 404
    )

    assert (
        client.put(
            "/api/users/john/password",
            json={"password": "set by an admin"},
            headers=admin,
        ).status_code
        == 200
    )
    assert login(client, password="set by an admin").status_code == 200
    assert (
        client.put(
            "/api/users/john/password", json={"password": "short"}, headers=admin
        ).status_code
        == 422
    )

    response = client.put("/api/users/john/admin", json={"admin": True}, headers=admin)
    assert response.json()["admin"] is True
    response = client.put(
        "/api/users/john/disabled", json={"disabled": True}, headers=admin
    )
    assert response.json()["disabled"] is True
    assert login(client).status_code == 401


def test_admins_cannot_change_their_own_status(client):
    make_user("root", admin=True)
    admin = bearer(client, "root")
    assert (
        client.put(
            "/api/users/root/admin", json={"admin": False}, headers=admin
        ).status_code
        == 400
    )
    assert (
        client.put(
            "/api/users/root/disabled", json={"disabled": True}, headers=admin
        ).status_code
        == 400
    )
    assert client.get("/api/users/me", headers=admin).json()["admin"] is True


def test_the_users_json_is_camel_case(client):
    make_user(full_name="John Smith")
    body = client.get("/api/users/me", headers=bearer(client)).json()
    assert set(body) == {
        "username",
        "email",
        "fullName",
        "admin",
        "disabled",
        "createdWhen",
    }
    assert not any("_" in key for key in body)


def test_the_names_are_accepted_as_well_as_the_camel_case(client):
    make_user()
    make_user("root", admin=True)
    admin = bearer(client, "root")
    response = client.post(
        "/api/users",
        json={
            "username": "jane",
            "email": "jane@example.com",
            "password": PASSWORD,
            "full_name": "Jane Doe",
        },
        headers=admin,
    )
    assert response.status_code == 201
    assert response.json()["fullName"] == "Jane Doe"
    response = client.put(
        "/api/users/me/password",
        json={"old_password": PASSWORD, "new_password": "a new password"},
        headers=bearer(client),
    )
    assert response.status_code == 200


def test_the_token_endpoints_use_the_names_of_oauth2(client):
    make_user()
    body = login(client).json()
    assert set(body) == {"access_token", "refresh_token", "token_type", "expires_in"}
    refreshed = client.post(
        "/api/users/token/refresh", json={"refresh_token": body["refresh_token"]}
    ).json()
    assert set(refreshed) == {"access_token", "token_type", "expires_in"}
