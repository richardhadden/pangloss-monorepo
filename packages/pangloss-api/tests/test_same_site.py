"""A cookie session is used only from the API's own site, or from one of `BACKEND_CORS_ORIGINS`: a write that a browser
made from another site with the cookies (a cross-site request forgery) is refused, as is a login or logout from there.
A read is not, nor is anything with the token in the `Authorization` header (which another site cannot add)."""

import asyncio

from fastapi.testclient import TestClient
from pangloss_api import create_app
from pangloss_api.dependencies import (
    ACCESS_COOKIE_NAME,
    REFRESH_COOKIE_NAME,
    REFRESH_COOKIE_PATH,
)
from pangloss_api.tokens import create_token
from pangloss_users import service

from conftest import PASSWORD

ELSEWHERE = "http://evil.example"
FRONTEND = "http://frontend.example"
CROSS_SITE = {"Origin": ELSEWHERE, "Sec-Fetch-Site": "cross-site"}


def make_user() -> None:
    asyncio.run(service.create_user("john", "john@example.com", PASSWORD))


def log_in(client: TestClient) -> None:
    response = client.post(
        "/api/users/session", data={"username": "john", "password": PASSWORD}
    )
    assert response.status_code == 200


def test_a_cross_site_write_with_the_cookie_is_refused(client):
    make_user()
    log_in(client)
    for headers in (CROSS_SITE, {"Origin": ELSEWHERE}, {"Origin": "null"}):
        response = client.patch(
            "/api/users/me", json={"fullName": "Forged"}, headers=headers
        )
        assert response.status_code == 403, headers
        assert "another site" in response.json()["detail"]
    assert client.get("/api/users/me").json()["fullName"] is None


def test_reads_and_same_site_writes_go_through(client):
    make_user()
    log_in(client)
    # (reading is open anyway)
    assert client.get("/api/users/me", headers=CROSS_SITE).status_code == 200
    same = (
        {"Sec-Fetch-Site": "same-origin"},
        {"Sec-Fetch-Site": "same-site", "Origin": "http://api.testserver"},
        {"Sec-Fetch-Site": "none"},
        {"Origin": "http://testserver"},  # (the API's own host, an older browser)
        {},  # (not a browser)
    )
    for headers in same:
        response = client.patch(
            "/api/users/me", json={"fullName": "John"}, headers=headers
        )
        assert response.status_code == 200, headers


def test_an_allowed_origin_may_write_with_the_cookie(settings):
    settings.BACKEND_CORS_ORIGINS = [FRONTEND]
    client = TestClient(create_app())
    make_user()
    log_in(client)
    response = client.patch(
        "/api/users/me",
        json={"fullName": "John"},
        headers={"Origin": FRONTEND, "Sec-Fetch-Site": "cross-site"},
    )
    assert response.status_code == 200
    assert client.patch("/api/users/me", json={}, headers=CROSS_SITE).status_code == 403


def test_the_authorization_header_is_not_a_cookie(client):
    make_user()
    token = create_token("john", "access")
    response = client.patch(
        "/api/users/me",
        json={"fullName": "John"},
        headers={**CROSS_SITE, "Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200


def test_logging_in_and_out_from_another_site_is_refused(client):
    make_user()
    login = client.post(
        "/api/users/session",
        data={"username": "john", "password": PASSWORD},
        headers=CROSS_SITE,
    )
    assert login.status_code == 403
    assert not login.headers.get_list("set-cookie")
    # (tokens are for whoever asks: they are not kept by the browser)
    assert (
        client.post(
            "/api/users/token",
            data={"username": "john", "password": PASSWORD},
            headers=CROSS_SITE,
        ).status_code
        == 200
    )

    log_in(client)
    assert (
        client.post("/api/users/session/refresh", headers=CROSS_SITE).status_code == 403
    )
    assert client.delete("/api/users/session", headers=CROSS_SITE).status_code == 403
    assert client.get("/api/users/me").status_code == 200


def test_the_refresh_cookie_is_only_sent_to_the_session_routes(client):
    make_user()
    response = client.post(
        "/api/users/session", data={"username": "john", "password": PASSWORD}
    )
    cookies = {
        cookie.split("=")[0]: cookie
        for cookie in response.headers.get_list("set-cookie")
    }
    assert "Path=/;" in cookies[ACCESS_COOKIE_NAME] or cookies[
        ACCESS_COOKIE_NAME
    ].endswith("Path=/")
    assert f"Path={REFRESH_COOKIE_PATH}" in cookies[REFRESH_COOKIE_NAME]

    ended = client.delete("/api/users/session")
    cleared = {
        cookie.split("=")[0]: cookie for cookie in ended.headers.get_list("set-cookie")
    }
    assert f"Path={REFRESH_COOKIE_PATH}" in cleared[REFRESH_COOKIE_NAME]
