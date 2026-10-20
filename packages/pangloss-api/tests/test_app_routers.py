import textwrap

import pytest
from conftest import Settings
from fastapi.testclient import TestClient
from pangloss_api.app import create_app


@pytest.fixture
def apps(tmp_path, monkeypatch):
    """Packages (on the path) that the tests can make installed apps"""
    monkeypatch.syspath_prepend(str(tmp_path))
    names = []

    def make(name: str, files: dict[str, str]):
        for file, content in {"__init__.py": "", **files}.items():
            path = tmp_path / name / file
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(textwrap.dedent(content))
        names.append(name)

    yield make
    import sys

    for module in list(sys.modules):
        if module.split(".")[0] in names:
            del sys.modules[module]


ROUTER = """
    from fastapi import APIRouter

    router = APIRouter(prefix="/api/hello")

    @router.get("/")
    async def hello():
        return {"hello": "world"}
"""


def client_with(*installed: str) -> TestClient:
    Settings(INSTALLED_APPS=list(installed))
    return TestClient(create_app())


def test_an_installed_app_can_add_routes(settings, apps):
    apps("routeapp", {"api.py": ROUTER})
    response = client_with("routeapp").get("/api/hello/")
    assert response.status_code == 200
    assert response.json() == {"hello": "world"}


def test_apps_without_an_api_module_or_router_are_left_alone(settings, apps):
    apps("plain", {})
    apps("norouter", {"api.py": "x = 1"})
    client = client_with("plain", "norouter")
    assert client.get("/api/hello/").status_code == 404


def test_a_router_that_is_not_one_is_an_error(settings, apps):
    apps("badrouter", {"api.py": "router = 3"})
    Settings(INSTALLED_APPS=["badrouter"])
    with pytest.raises(TypeError, match="badrouter.api"):
        create_app()


def test_an_error_inside_the_api_module_is_not_hidden(settings, apps):
    apps("brokenapi", {"api.py": "import module_that_is_not_there"})
    Settings(INSTALLED_APPS=["brokenapi"])
    with pytest.raises(ModuleNotFoundError, match="module_that_is_not_there"):
        create_app()
