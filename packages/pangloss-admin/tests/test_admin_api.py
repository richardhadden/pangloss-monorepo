"""The routes: all for admins only"""

from types import SimpleNamespace
from uuid import uuid4

import pangloss_admin.api as admin_api
import pangloss_core.settings as core_settings
import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pangloss_admin import Flag, JobKind
from pangloss_admin import store as job_store
from pangloss_admin.store import JobStore
from pangloss_api.dependencies import get_current_user


async def nothing(context):
    pass


KIND = JobKind("a_job", nothing, options=(Flag("deep"),))


def user(admin: bool):
    return SimpleNamespace(username="someone", admin=admin, disabled=False)


@pytest.fixture
def launched(monkeypatch, tmp_path):
    monkeypatch.setitem(
        core_settings.__dict__,
        "SETTINGS",
        SimpleNamespace(INSTALLED_APPS=[], ADMIN_JOBS_DIRECTORY=str(tmp_path / "jobs")),
    )
    monkeypatch.setattr(admin_api, "_kinds", lambda: {"a_job": KIND})
    calls = []
    monkeypatch.setattr(job_store, "launch", lambda store, job_id: calls.append(job_id))
    return calls


def client(admin: bool) -> TestClient:
    app = FastAPI()
    app.include_router(admin_api.router)
    app.dependency_overrides[get_current_user] = lambda: user(admin)
    return TestClient(app)


@pytest.fixture
def store(launched, tmp_path):
    return JobStore(tmp_path / "jobs")


def finished(store, job_id, name="out.nq"):
    store.files(job_id).mkdir(exist_ok=True)
    (store.files(job_id) / name).write_text("data")
    store.write(
        {
            **store.read_raw(job_id),
            "state": "finished",
            "files": [{"name": name, "size": 4}],
        }
    )


@pytest.mark.parametrize(
    "route",
    [r for r in admin_api.router.routes if isinstance(r, APIRoute)],
    ids=lambda r: r.operation_id,
)
def test_every_route_refuses_someone_who_is_not_an_admin(route, launched):
    method = next(iter(route.methods))
    path = route.path.replace("{job_id}", str(uuid4())).replace("{name}", "x")
    response = client(False).request(method, path, json={"kind": "a_job"})
    assert response.status_code == 403


def test_a_login_is_needed(launched):
    app = FastAPI()
    app.include_router(admin_api.router)
    assert TestClient(app).get("/api/admin/jobs").status_code == 401


def test_starting_a_job(launched):
    api = client(True)
    made = api.post(
        "/api/admin/jobs", json={"kind": "a_job", "options": {"deep": True}}
    )
    assert made.status_code == 201
    job = made.json()
    assert job["options"] == {"deep": True}
    assert job["createdBy"] == "someone"
    assert launched == [job["id"]]

    listing = api.get("/api/admin/jobs").json()
    assert listing["kinds"] == [
        {
            "name": "a_job",
            "options": [{"name": "deep", "type": "flag", "default": False}],
        }
    ]
    assert [j["id"] for j in listing["jobs"]] == [job["id"]]

    assert api.post("/api/admin/jobs", json={"kind": "a_job"}).status_code == 409
    assert len(launched) == 1


@pytest.mark.parametrize(
    "body", [{"kind": "other"}, {"kind": "a_job", "options": {"deep": "no"}}]
)
def test_a_wrong_job_or_option_is_refused(body, launched):
    assert client(True).post("/api/admin/jobs", json=body).status_code == 422
    assert launched == []


def test_downloading_what_a_job_made(store):
    api = client(True)
    job = store.create("a_job", {}, "me")
    finished(store, job["id"])
    got = api.get(f"/api/admin/jobs/{job['id']}/files/out.nq")
    assert got.status_code == 200
    assert got.content == b"data"
    assert "attachment" in got.headers["content-disposition"]
    assert got.headers["content-encoding"] == "identity"
    for name in ("job.json", "..%2Fjob.json", "log.txt"):
        assert api.get(f"/api/admin/jobs/{job['id']}/files/{name}").status_code == 404


def test_cancel_and_delete(store):
    api = client(True)
    job = store.create("a_job", {}, "me")
    assert api.delete(f"/api/admin/jobs/{job['id']}").status_code == 409
    assert api.post(f"/api/admin/jobs/{job['id']}/cancel").status_code == 200
    assert api.get("/api/admin/jobs").json()["jobs"][0]["cancelling"] is True
    store.write({**store.read_raw(job["id"]), "state": "cancelled"})
    assert api.post(f"/api/admin/jobs/{job['id']}/cancel").status_code == 409
    assert api.delete(f"/api/admin/jobs/{job['id']}").status_code == 204
    assert api.get("/api/admin/jobs").json()["jobs"] == []
    assert api.post(f"/api/admin/jobs/{uuid4()}/cancel").status_code == 404
