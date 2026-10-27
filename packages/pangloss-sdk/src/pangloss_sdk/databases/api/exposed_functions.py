"""The model functions as requests to a Pangloss API (async).

These are what `Model.get`, `Model.list`, `Create(...).save()` and the rest are bound to
when `DATABASE_MODULE` is `pangloss_sdk.databases.api`. Each is one request, and returns
what the database module of the server returns, or raises what it raises.
"""

from typing import Any
from uuid import UUID

from pangloss_models.autocomplete import AutocompleteResults
from pangloss_models.model_bases.base_models import _ListItems
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from pangloss_models.search import Match
from pangloss_sdk import protocol
from pangloss_sdk.client import current_async_client
from pydantic import AnyHttpUrl


async def get_document(cls: type[Document], id: UUID | AnyHttpUrl) -> Any:
    return protocol.got(cls, await current_async_client().send(protocol.get(cls, id)))


async def get_entity(cls: type[Entity], id: UUID | AnyHttpUrl) -> Any:
    return protocol.got(cls, await current_async_client().send(protocol.get(cls, id)))


async def get_entity_for_edit(cls: type[Entity], id: UUID | AnyHttpUrl) -> Any:
    response = await current_async_client().send(protocol.get_for_edit(cls, id))
    return protocol.got_for_edit(cls, response)


async def list_items(
    cls: type[Document | Entity],
    search_terms: str | None = None,
    page_number: int | None = None,
    page_size: int | None = None,
    deep_search: bool = False,
    published: bool | None = None,
    review_status: str | None = None,
) -> _ListItems:
    call = protocol.list_items(
        cls,
        search_terms,
        page_number,
        page_size,
        deep_search,
        published,
        review_status,
    )
    return protocol.listed(cls, await current_async_client().send(call))


async def search(
    cls: type[Document | Entity],
    match: Match,
    page_number: int | None = None,
    page_size: int | None = None,
) -> _ListItems:
    call = protocol.search(
        match if match.type else match.model_copy(update={"type": cls.__name__}),
        page_number,
        page_size,
    )
    return protocol.searched(cls, await current_async_client().send(call))


async def autocomplete(
    cls: type[Entity],
    search_terms: str,
    types: list[type] | None = None,
    page_number: int | None = None,
    page_size: int | None = None,
) -> AutocompleteResults:
    call = protocol.autocomplete(search_terms, types or [cls], page_number, page_size)
    return protocol.autocompleted(await current_async_client().send(call))


async def create_head_node(self: Any, detail: bool = False) -> Any:
    response = await current_async_client().send(protocol.create(self, detail))
    return protocol.created(self, response, detail)


async def update_head_node(
    self: Any, detail: bool = False, expected_version: int | None = None
) -> Any:
    call = protocol.update(self, detail, expected_version)
    response = await current_async_client().send(call)
    return protocol.updated(self, response, detail)


async def delete_document(cls: type[Document], id: UUID) -> None:
    protocol.done(await current_async_client().send(protocol.delete(cls, id)))


async def delete_entity(cls: type[Entity], id: UUID | AnyHttpUrl) -> None:
    protocol.done(await current_async_client().send(protocol.delete(cls, id)))


async def undelete_document(cls: type[Document], id: UUID) -> None:
    protocol.done(await current_async_client().send(protocol.undelete(cls, id)))


async def undelete_entity(cls: type[Entity], id: UUID | AnyHttpUrl) -> None:
    protocol.done(await current_async_client().send(protocol.undelete(cls, id)))
