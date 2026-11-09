"""Everything a reader who is not logged in can see, as RDF. One read for each head, a page of them at a time."""

import asyncio
import datetime
import gzip
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from pangloss_models import Document, Entity
from pangloss_users import see_unpublished

from pangloss_rdf.convert import convert
from pangloss_rdf.dataset import dataset_quads, dataset_uri
from pangloss_rdf.export import read
from pangloss_rdf.literals import to_literal
from pangloss_rdf.meta import is_excluded
from pangloss_rdf.ontology import exported_models
from pangloss_rdf.serialise import line, serialise
from pangloss_rdf.terms import Quad
from pangloss_rdf.uris import class_name
from pangloss_rdf.vocabulary import dcterms

PAGE_SIZE = 200
CONCURRENT_READS = 16


@dataclass
class DumpResult:
    items: int = 0
    quads: int = 0


def models_to_dump(names: Iterable[str] | None = None) -> list[Any]:
    wanted = set(names) if names else None
    models = []
    for model in exported_models():
        if not issubclass(model, (Document, Entity)) or is_excluded(model):
            continue
        if model._meta.abstract:  # type: ignore[attr-defined]
            continue
        if wanted is None or model.__name__ in wanted or class_name(model) in wanted:
            models.append(model)
    return models


async def _head_ids(model: Any) -> Any:
    """A page at a time, the heads that are this class: a list of a class also has its subclasses, which have their own turn"""
    page = 1
    while True:
        listing = await model.list(page_number=page, page_size=PAGE_SIZE)
        ids = [item.id for item in listing.results if item.type == model.__name__]
        if ids:
            yield ids
        if not listing.next_page:
            return
        page = listing.next_page


def _is_head(item: Any) -> bool:
    head = getattr(getattr(item, "meta", None), "head_node_id", None)
    return head is None or head == item.id


def _write(output: Any, quads: list[Quad], format: str) -> None:
    if format == "nq":
        output.writelines(line(quad) for quad in quads)
    else:
        output.write(serialise(quads, "trig"))


async def dump(
    path: Path,
    format: str = "nq",
    types: Iterable[str] | None = None,
    include_unpublished: bool = False,
) -> DumpResult:
    """`format` is `nq` or `trig`; a `path` ending `.gz` is compressed. An entity's export has no `referencedBy` here:
    the documents that refer to it are all in the file"""
    see_unpublished.set(include_unpublished)
    result = DumpResult()
    limit = asyncio.Semaphore(CONCURRENT_READS)

    async def one(model: Any, item_id: UUID) -> list[Quad] | None:
        async with limit:
            item = await read(model, item_id)
        if item is None or not _is_head(item):
            return None
        return list(convert(item))

    opened = gzip.open if path.suffix == ".gz" else open
    with opened(path, "wt", encoding="utf-8") as output:
        description = [
            *dataset_quads(),
            Quad(
                dataset_uri(),
                dcterms("issued"),
                to_literal(datetime.datetime.now(datetime.timezone.utc)),
            ),
        ]
        _write(output, description, format)
        result.quads += len(description)
        for model in models_to_dump(types):
            async for ids in _head_ids(model):
                found = await asyncio.gather(*(one(model, i) for i in ids))
                for quads in found:
                    if quads is None:
                        continue
                    _write(output, quads, format)
                    result.items += 1
                    result.quads += len(quads)
    return result
