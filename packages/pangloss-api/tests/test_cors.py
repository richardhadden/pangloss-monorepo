import pytest
from conftest import PASSWORD, Settings
from fastapi.testclient import TestClient
from pangloss_api.app import create_app
from pangloss_core.settings import (
    BaseSettings,
    DatabaseSettings,
    normalise_cors_origins,
)
from pangloss_users import service
from pydantic import AnyHttpUrl, ValidationError

FRONTEND = "http://localhost:5173"


def client_allowing(*origins) -> TestClient:
    Settings(BACKEND_CORS_ORIGINS=list(origins))
    return TestClient(create_app())


def preflight(
    client, origin=FRONTEND, method="PUT", headers="authorization,content-type"
):
    return client.options(
        "/api/users/me",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": headers,
        },
    )


# ---------------------------------------------------------------------------
# What a browser is told
# ---------------------------------------------------------------------------


def test_an_allowed_origin_may_use_the_api(settings):
    client = client_allowing(FRONTEND)

    response = client.get("/api/users/me", headers={"Origin": FRONTEND})
    assert response.status_code == 401  # (not logged in; the origin is not why)
    assert response.headers["access-control-allow-origin"] == FRONTEND
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "Origin" in response.headers["vary"]


def test_the_preflight_of_a_request_with_a_token(settings):
    client = client_allowing(FRONTEND)
    response = preflight(client)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == FRONTEND
    assert response.headers["access-control-allow-credentials"] == "true"
    for method in ("GET", "POST", "PUT", "PATCH", "DELETE"):
        assert method in response.headers["access-control-allow-methods"]
    allowed = response.headers["access-control-allow-headers"].lower()
    assert "authorization" in allowed
    assert "content-type" in allowed
    assert "if-match" in allowed  # (an update says which version it is based on)
    assert response.headers["access-control-max-age"] == "600"


