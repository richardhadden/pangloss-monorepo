"""Reading every document and entity with the models as they are, to find what they cannot read.

A migration is checked by what it leaves: data that the models can read. `check_data` reads each
head node (a Document or Entity that is not deleted) as the model of its `type` does, and reports
what fails and why. It needs the models initialised and the database connected.
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from pangloss_models.model_registry import ModelRegistry

PAGE_SIZE = 100
# How many nodes are read at once. One: measured against a local Memgraph, reading several at a
# time was slower (300 nodes: 0.48 s one at a time, 0.76 s four, 0.89 s eight), as the time is in
# building the models, not waiting for the database. A database a long way off may do better.
CONCURRENCY = 1


@dataclass
class DataProblem:
    model: str
    id: str
    label: str | None
    errors: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        shown = "; ".join(self.errors[:3]) + (" ..." if len(self.errors) > 3 else "")
        return f"{self.model} {self.id} ({self.label}): {shown}"


@dataclass
class DataCheck:
    checked: int = 0
    problems: list[DataProblem] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def describe_error(error: Exception) -> list[str]:
    if isinstance(error, ValidationError):
        return [
            f"{'.'.join(str(part) for part in e['loc'])}: {e['msg']}" for e in error.errors()
        ]
    return [f"{type(error).__name__}: {error}"]


def head_models() -> list[type]:
    """The models whose nodes can be read on their own: Documents and Entities, not abstract"""
    found = []
    for model in ModelRegistry.all_models().values():
        if getattr(model, "__metatype__", None) not in ("Document", "Entity"):
            continue
        if (model.__pydantic_generic_metadata__ or {}).get("origin"):
            continue
        if getattr(model._meta, "abstract", False):  # type: ignore[attr-defined]
            continue
        found.append(model)
    return sorted(found, key=lambda m: m.__name__)


async def check_data(
    types: list[str] | None = None,
    limit: int | None = None,
    progress: Callable[[str, int], None] | None = None,
    concurrency: int = CONCURRENCY,
) -> DataCheck:
    """Read the head nodes (of the models named, or all), up to `limit` of each model, `concurrency`
    at a time. The problems are in the order the nodes were listed in."""
    models = {m.__name__: m for m in head_models()}
    wanted = [models[name] for name in (types or models) if name in models]
    result = DataCheck()
    seen: set[str] = set()
    gate = asyncio.Semaphore(max(1, concurrency))

    async def read(model: type, reference: Any) -> DataProblem | None:
        # (read as the model of its own type does, not of the one it was listed under)
        own = models.get(reference.type, model)
        async with gate:
            try:
                await own.get(id=reference.id)  # type: ignore[attr-defined]
            except Exception as error:
                return DataProblem(
                    model=reference.type,
                    id=str(reference.id),
                    label=getattr(reference, "label", None),
                    errors=describe_error(error),
                )
        return None

    for model in wanted:
        page, count = 1, 0
        while True:
            listing: Any = await model.list(page_number=page, page_size=PAGE_SIZE)  # type: ignore[attr-defined]
            to_read = []
            for reference in listing.results:
                node_id = str(reference.id)
                if node_id in seen:
                    continue  # (a node is listed with each model above it)
                seen.add(node_id)
                count += 1
                if limit is not None and count > limit:
                    break
                to_read.append(reference)
            found = await asyncio.gather(*(read(model, reference) for reference in to_read))
            result.checked += len(to_read)
            result.problems += [problem for problem in found if problem is not None]
            if (limit is not None and count > limit) or listing.next_page is None:
                break
            page = listing.next_page
        if progress:
            progress(model.__name__, count)
    return result
