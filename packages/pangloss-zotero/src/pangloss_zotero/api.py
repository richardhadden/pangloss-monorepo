"""The server's side of Zotero: the watcher as a background task, and a small router (`/api/zotero/...`)."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from pangloss_api import BackgroundTask, get_current_user
from pangloss_core import settings as core_settings
from pydantic import BaseModel

from pangloss_zotero import config
from pangloss_zotero.client import ZoteroClient
from pangloss_zotero.link import LinkError, base_on, fallback, link_item, unlink_item
from pangloss_zotero.mapping import build_table, concrete_classes
from pangloss_zotero.store import ModelStore
from pangloss_zotero.watch import watch

router = APIRouter(prefix="/api/zotero", tags=["zotero"])


@router.get("/status", dependencies=[Depends(get_current_user)])
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


@router.get("/classes")
async def classes() -> dict[str, Any]:
    """The class of the items no project class stands for (`fallback`), and the classes a person can make one into
    (`targets`: `base-on`, `link`)"""
    plain = fallback()
    return {
        "fallback": plain.__name__,
        "targets": sorted(
            c.__name__ for c in concrete_classes() if c.__name__ != plain.__name__
        ),
    }


class Summary(BaseModel):
    id: UUID
    type: str
    label: str


class LinkRequest(BaseModel):
    model: str
    id: UUID
    zotero_url: str


@router.post("/link", dependencies=[Depends(get_current_user)])
async def link(body: LinkRequest, request: Request) -> Summary:
    """Make a text object that was made by hand an item of the Zotero library: it takes the item's fields and
    its address. If the item is a node already, the two become one: the one something refers to is kept (refused if
    both are), so the node that is the item, which this gives, may be another one. Refused if the class cannot be
    of the item's type."""
    settings = core_settings.SETTINGS
    factory = getattr(request.app.state, "zotero_client", None)
    client = (
        factory()
        if factory
        else ZoteroClient(config.api_key(settings), config.api_url(settings))
    )
    try:
        return Summary(
            **await link_item(settings, client, body.model, body.id, body.zotero_url)
        )
    except LinkError as error:
        raise HTTPException(error.status, detail=str(error)) from error
    finally:
        if not factory:
            await client.close()


class BaseOnRequest(BaseModel):
    model: str
    # (the item's id, or its Zotero address)
    item: str
    # (what the form of a new `model` gives)
    data: dict[str, Any]


@router.post("/base-on", dependencies=[Depends(get_current_user)])
async def make_from_item(body: BaseOnRequest) -> Summary:
    """Make an item (a node of the fallback class) a `model`, in place, with what the form gives: it keeps its id, its
    address and what refers to it, and stays an item of the library"""
    try:
        return Summary(
            **await base_on(core_settings.SETTINGS, body.model, body.item, body.data)
        )
    except LinkError as error:
        raise HTTPException(error.status, detail=str(error)) from error


class UnlinkRequest(BaseModel):
    model: str
    id: UUID


@router.post("/unlink", dependencies=[Depends(get_current_user)])
async def unlink(body: UnlinkRequest) -> Summary:
    """Take the Zotero item off a node: the node keeps its own fields and what refers to it; the item is a node of the
    fallback class again, which this gives"""
    try:
        return Summary(**await unlink_item(core_settings.SETTINGS, body.model, body.id))
    except LinkError as error:
        raise HTTPException(error.status, detail=str(error)) from error


def configure_app(app: FastAPI, settings: Any) -> None:
    if config.watch_wanted(settings):
        app.state.background_tasks.append(BackgroundTask("zotero", watch))