def test_another_origin_is_not_allowed(settings):
    client = client_allowing(FRONTEND)

    response = client.get("/api/users/me", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in response.headers

    response = preflight(client, origin="http://evil.example")
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers

    # (the origin has to be the whole of it: scheme, host and port)
    for origin in (
        "https://localhost:5173",
        "http://localhost:5174",
        "http://localhost",
    ):
        response = client.get("/api/users/me", headers={"Origin": origin})
        assert "access-control-allow-origin" not in response.headers, origin


def test_several_origins(settings):
    client = client_allowing(FRONTEND, "https://app.example.com")
    for origin in (FRONTEND, "https://app.example.com"):
        response = client.get("/api/users/me", headers={"Origin": origin})
        assert response.headers["access-control-allow-origin"] == origin


def test_errors_and_successes_both_carry_the_headers(settings):
    client = client_allowing(FRONTEND)
    asyncio_run(service.create_user("john", "john@example.com", PASSWORD))

    login = client.post(
        "/api/users/token",
        data={"username": "john", "password": PASSWORD},
        headers={"Origin": FRONTEND},
    )
    assert login.status_code == 200
    assert login.headers["access-control-allow-origin"] == FRONTEND

    wrong = client.post(
        "/api/users/token",
        data={"username": "john", "password": "wrong password"},
        headers={"Origin": FRONTEND},
    )
    assert wrong.status_code == 401
    assert wrong.headers["access-control-allow-origin"] == FRONTEND

    missing = client.get("/api/Nothing", headers={"Origin": FRONTEND})
    assert missing.status_code == 404
    assert missing.headers["access-control-allow-origin"] == FRONTEND


def asyncio_run(coroutine):
    import asyncio

    return asyncio.run(coroutine)


def test_cookies_can_be_used_from_an_allowed_origin(settings):
    client = client_allowing(FRONTEND)
    asyncio_run(service.create_user("john", "john@example.com", PASSWORD))
    response = client.post(
        "/api/users/session",
        data={"username": "john", "password": PASSWORD},
        headers={"Origin": FRONTEND},
    )
    assert response.status_code == 200
    # (a browser only lets the page use the response if it is told credentials may be)
    assert response.headers["access-control-allow-credentials"] == "true"
    assert response.headers["access-control-allow-origin"] == FRONTEND
    me = client.get("/api/users/me", headers={"Origin": FRONTEND})
    assert me.json()["username"] == "john"


# ---------------------------------------------------------------------------
# No origins, and any
# ---------------------------------------------------------------------------


def test_with_no_origins_there_is_no_cors(settings):
    client = TestClient(create_app())
    response = client.get("/api/users/me", headers={"Origin": FRONTEND})
    assert "access-control-allow-origin" not in response.headers
    response = preflight(client)
    assert "access-control-allow-origin" not in response.headers


def test_any_origin_is_allowed_without_credentials_and_with_a_warning(settings):
    with pytest.warns(UserWarning, match="any site"):
        client = client_allowing("*")

    response = client.get(
        "/api/users/me", headers={"Origin": "http://anywhere.example"}
    )
    assert response.headers["access-control-allow-origin"] == "*"
    # (the cookies of a user must not be usable by any site)
    assert "access-control-allow-credentials" not in response.headers
    assert preflight(client, origin="http://anywhere.example").status_code == 200


# ---------------------------------------------------------------------------
# The setting
# ---------------------------------------------------------------------------


def test_origins_are_made_as_a_browser_sends_them():
    assert normalise_cors_origins(["http://localhost:5173/"]) == [
        "http://localhost:5173"
    ]
    assert normalise_cors_origins([AnyHttpUrl("http://localhost:5173")]) == [
        "http://localhost:5173"
    ]
    assert normalise_cors_origins("http://a.com, HTTPS://B.com/ ,") == [
        "http://a.com",
        "https://b.com",
    ]
    assert normalise_cors_origins('["http://a.com/"]') == ["http://a.com"]
    assert normalise_cors_origins("") == []
    assert normalise_cors_origins(["*"]) == ["*"]


@pytest.mark.parametrize(
    "bad", ["http://a.com/app", "localhost:5173", "ftp://a.com", "a.com", 5, "http://"]
)
def test_what_is_not_an_origin_is_refused(bad):
    with pytest.raises(ValueError):
        normalise_cors_origins(bad)


def test_the_setting_is_checked_and_normalised(settings):
    assert Settings(
        BACKEND_CORS_ORIGINS="http://a.com/, http://b.com"
    ).BACKEND_CORS_ORIGINS == [
        "http://a.com",
        "http://b.com",
    ]
    with pytest.raises(ValidationError, match="is not an origin"):
        Settings(BACKEND_CORS_ORIGINS=["http://a.com/some/path"])


def test_the_setting_can_be_given_as_a_comma_separated_environment_variable(
    settings, monkeypatch
):
    class FromEnvironment(BaseSettings[DatabaseSettings]):
        # (BACKEND_CORS_ORIGINS is not declared again, so it is read as it is in the base)
        PROJECT_NAME: str = "Test"
        INSTALLED_APPS: list[str] = []
        DATABASE_MODULE: str = "fake_api_db"
        DATABASE: DatabaseSettings = DatabaseSettings()
        AUTHJWT_SECRET_KEY: str = "a secret for the tests, of a decent length"
        ENTITY_BASE_URL: AnyHttpUrl = AnyHttpUrl("http://test.com/")

    monkeypatch.setenv(
        "BACKEND_CORS_ORIGINS", "http://localhost:5173, https://app.example.com/"
    )
    assert FromEnvironment().BACKEND_CORS_ORIGINS == [
        "http://localhost:5173",
        "https://app.example.com",
    ]
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", '["http://localhost:5173"]')
    assert FromEnvironment().BACKEND_CORS_ORIGINS == ["http://localhost:5173"]


def test_a_server_error_carries_the_headers_too(settings, caplog):
    Settings(BACKEND_CORS_ORIGINS=[FRONTEND])
    app = create_app()

    @app.get("/test/broken")
    async def broken():
        raise RuntimeError("a bug")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/test/broken", headers={"Origin": FRONTEND})
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert response.headers["access-control-allow-origin"] == FRONTEND
    assert "a bug" in caplog.text  # (logged here, as it does not reach the server)


def test_the_etag_can_be_read_by_the_frontend(settings):
    client = client_allowing(FRONTEND)
    asyncio_run(service.create_user("john", "john@example.com", PASSWORD))
    response = client.post(
        "/api/users/token",
        data={"username": "john", "password": PASSWORD},
        headers={"Origin": FRONTEND},
    )
    # (a browser only lets a page read the headers that are exposed)
    assert response.headers["access-control-expose-headers"] == "ETag"
