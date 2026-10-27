"""The server's side of Zotero: the watcher as a background task, and a small router (`/api/zotero/...`)."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from pangloss_api.background import BackgroundTask
from pangloss_api.dependencies import get_current_user
from pangloss_core import settings as core_settings
from pydantic import BaseModel

from pangloss_zotero import config
from pangloss_zotero.client import ZoteroClient
from pangloss_zotero.link import LinkError, link_item
from pangloss_zotero.mapping import build_table
from pangloss_zotero.store import ModelStore
from pangloss_zotero.watch import watch

router = APIRouter(prefix="/api/zotero", tags=["zotero"])


@router.get("/status")
async def status(request: Request) -> dict[str, Any]:
    """Where each library is, whether the watcher runs here, and which class each item type is written as"""
    store = ModelStore()
    libraries = {}
    for library in config.libraries():
        state = await store.library_state(library)
        libraries[library] = {
            "synced_version": state.synced_version,
            "last_sync": state.last_sync,
            "last_error": state.last_error,
        }
    supervisor = getattr(request.app.state, "supervisor", None)
    table = build_table()
    return {
        "libraries": libraries,
        "watcher": supervisor.status().get("zotero") if supervisor else None,
        "item_types": table.describe(),
        "fallback": table.fallback.__name__,
    }


class LinkRequest(BaseModel):
    model: str
    id: UUID
    zotero_url: str


@router.post("/link", status_code=204, dependencies=[Depends(get_current_user)])
async def link(body: LinkRequest, request: Request) -> None:
    """Make a text object that was made by hand an item of the Zotero library: it takes the item's fields and
    its address. Refused if the item is in the database already, or the class cannot be of its type."""
    settings = core_settings.SETTINGS
    factory = getattr(request.app.state, "zotero_client", None)
    client = (
        factory()
        if factory
        else ZoteroClient(config.api_key(settings), config.api_url(settings))
    )
    try:
        await link_item(settings, client, body.model, body.id, body.zotero_url)
    except LinkError as error:
        raise HTTPException(error.status, detail=str(error)) from error
    finally:
        if not factory:
            await client.close()


def configure_app(app: FastAPI, settings: Any) -> None:
    if config.watch_wanted(settings):
        app.state.background_tasks.append(BackgroundTask("zotero", watch))
