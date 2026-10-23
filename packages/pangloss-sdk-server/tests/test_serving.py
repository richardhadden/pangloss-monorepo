"""The routes of the SDK, and the check of a client's version, with the real app and the
users of the API's fake database"""

import asyncio
import base64
import hashlib
import io
import shutil
import json
import re
import subprocess
import sys
import tarfile
import zipfile

import pytest
from pangloss_core import settings as core_settings
from pangloss_core.settings import BaseSettings, DatabaseSettings
from pangloss_sdk.schemas import schema_hash
from pangloss_sdk_server import archives, check, current
from pangloss_users import service
from pydantic import AnyHttpUrl

from server_support import API_TESTS, write

sys.path.insert(0, str(API_TESTS))
import fake_api_db  # noqa: E402
from fake_api_db import exposed_functions  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from pangloss_api.app import create_app  # noqa: E402

PASSWORD = "correct horse"


def settings_class(root):
    class Settings(BaseSettings[DatabaseSettings]):
        PROJECT_NAME: str = "shop"
        BACKEND_CORS_ORIGINS: list = []
        INSTALLED_APPS: list[str] = ["shop", "pangloss_sdk_server"]
        DATABASE_MODULE: str = "fake_api_db"
        DATABASE: DatabaseSettings = DatabaseSettings()
        AUTHJWT_SECRET_KEY: str = "a secret for the tests, of a decent length"
        ENTITY_BASE_URL: AnyHttpUrl = AnyHttpUrl("http://test.com/")

    return Settings


@pytest.fixture
def make_app(project):
    saved = core_settings.__dict__.get("SETTINGS")
    exposed_functions.USERS.clear()
    exposed_functions.REVOKED.clear()
    exposed_functions.ACCESS_TOKENS.clear()
    current.reset()

    def make(**options):
        # (the SDK's settings are read from the instance, where they may be set as attributes)
        instance = settings_class(project)()
        for key, value in {"SDK_ROOT": str(project), **options}.items():
            object.__setattr__(instance, key, value)
        return create_app()

    yield make
    exposed_functions.USERS.clear()
    exposed_functions.REVOKED.clear()
    exposed_functions.ACCESS_TOKENS.clear()
    current.reset()
    if saved is None:
        core_settings.__dict__.pop("SETTINGS", None)
    else:
        core_settings.SETTINGS = saved


def user(username="ada", admin=False):
    asyncio.run(service.create_user(username, f"{username}@example.com", PASSWORD, admin=admin))
    return username


