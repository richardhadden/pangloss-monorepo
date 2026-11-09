"""An item, read and converted: what the routes and the dump do"""

import inspect
from typing import Any
from uuid import UUID

from pangloss_core.settings import get_settings
from pangloss_core.storage import storage_of
from pangloss_models import Entity

from pangloss_rdf.convert import convert
from pangloss_rdf.literals import to_literal
from pangloss_rdf.terms import Quad
from pangloss_rdf.uris import item_uri
from pangloss_rdf.vocabulary import pgo

DEFAULT_REFERENCED_BY_LIMIT = 1000


async def _called(result: Any) -> Any:
    return await result if inspect.isawaitable(result) else result


def referenced_by_limit() -> int:
    return int(
        getattr(get_settings(), "RDF_REFERENCED_BY_LIMIT", DEFAULT_REFERENCED_BY_LIMIT)
    )


async def read(model: Any, item_id: UUID) -> Any | None:
    """The item with its own data: an entity without what refers to it, which is said in the documents that do"""
    if issubclass(model, Entity):
        return await _called(
            storage_of().operations.get_entity_without_incoming(model, item_id)
        )
    return await _called(model.get(item_id))


async def referenced_by(item: Any, limit: int | None = None) -> list[Quad]:
    """A triple for each document that refers to an entity, up to `limit` for each incoming field, and how many there are"""
    limit = limit if limit is not None else referenced_by_limit()
    found = await _called(
        storage_of().operations.get_incoming_fields(
            item._owner, item.id, min(limit, 500)
        )
    )
    if found is None:
        return []
    subject = item_uri(item._owner, item.id)
    documents = {
        item_uri(referrer._owner, referrer.id)
        for referrers in found.fields.values()
        for referrer in referrers
    }
    quads = [
        Quad(subject, pgo("referencedBy"), uri, subject)
        for uri in sorted(documents, key=str)
    ]
    total = sum(found.counts.values())
    quads.append(Quad(subject, pgo("referenceCount"), to_literal(total), subject))
    return quads


async def item_quads(model: type, item_id: UUID) -> tuple[Any, list[Quad]] | None:
    """`(item, quads)`, or None if a reader of this request cannot see one"""
    item = await read(model, item_id)
    if item is None:
        return None
    quads = list(convert(item))
    if issubclass(item._owner, Entity):
        quads.extend(await referenced_by(item))
    return item, quads
