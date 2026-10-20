from fastapi import FastAPI
from fastapi.testclient import TestClient
from pangloss_interface.api import router

client = TestClient(FastAPI())
client.app.include_router(router)  # type: ignore[union-attr]


def test_health():
    assert client.get("/api/interface/health").json() == {"status": "ok"}


def test_sessions_are_not_implemented_yet():
    for method in ("post", "get", "delete"):
        assert getattr(client, method)("/api/interface/session").status_code == 501


def test_the_js_is_where_the_commands_expect():
    from pangloss_interface.paths import APP_PATH, CORE_PATH, JS_ROOT

    for path in (JS_ROOT / "package.json", APP_PATH / "package.json", CORE_PATH / "package.json"):
        assert path.is_file(), path