def bearer(client, username):
    token = client.post(
        "/api/users/token", data={"username": username, "password": PASSWORD}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def basic(username, password=PASSWORD):
    return {"Authorization": "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()}


# --- building and the version --------------------------------------------------------------


def test_the_sdk_is_built_as_the_server_starts_and_its_version_is_public(make_app, project):
    with TestClient(make_app()) as client:
        response = client.get("/api/sdk/version")

    assert response.status_code == 200
    body = response.json()
    assert body["project"] == "shop"
    assert body["distribution"] == "shop-sdk"
    assert body["version"] == "0.1"
    assert body["schemaHash"] == schema_hash(body["schemaPosition"])
    assert (project / ".pangloss/sdk/package/shop/models.py").is_file()


def test_with_building_off_the_last_build_on_disk_is_served_or_there_is_none(make_app, project):
    with TestClient(make_app(SDK_BUILD="off")) as client:
        response = client.get("/api/sdk/version")
    assert response.status_code == 503
    assert "not built" in response.json()["detail"]

    current.reset()
    from pangloss_sdk_server import publish

    publish.build(project, core_settings.SETTINGS)
    current.reset()
    with TestClient(make_app(SDK_BUILD="off")) as client:
        assert client.get("/api/sdk/version").status_code == 200


def test_a_build_that_fails_does_not_stop_the_server_and_says_why(make_app, project):
    write(project, {"shop/helpers.py": "import neo4j\nSHOUT = 1\n"})
    with TestClient(make_app()) as client:
        assert client.get("/api/users/me").status_code == 401  # (the server is up)
        response = client.get("/api/sdk/version")
    assert response.status_code == 503
    assert "neo4j" in response.json()["detail"]


# --- who may get it ------------------------------------------------------------------------


def test_the_sdk_is_for_admins_by_default(make_app):
    with TestClient(make_app()) as client:
        user("ada")
        user("root", admin=True)

        anonymous = client.get("/api/sdk")
        assert anonymous.status_code == 401
        assert anonymous.headers["www-authenticate"].startswith("Basic")

        assert client.get("/api/sdk", headers=bearer(client, "ada")).status_code == 403
        assert client.get("/api/sdk", headers=basic("ada")).status_code == 403
        assert client.get("/api/sdk", headers=bearer(client, "root")).status_code == 200
        assert client.get("/api/sdk", headers=basic("root")).status_code == 200
        assert client.get("/api/sdk", headers=basic("root", "wrong")).status_code == 401


def test_an_access_token_works_as_the_basic_password(make_app):
    with TestClient(make_app()) as client:
        user("root", admin=True)
        token = bearer(client, "root")["Authorization"].removeprefix("Bearer ")
        assert client.get("/api/sdk", headers=basic("root", token)).status_code == 200
        assert client.get("/api/sdk", headers=basic("someone", token)).status_code == 401


def test_the_access_can_be_for_any_user_or_for_everyone(make_app):
    with TestClient(make_app(SDK_ACCESS="user")) as client:
        user("ada")
        assert client.get("/api/sdk").status_code == 401
        assert client.get("/api/sdk", headers=basic("ada")).status_code == 200

    with TestClient(make_app(SDK_ACCESS="public")) as client:
        assert client.get("/api/sdk").status_code == 200


# --- downloads -----------------------------------------------------------------------------


def info(client):
    user("root", admin=True)
    return client.get("/api/sdk", headers=basic("root")).json()


def test_the_manifest_has_the_downloads(make_app):
    with TestClient(make_app(SDK_ACCESS="public")) as client:
        body = client.get("/api/sdk").json()
    assert body["apps"] == ["shop"]
    assert body["downloads"]["wheel"].endswith("/api/sdk/download/shop_sdk-0.1-py3-none-any.whl")
    assert body["downloads"]["sdist"].endswith("/api/sdk/download/shop-sdk-0.1.tar.gz")
    assert body["requires"][0].startswith("pangloss-sdk==")


def test_the_wheel_is_a_valid_wheel_that_works_on_a_clean_client(make_app, tmp_path):
    with TestClient(make_app()) as client:
        body = info(client)
        url = body["downloads"]["wheel"].removeprefix("http://testserver")
        assert client.get(url).status_code == 401
        response = client.get(url, headers=basic("root"))
        again = client.get(url, headers=basic("root"))

    assert response.status_code == 200
    assert response.content == again.content  # (the same bytes: no times)
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    names = set(archive.namelist())
    assert {"shop/models.py", "shop/models.pyi", "shop_sdk/manifest.json"} <= names
    assert "pyproject.toml" not in names
    dist_info = "shop_sdk-0.1.dist-info"
    assert {f"{dist_info}/METADATA", f"{dist_info}/WHEEL", f"{dist_info}/RECORD"} <= names
    metadata = archive.read(f"{dist_info}/METADATA").decode()
    assert "Name: shop-sdk" in metadata and "Requires-Dist: pangloss-sdk==" in metadata

    # (RECORD has the hash and size of every file)
    record = dict(
        (line.split(",")[0], line.split(",")[1:]) for line in archive.read(f"{dist_info}/RECORD").decode().splitlines()
    )
    for name in names - {f"{dist_info}/RECORD"}:
        content = archive.read(name)
        digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode()
        assert record[name] == [f"sha256={digest}", str(len(content))], name

    # (and what is in it is the SDK: it imports, and makes the server's models, on a clean client)
    archive.extractall(tmp_path / "installed")
    schemas = check.run_in_clean_process(tmp_path / "installed", "shop_sdk")
    assert set(schemas) == {"Person", "Statement"}


def test_the_sdist_has_the_source_and_pkg_info(make_app):
    with TestClient(make_app()) as client:
        body = info(client)
        url = body["downloads"]["sdist"].removeprefix("http://testserver")
        response = client.get(url, headers=basic("root"))
        again = client.get(url, headers=basic("root"))

    assert response.content == again.content
    with tarfile.open(fileobj=io.BytesIO(response.content), mode="r:gz") as archive:
        names = set(archive.getnames())
        assert {"shop-sdk-0.1/pyproject.toml", "shop-sdk-0.1/PKG-INFO", "shop-sdk-0.1/shop/models.py"} <= names
        assert b"Name: shop-sdk" in archive.extractfile("shop-sdk-0.1/PKG-INFO").read()  # type: ignore[union-attr]


def test_any_other_file_name_is_not_found(make_app):
    with TestClient(make_app(SDK_ACCESS="public")) as client:
        assert client.get("/api/sdk/download/shop_sdk-0.9-py3-none-any.whl").status_code == 404
        assert client.get("/api/sdk/download/pyproject.toml").status_code == 404


def test_the_archives_have_the_same_names_as_the_manifest():
    manifest = {"distribution": "my-shop-sdk", "version": "0.12"}
    assert archives.wheel_name(manifest) == "my_shop_sdk-0.12-py3-none-any.whl"
    assert archives.sdist_name(manifest) == "my-shop-sdk-0.12.tar.gz"


# --- the client's version ------------------------------------------------------------------


def server_values(client):
    body = client.get("/api/sdk/version").json()
    return body["fingerprint"], body["schemaHash"]


def test_the_status_of_a_clients_sdk_is_in_the_answer(make_app):
    with TestClient(make_app()) as client:
        fingerprint, schema = server_values(client)
        sdk = "X-Pangloss-SDK"

        assert "x-pangloss-sdk-status" not in client.get("/api/users/me").headers

        same = client.get("/api/users/me", headers={sdk: fingerprint, "X-Pangloss-Schema": schema})
        assert same.headers["x-pangloss-sdk-status"] == "current"

        other_package = client.get("/api/users/me", headers={sdk: "0" * 64, "X-Pangloss-Schema": schema})
        assert other_package.headers["x-pangloss-sdk-status"] == "stale"

        moved_on = client.get("/api/users/me", headers={sdk: fingerprint, "X-Pangloss-Schema": "f" * 16})
        assert moved_on.headers["x-pangloss-sdk-status"] == "schema-changed"
        assert moved_on.status_code != 409  # (a read is never refused)


def test_a_write_from_a_client_whose_schema_has_moved_on_is_refused(make_app):
    old = {"X-Pangloss-SDK": "0" * 64, "X-Pangloss-Schema": "f" * 16}
    with TestClient(make_app()) as client:
        user("ada")
        headers = {**bearer(client, "ada"), **old}

        refused = client.post("/api/Person", json={"type": "Person", "label": "x"}, headers=headers)
        assert refused.status_code == 409
        assert refused.json()["error"] == "PanglossSdkOutOfDate"
        assert refused.headers["x-pangloss-sdk-status"] == "schema-changed"

        # a login, and the SDK itself, are not refused
        login = client.post("/api/users/token", data={"username": "ada", "password": PASSWORD}, headers=old)
        assert login.status_code == 200


def test_stale_writes_can_be_let_through(make_app):
    old = {"X-Pangloss-SDK": "0" * 64, "X-Pangloss-Schema": "f" * 16}
    with TestClient(make_app(SDK_STALE_WRITES="warn")) as client:
        user("ada")
        response = client.post(
            "/api/Person", json={"type": "Person", "label": "x"}, headers={**bearer(client, "ada"), **old}
        )
    assert response.status_code != 409
    assert response.headers["x-pangloss-sdk-status"] == "schema-changed"


@pytest.mark.asyncio
async def test_a_client_with_the_built_manifest_is_current_against_the_app(make_app, project):
    import httpx2 as httpx
    from pangloss_sdk import client as sdk_client
    from pangloss_sdk import check as check_version
    from pangloss_sdk.settings import SdkSettings

    app = make_app()
    await current.ensure_built(core_settings.SETTINGS)
    manifest = json.loads((project / ".pangloss/sdk/package/shop_sdk/manifest.json").read_text())
    server_settings = core_settings.SETTINGS
    sdk_settings = SdkSettings(URL="http://test", INSTALLED_APPS=[])  # type: ignore[arg-type]
    core_settings.SETTINGS = server_settings

    client = sdk_client.AsyncClient(sdk_settings, httpx.ASGITransport(app=app), None, manifest)
    sdk_client.install(client)
    try:
        result = await check_version()
        assert result["current"] is True and result["same_schema"] is True
        await client.send(__import__("pangloss_sdk.protocol", fromlist=["x"]).server_version())
        assert client.observer.status == "current"
    finally:
        sdk_client.install(None)
        await client.close()


# --- a package index (PEP 503) ------------------------------------------------------------------


def test_the_index_lists_the_one_project_and_links_its_files_with_hashes(make_app):
    with TestClient(make_app()) as client:
        user("root", admin=True)
        assert client.get("/api/sdk/simple/").status_code == 401

        root = client.get("/api/sdk/simple/", headers=basic("root"))
        assert root.status_code == 200 and '<a href="shop-sdk/">shop-sdk</a>' in root.text

        # (any spelling pip may use for the name)
        project = client.get("/api/sdk/simple/Shop_SDK/", headers=basic("root"))
        assert project.status_code == 200
        assert client.get("/api/sdk/simple/other/", headers=basic("root")).status_code == 404

        links = re.findall(r'href="([^"#]+)#sha256=([0-9a-f]{64})"', project.text)
        assert [file for file, _ in links] == [
            "../../download/shop_sdk-0.1-py3-none-any.whl",
            "../../download/shop-sdk-0.1.tar.gz",
        ]
        assert "data-requires-python" in project.text
        for link, digest in links:
            # (pip resolves it against the page: /api/sdk/simple/shop-sdk/)
            path = "/api/sdk/" + link.removeprefix("../../")
            content = client.get(path, headers=basic("root")).content
            assert hashlib.sha256(content).hexdigest() == digest


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is not installed")
def test_an_installer_accepts_the_wheel_and_the_installed_package_works(make_app, tmp_path):
    """`uv pip install` reads METADATA, WHEEL and RECORD (no network: the dependencies are not
    fetched, and the check imports with this environment's)"""
    with TestClient(make_app()) as client:
        body = info(client)
        url = body["downloads"]["wheel"].removeprefix("http://testserver")
        wheel = tmp_path / "shop_sdk-0.1-py3-none-any.whl"
        wheel.write_bytes(client.get(url, headers=basic("root")).content)

    target = tmp_path / "installed"
    result = subprocess.run(
        ["uv", "pip", "install", "--no-deps", "--target", str(target), str(wheel)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (target / "shop/models.pyi").is_file()
    assert (target / "shop_sdk/sync_stubs/shop/models.pyi").is_file()
    assert (target / "shop_sdk-0.1.dist-info/METADATA").is_file()
    assert set(check.run_in_clean_process(target, "shop_sdk")) == {"Person", "Statement"}
