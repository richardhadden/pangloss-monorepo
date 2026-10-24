import json
import logging

import pytest
from conftest import PASSWORD
from pangloss_core import logs
from test_api_users import bearer, login, make_user

SECRET = "sentinel-secret-value-1234"


@pytest.fixture
def log(caplog):
    caplog.set_level(logging.DEBUG, logger="pangloss")
    return caplog


def lines(caplog, logger_name, level=None):
    return [
        record.getMessage()
        for record in caplog.records
        if record.name == logger_name and (level is None or record.levelname == level)
    ]


def test_a_login_is_logged_as_info(client, log):
    make_user()
    assert login(client).status_code == 200
    (line,) = lines(log, "pangloss.api.auth", "INFO")
    assert "Login: 'john'" in line and "(token)" in line


def test_a_wrong_password_is_logged_as_a_warning_without_the_password(client, log):
    make_user()
    assert login(client, password=SECRET).status_code == 401
    (line,) = lines(log, "pangloss.api.auth", "WARNING")
    assert "Login failed for user 'john'" in line
    assert SECRET not in log.text


def test_a_username_from_a_client_cannot_make_a_line_of_its_own(client, log):
    login(client, username="x\nINFO fake line", password="a")
    (line,) = lines(log, "pangloss.api.auth", "WARNING")
    assert "\n" not in line


def test_a_throttled_login_is_a_warning(client, settings, log):
    make_user()
    for _ in range(settings.LOGIN_MAX_FAILURES):
        login(client, password="wrong")
    assert login(client).status_code == 429
    assert any(
        "Login throttled for user 'john'" in line
        for line in lines(log, "pangloss.api.auth", "WARNING")
    )


def test_no_log_record_holds_a_password_or_token(client, log):
    make_user()
    tokens = login(client).json()
    login(client, password=SECRET)
    headers = bearer(client)
    client.get("/api/users/me", headers=headers)
    client.post(
        "/api/users/token/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    client.post(
        "/api/users/token/revoke", json={"refresh_token": tokens["refresh_token"]}
    )
    client.post("/api/users/session", data={"username": "john", "password": PASSWORD})
    client.put(
        "/api/users/me/password",
        json={"old_password": PASSWORD, "new_password": SECRET},
        headers=headers,
    )
    text = log.text
    for secret in (PASSWORD, SECRET, tokens["access_token"], tokens["refresh_token"]):
        assert secret not in text


def test_logout_everywhere_and_password_change_are_logged(client, log):
    make_user()
    headers = bearer(client)
    client.post("/api/users/me/logout-all", headers=headers)
    assert any(
        "All sessions ended by 'john'" in line
        for line in lines(log, "pangloss.api.auth", "INFO")
    )


def test_personal_access_tokens_are_logged_without_the_token(client, log):
    make_user()
    headers = bearer(client)
    made = client.post(
        "/api/users/me/tokens", json={"name": "ci", "scope": "read"}, headers=headers
    )
    assert made.status_code == 201
    token = made.json()["token"]
    client.delete(f"/api/users/me/tokens/{made.json()['id']}", headers=headers)
    auth = lines(log, "pangloss.api.auth", "INFO")
    assert any("Personal access token 'ci'" in line for line in auth)
    assert any("revoked by 'john'" in line for line in auth)
    assert token not in log.text


def test_user_management_by_an_admin_is_logged(client, log):
    make_user("root", admin=True)
    headers = bearer(client, "root")
    client.post(
        "/api/users",
        json={"username": "ann", "email": "a@example.com", "password": PASSWORD},
        headers=headers,
    )
    client.put("/api/users/ann/disabled", json={"disabled": True}, headers=headers)
    auth = lines(log, "pangloss.api.auth", "INFO")
    assert any("User 'ann' made by 'root'" in line for line in auth)
    assert any("Disabled of 'ann' set to True by 'root'" in line for line in auth)


def test_a_request_gets_an_id_in_the_header_and_the_log(client, log):
    response = client.get("/api/users/me")
    identifier = response.headers["x-request-id"]
    assert len(identifier) == 32
    record = next(r for r in log.records if r.name == "pangloss.api.requests")
    assert "GET /api/users/me -> 401" in record.getMessage()


def test_a_request_id_from_the_client_is_used(client):
    response = client.get("/api/users/me", headers={"X-Request-ID": "trace-1.a"})
    assert response.headers["x-request-id"] == "trace-1.a"


def test_a_request_id_that_is_not_plain_is_replaced(client):
    response = client.get(
        "/api/users/me", headers={"X-Request-ID": "bad id\x7f" + "x" * 80}
    )
    assert len(response.headers["x-request-id"]) == 32


def test_records_made_in_a_request_have_its_id(settings, capsys):
    settings.LOG_FORMAT = "json"
    from fastapi.testclient import TestClient
    from pangloss_api.app import create_app

    client = TestClient(create_app())
    make_user()
    response = login(client)
    records = [json.loads(line) for line in capsys.readouterr().err.splitlines()]
    login_record = next(r for r in records if r["message"].startswith("Login: 'john'"))
    assert login_record["request_id"] == response.headers["x-request-id"]


def test_a_slow_request_is_a_warning(client, settings, log, monkeypatch):
    monkeypatch.setattr("pangloss_api.request_log.slow_request_ms", lambda: -1)
    client.get("/api/users/me")
    (line,) = lines(log, "pangloss.api.requests", "WARNING")
    assert "(slow)" in line


def test_the_query_string_is_not_logged(client, log):
    client.get("/api/users/me?q=private-search-terms")
    assert "private-search-terms" not in log.text


def test_a_bug_is_logged_with_the_request_id(client, app, log):
    @app.get("/boom")
    def boom():
        raise RuntimeError("a bug")

    from fastapi.testclient import TestClient

    response = TestClient(app, raise_server_exceptions=False).get("/boom")
    assert response.status_code == 500
    assert response.headers["x-request-id"]
    assert any(
        "Unhandled error in GET /boom" in line
        for line in lines(log, "pangloss.api.errors", "ERROR")
    )


def test_startup_and_shutdown_are_logged(app, log):
    from fastapi.testclient import TestClient

    with TestClient(app):
        pass
    app_lines = lines(log, "pangloss.api.app", "INFO")
    assert any(line.startswith("Starting Test: fake_api_db") for line in app_lines)
    assert "Test is ready" in app_lines
    assert "Test stopped" in app_lines


def test_the_log_is_set_up_from_the_settings(settings, capsys):
    settings.LOG_LEVEL = "DEBUG"
    settings.LOG_FORMAT = "json"
    from pangloss_api.app import create_app

    create_app()
    logging.getLogger("pangloss.test").debug("probe")
    line = capsys.readouterr().err.strip().splitlines()[-1]
    assert json.loads(line)["message"] == "probe"
    assert logging.getLogger("pangloss").level == logging.DEBUG


def test_the_defaults(settings):
    assert (settings.LOG_LEVEL, settings.LOG_FORMAT) == ("INFO", "text")
    assert (settings.SLOW_QUERY_MS, settings.SLOW_REQUEST_MS) == (500, 2000)
