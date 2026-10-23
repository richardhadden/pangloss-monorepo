"""Endpoints for reading history, under each model: `/api/<Model>/{id}/history`.

(`pangloss-api` includes the routers of installed apps before those of the models, so these
come first: an entity's own route would otherwise take the whole path.)
"""

import inspect
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from pangloss_api.dependencies import get_current_user
from pangloss_api.routes.models import etag, expected_version, routable_models

from pangloss_history import config
from pangloss_history.diff import diff
from pangloss_history.draft import make_draft
from pangloss_history.gaps import find_gaps
from pangloss_history.restore import restore
from pangloss_history.store import HistoryRecord, HistoryStore, SqliteStore

router = APIRouter(
    prefix="/api",
    tags=["history"],
    dependencies=[Depends(get_current_user)],
)

_store: HistoryStore | None = None


def get_store() -> HistoryStore:
    """The store that is read (the same file that the recorder writes)"""
    global _store
    if _store is None:
        _store = SqliteStore(config.db_path())
    return _store


def set_store(store: HistoryStore | None) -> None:
    global _store
    _store = store


Store = Annotated[HistoryStore, Depends(get_store)]


def find_model(name: str) -> type:
    for model in routable_models():
        if model.__name__ == name:
            return model
    raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"There is no model '{name}'")


async def current_version(model: Any, id: UUID) -> int | None:
    """The version of the head node now (None if it is not there, as when deleted)"""
    found = model.get(id)
    view = await found if inspect.isawaitable(found) else found
    return view.meta.version if view is not None else None


def describe(record: HistoryRecord) -> dict[str, Any]:
    return {
        "seq": record.seq,
        "version": record.version,
        "op": record.op,
        "who": record.who,
        "at": record.at.isoformat(),
        "schemaPosition": record.schema_position,
        "restoredFrom": record.restored_from,
    }


def records_of_model(store: HistoryStore, model: type, id: UUID) -> list[HistoryRecord]:
    records = [r for r in store.versions(id) if r.model == model.__name__]
    if not records:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"There is no history of a {model.__name__} with id {id}",
        )
    return records


@router.get("/{model_name}/{id}/history")
async def list_versions(model_name: str, id: UUID, store: Store) -> dict[str, Any]:
    """The versions of a head node: version, operation, who, when, and any that were not recorded"""
    model = find_model(model_name)
    records = records_of_model(store, model, id)
    current = await current_version(model, id)
    return {
        "id": str(id),
        "model": model_name,
        "versions": [describe(r) for r in records],
        "currentVersion": current,
        "missing": find_gaps(records, current) if current is not None else [],
    }


def version_content(store: HistoryStore, model: type, id: UUID, version: int) -> HistoryRecord:
    records_of_model(store, model, id)
    record = store.get(id, version)
    if record is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"Version {version} of {model.__name__} {id} was not recorded",
        )
    return record


@router.get("/{model_name}/{id}/history/{version}")
async def get_version(
    model_name: str,
    id: UUID,
    version: int,
    store: Store,
    upgrade: Annotated[
        bool, Query(description="Upgrade it to the models of now (false: as it was written)")
    ] = True,
) -> dict[str, Any]:
    """A version, upgraded to the models of now (with what could not be upgraded in `problems`)"""
    model = find_model(model_name)
    record = version_content(store, model, id, version)
    body = describe(record)
    if upgrade:
        draft = make_draft(record, model)
        return {
            **body,
            "content": draft.data,
            "upgraded": draft.upgraded,
            "problems": [p.to_dict() for p in draft.problems],
        }
    return {**body, "content": record.data(), "upgraded": False, "problems": []}


@router.get("/{model_name}/{id}/history/{version}/draft")
async def get_draft(model_name: str, id: UUID, version: int, store: Store) -> dict[str, Any]:
    """A restore as a draft to reconcile: the version upgraded as far as it can be, and the
    problems that someone has to decide (it may be incomplete or invalid)"""
    model = find_model(model_name)
    record = version_content(store, model, id, version)
    draft = make_draft(record, model)
    return {
        "fromVersion": version,
        "schemaPosition": record.schema_position,
        "draft": draft.data,
        "problems": [p.to_dict() for p in draft.problems],
    }


@router.get("/{model_name}/{id}/history/{version}/diff")
async def get_difference(
    model_name: str,
    id: UUID,
    version: int,
    store: Store,
    to: Annotated[int | None, Query(description="Defaults to the latest recorded")] = None,
) -> dict[str, Any]:
    """What changed from one version to another"""
    model = find_model(model_name)
    if to is None:
        to = store.latest_version(id)
        if to is None:
            records_of_model(store, model, id)
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Nothing is recorded")
    before = version_content(store, model, id, version)
    after = version_content(store, model, id, to)
    return {
        "id": str(id),
        "from": version,
        "to": to,
        "changes": [c.to_dict() for c in diff(before.data(), after.data())],
    }


@router.post("/{model_name}/{id}/history/{version}/restore")
async def restore_version(
    model_name: str,
    id: UUID,
    version: int,
    store: Store,
    response: Response,
    if_match: Annotated[
        str | None,
        Header(
            alias="If-Match",
            description='The version that is being replaced: its ETag ("3"), or * for whatever it is now.',
        ),
    ] = None,
) -> dict[str, Any]:
    """Write an earlier version again, as a new version. 409 if it cannot be restored as it is
    (the reasons are in the message)"""
    model = find_model(model_name)
    records_of_model(store, model, id)
    new_version = await restore(store, model, id, version, expected_version(if_match))
    response.headers["ETag"] = etag(new_version)
    return {"id": str(id), "version": new_version, "restoredFrom": version}
