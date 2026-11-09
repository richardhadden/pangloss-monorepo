"""`/api/admin`: the jobs, for admins only.

    GET    /api/admin/jobs                     what jobs there are, with their options, and the latest jobs
    POST   /api/admin/jobs                     start one: {"kind": ..., "options": {...}} (409 if one of the kind is running)
    POST   /api/admin/jobs/{id}/cancel
    DELETE /api/admin/jobs/{id}                the job and its files (409 while it is running)
    GET    /api/admin/jobs/{id}/files/{name}   download what it made

The routes are plain functions, so that their files are read on FastAPI's threads and not on the event loop.
"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse
from pangloss_api.dependencies import CurrentAdmin
from pangloss_core import settings as core_settings
from pydantic import BaseModel

from pangloss_admin import store as job_store
from pangloss_admin.kinds import JobKind, job_kinds
from pangloss_admin.store import JobConflict, JobStore, jobs_directory

router = APIRouter(prefix="/api/admin", tags=["admin"])


class NewJob(BaseModel):
    kind: str
    options: dict[str, Any] = {}


def _kinds() -> dict[str, JobKind]:
    return job_kinds(core_settings.SETTINGS.INSTALLED_APPS)


def _store() -> JobStore:
    return JobStore(jobs_directory(core_settings.SETTINGS))


def _public(job: dict[str, Any]) -> dict[str, Any]:
    """In the API's case. (Only the job's own keys: the names of its options are the job's business)"""
    return {
        "id": job["id"],
        "kind": job["kind"],
        "options": job["options"],
        "state": job["state"],
        "cancelling": job.get("cancelling", False),
        "createdBy": job["created_by"],
        "createdWhen": job["created_when"],
        "startedWhen": job["started_when"],
        "finishedWhen": job["finished_when"],
        "step": job["step"],
        "steps": job["steps"],
        "current": job["current"],
        "counts": job["counts"],
        "error": job["error"],
        "files": job["files"],
    }


@router.get("/jobs", operation_id="admin_jobs")
def list_jobs(admin: CurrentAdmin) -> dict[str, Any]:
    return {
        "kinds": [kind.describe() for kind in _kinds().values()],
        "jobs": [_public(job) for job in _store().recent()],
    }


@router.post("/jobs", status_code=201, operation_id="admin_start_job")
def start_job(body: NewJob, admin: CurrentAdmin) -> dict[str, Any]:
    kind = _kinds().get(body.kind)
    if kind is None:
        raise HTTPException(422, detail=f"There is no job {body.kind}")
    try:
        options = kind.checked_options(body.options)
    except ValueError as error:
        raise HTTPException(422, detail=str(error)) from None
    store = _store()
    try:
        job = store.create(kind.name, options, admin.username)
    except JobConflict as error:
        raise HTTPException(409, detail=str(error)) from None
    # (through the module, so that the tests can put something else in its place)
    job_store.launch(store, job["id"])
    return _public(job)


@router.post("/jobs/{job_id}/cancel", operation_id="admin_cancel_job")
def cancel_job(job_id: UUID, admin: CurrentAdmin) -> dict[str, Any]:
    store = _store()
    if store.read(str(job_id)) is None:
        raise HTTPException(404, detail="There is no such job")
    try:
        return _public(store.cancel(str(job_id)))
    except JobConflict as error:
        raise HTTPException(409, detail=str(error)) from None


@router.delete("/jobs/{job_id}", status_code=204, operation_id="admin_delete_job")
def delete_job(job_id: UUID, admin: CurrentAdmin) -> None:
    try:
        _store().delete(str(job_id))
    except JobConflict as error:
        raise HTTPException(409, detail=str(error)) from None


@router.get("/jobs/{job_id}/files/{name}", operation_id="admin_job_file")
def download(job_id: UUID, name: str, admin: CurrentAdmin) -> FileResponse:
    path = _store().file_path(str(job_id), name)
    if path is None:
        raise HTTPException(404, detail="There is no such file")
    # (`identity`: the API's gzip middleware leaves it alone, as it would otherwise compress gigabytes as it sends them)
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=name,
        headers={"Content-Encoding": "identity"},
    )


def configure_app(app: FastAPI, settings: Any) -> None:
    """What is wrong with a declared job is found as the server starts"""
    job_kinds(settings.INSTALLED_APPS)
