"""The model functions as requests to a Pangloss API (blocking).

These are what `Model.get`, `Model.list`, `Create(...).save()` and the rest are bound to
when `DATABASE_MODULE` is `pangloss_sdk.databases.api_sync`. Each is one request, and returns
what the database module of the server returns, or raises what it raises.
"""

from typing import Any
from uuid import UUID

from pangloss_models.model_bases.base_models import _ListItems
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from pydantic import AnyHttpUrl

from pangloss_sdk import protocol
from pangloss_sdk.client import current_client


def get_document(cls: type[Document], id: UUID | AnyHttpUrl) -> Any:
    return protocol.got(cls, current_client().send(protocol.get(cls, id)))


def get_entity(cls: type[Entity], id: UUID | AnyHttpUrl) -> Any:
    return protocol.got(cls, current_client().send(protocol.get(cls, id)))


def get_entity_for_edit(cls: type[Entity], id: UUID | AnyHttpUrl) -> Any:
    response = current_client().send(protocol.get_for_edit(cls, id))
    return protocol.got_for_edit(cls, response)


def list_items(
    cls: type[Document | Entity],
    search_terms: str | None = None,
    page_number: int | None = None,
    page_size: int | None = None,
    deep_search: bool = False,
) -> _ListItems:
    call = protocol.list_items(cls, search_terms, page_number, page_size, deep_search)
    return protocol.listed(cls, current_client().send(call))


def create_head_node(self: Any, detail: bool = False) -> Any:
    response = current_client().send(protocol.create(self, detail))
    return protocol.created(self, response, detail)


def update_head_node(
    self: Any, detail: bool = False, expected_version: int | None = None
) -> Any:
    call = protocol.update(self, detail, expected_version)
    response = current_client().send(call)
    return protocol.updated(self, response, detail)


def delete_document(cls: type[Document], id: UUID) -> None:
    protocol.done(current_client().send(protocol.delete(cls, id)))


def delete_entity(cls: type[Entity], id: UUID | AnyHttpUrl) -> None:
    protocol.done(current_client().send(protocol.delete(cls, id)))


def undelete_document(cls: type[Document], id: UUID) -> None:
    protocol.done(current_client().send(protocol.undelete(cls, id)))


def undelete_entity(cls: type[Entity], id: UUID | AnyHttpUrl) -> None:
    protocol.done(current_client().send(protocol.undelete(cls, id)))
