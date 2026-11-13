"""The model functions as requests to a Pangloss API (blocking).

These are what `Model.get`, `Model.list`, `Create(...).save()` and the rest are bound to
when `STORAGE` is `pangloss_sdk.storage:api_sync`. Each is one request, and returns
what the database module of the server returns, or raises what it raises.
"""

from collections.abc import Iterable
from typing import Any
from uuid import UUID

from pangloss_models.creators import ToolchainRun
from pangloss_models.autocomplete import AutocompleteItem, AutocompleteResults
from pangloss_models.model_bases.base_models import _ListItems
from pangloss_models import Document, Entity, Match, OrderBy, Where
from pangloss_models.merging import (
    MergePreview,
    MergeRecord,
    MergeResult,
    UnmergeResult,
)
from pangloss_models.search import search_match
from pangloss_models.utils import get_concrete_types
from pangloss_sdk import protocol
from pangloss_sdk.client import current_client
from pydantic import AnyHttpUrl


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
    published: bool | None = None,
    review_status: str | None = None,
    used_only: bool = False,
    use_counts: bool = False,
) -> _ListItems:
    call = protocol.list_items(
        cls,
        search_terms,
        page_number,
        page_size,
        deep_search,
        published,
        review_status,
        used_only,
        use_counts,
    )
    return protocol.listed(cls, current_client().send(call))


def search(
    cls: type[Document | Entity],
    pattern: Match | Where | None = None,
    page_number: int | None = None,
    page_size: int | None = None,
    *,
    order_by: list[OrderBy | str] | None = None,
    used_only: bool = False,
    use_counts: bool = False,
) -> _ListItems:
    call = protocol.search(
        cls,
        search_match(cls, pattern, order_by),
        page_number,
        page_size,
        used_only,
        use_counts,
    )
    return protocol.searched(cls, current_client().send(call))


def autocomplete(
    cls: type[Entity],
    search_terms: str = "",
    types: list[type] | None = None,
    page_number: int | None = None,
    page_size: int | None = None,
) -> AutocompleteResults:
    call = protocol.autocomplete(search_terms, types or [cls], page_number, page_size)
    return protocol.autocompleted(current_client().send(call))


def search_everything(
    search_terms: str,
    labels: list[str] | None,
    excluded: list[str],  # (the API has its own, from the same models)
    page_number: int | None = None,
    page_size: int | None = None,
) -> AutocompleteResults:
    call = protocol.search_everything(search_terms, labels, page_number, page_size)
    return protocol.autocompleted(current_client().send(call))


def references(cls: type[Entity], ids: list[UUID]) -> list[AutocompleteItem]:
    if not ids:
        return []
    call = protocol.references(ids)
    found = protocol.referenced(current_client().send(call))
    if cls is Entity:
        return found
    allowed = {t.__name__ for t in get_concrete_types(cls, include_abstract=True)}
    return [item for item in found if item.type in allowed]


def create_head_node(
    self: Any,
    detail: bool = False,
    published: bool | None = None,
    review_status: str | None = None,
    created_by: Iterable[str] | str | None = None,
    toolchain: ToolchainRun | str | None = None,
    review_assigned_to: str | None = None,
) -> Any:
    response = current_client().send(
        protocol.create(
            self,
            detail,
            published,
            review_status,
            created_by,
            toolchain,
            review_assigned_to,
        )
    )
    return protocol.created(self, response, detail)


def save_with_companions(
    self: Any,
    companions: dict[str, dict[str, Any]],
    detail: bool = False,
    **options: Any,
) -> tuple[Any, list[Any]]:
    """The entity and its companions, made by the API in one transaction"""
    call = protocol.create_with_companions(self, companions, detail, **options)
    return protocol.created_with_companions(self, current_client().send(call), detail)


def update_head_node(
    self: Any,
    detail: bool = False,
    expected_version: int | None = None,
    published: bool | None = None,
    review_status: str | None = None,
    acknowledge_citations: Any = None,
) -> Any:
    call = protocol.update(
        self, detail, expected_version, published, review_status, acknowledge_citations
    )
    response = current_client().send(call)
    return protocol.updated(self, response, detail)


def delete_document(
    cls: type[Document], id: UUID, acknowledge_citations: Any = None
) -> None:
    protocol.done(
        current_client().send(protocol.delete(cls, id, acknowledge_citations))
    )


def document_cited_by(cls: type[Document], id: UUID) -> list[dict[str, Any]]:
    """Who cites a document and its parts (`GET /api/NAME/{id}/cited`)"""
    return protocol.cited_by_rows(current_client().send(protocol.cited_by(cls, id)))


def delete_entity(cls: type[Entity], id: UUID | AnyHttpUrl) -> None:
    protocol.done(current_client().send(protocol.delete(cls, id)))


def undelete_document(cls: type[Document], id: UUID) -> None:
    protocol.done(current_client().send(protocol.undelete(cls, id)))


def undelete_entity(cls: type[Entity], id: UUID | AnyHttpUrl) -> None:
    protocol.done(current_client().send(protocol.undelete(cls, id)))


# --- merging entities (implementation_docs/entity-identity.md): what the server lets this user do -----------------------


def merge_entities(
    cls: type[Entity],
    absorb: UUID,
    into: UUID,
    *,
    values: Any = None,
    as_class: type[Entity] | None = None,
    version_into: int | None = None,
    version_absorb: int | None = None,
    allow_large: bool = False,
) -> MergeResult:
    """(`allow_large` is the server's to say: a merge over the limit is made for an admin)"""
    body = protocol.merge_body(absorb, values, as_class, version_into, version_absorb)
    call = protocol.merge(cls, into, body)
    return protocol.merge_answer(MergeResult, current_client().send(call))


def preview_merge(
    cls: type[Entity],
    absorb: UUID,
    into: UUID,
    *,
    values: Any = None,
    as_class: type[Entity] | None = None,
) -> MergePreview:
    call = protocol.merge(
        cls, into, protocol.merge_body(absorb, values, as_class), "merge/preview"
    )
    return protocol.merge_answer(MergePreview, current_client().send(call))


def propose_merge(
    cls: type[Entity],
    absorb: UUID,
    into: UUID,
    *,
    values: Any = None,
    as_class: type[Entity] | None = None,
    note: str | None = None,
) -> MergeRecord:
    body = protocol.merge_body(absorb, values, as_class, note=note)
    call = protocol.merge(cls, into, body, "merge/propose")
    return protocol.merge_answer(MergeRecord, current_client().send(call))


def merges_of_entity(cls: type[Entity], id: UUID) -> list[MergeRecord]:
    return protocol.merge_records(current_client().send(protocol.merges_of(cls, id)))


def unmerge_entities(
    cls: type[Entity],
    merge_id: UUID | str,
    *,
    confirm_migrated: bool = False,
    dry_run: bool = False,
    accepting: bool = False,
) -> UnmergeResult:
    """(whether this is the accepting of someone's proposal is the server's to say, by who the user is)"""
    body = {"confirmMigrated": confirm_migrated, "dryRun": dry_run}
    call = protocol.a_merge(merge_id, "undo", body)
    return protocol.merge_answer(UnmergeResult, current_client().send(call))


def get_merge(merge_id: UUID | str) -> MergeRecord:
    call = protocol.a_merge(merge_id)
    return protocol.merge_answer(MergeRecord, current_client().send(call))


def verify_merge(
    merge_id: UUID | str,
    *,
    values: Any = None,
    as_class: type[Entity] | None = None,
    version_into: int | None = None,
    version_absorb: int | None = None,
    allow_large: bool = False,
) -> MergeResult:
    body = protocol.merge_body("", values, as_class, version_into, version_absorb)
    body.pop("absorb")
    call = protocol.a_merge(merge_id, "verify", body)
    return protocol.merge_answer(MergeResult, current_client().send(call))


def reject_merge(merge_id: UUID | str, reason: str | None = None) -> MergeRecord:
    call = protocol.a_merge(merge_id, "reject", {"reason": reason})
    return protocol.merge_answer(MergeRecord, current_client().send(call))


def propose_unmerge(merge_id: UUID | str, note: str | None = None) -> MergeRecord:
    call = protocol.a_merge(merge_id, "undo/propose", {"note": note})
    return protocol.merge_answer(MergeRecord, current_client().send(call))


def reject_unmerge(merge_id: UUID | str, reason: str | None = None) -> MergeRecord:
    call = protocol.a_merge(merge_id, "undo/reject", {"reason": reason})
    return protocol.merge_answer(MergeRecord, current_client().send(call))


def list_merges(
    states: list[str] | None = None,
    undo_proposed: bool = False,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[MergeRecord], int]:
    """(a page of the server's list: `skip` is taken to the start of the page it falls in)"""
    response = current_client().send(
        protocol.list_merges(states, undo_proposed, skip, limit)
    )
    records = protocol.merge_records(response, "results")
    return records, response.json()["count"]
