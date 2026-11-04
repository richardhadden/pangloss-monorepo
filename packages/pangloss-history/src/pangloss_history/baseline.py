"""`pangloss history baseline`: a record of what each head node is now, for those that history has no record of at
their version. A project that installs `pangloss_history` when it has data already has no history of that data until
it is next written, and what it was before that write could never be restored: a baseline is that missing record.

Each head node whose latest record is missing, or older than its version in the graph, gets one record: its content
read for editing, validated as its `Update` and made the write form, as a write would have it (the listener's
`serialise`); `op = "baseline"`, the version it has, and who last changed it, and when (its creation, if it has not
been changed). A head node with a record of its version is left alone, so it is safe to run again.
(docs/history-interface.md)"""

import dataclasses
import datetime
from collections.abc import Iterable, Sequence
from typing import Any

from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_registry import ModelRegistry

from pangloss_history import config
from pangloss_history.listener import serialise
from pangloss_history.restore import called
from pangloss_history.store import HistoryRecord, HistoryStore

PAGE_SIZE = 200


@dataclasses.dataclass
class Baseline:
    """What a run found: how many head nodes were looked at, recorded, and already had a record of their version;
    and those that could not be made the write form (with why)"""

    looked_at: int = 0
    recorded: int = 0
    up_to_date: int = 0
    failed: list[tuple[str, str, str]] = dataclasses.field(default_factory=list)


def models_with_history() -> list[Any]:
    """The concrete Documents and Entities that are written as head nodes, and that history is kept of"""
    excluded = config.excluded_models()
    return [
        model
        for name, model in ModelRegistry.all_models().items()
        if isinstance(model, type)
        and issubclass(model, (Document, Entity))
        and hasattr(model, "Update")
        and not model._meta.abstract  # type: ignore[attr-defined]
        and name not in excluded
    ]


async def head_nodes(model: Any) -> Iterable[Any]:
    """The head nodes of exactly this model (not of its subclasses, which are listed as themselves)"""
    found = []
    page = 1
    while True:
        listed = await called(model.list(page_number=page, page_size=PAGE_SIZE))
        for item in listed.results:
            if item.type == model.__name__ and getattr(item, "is_head_node", True):
                found.append(item)
        if not listed.next_page:
            return found
        page = listed.next_page


async def write_form(model: Any, id: Any) -> tuple[Any, Any]:
    """What the head node is now, as the write form of an update of it, and its `meta`"""
    read = model.get_for_edit if issubclass(model, Entity) else model.get
    view = await called(read(id))
    if view is None:
        raise LookupError(f"{model.__name__} {id} is not there")
    update = model.Update.model_validate(view.model_dump())
    return update._to_db_model(), view.meta


def record_of(
    model: Any, id: Any, payload: Any, meta: Any, position: dict[str, str]
) -> HistoryRecord:
    changed_when = meta.updated_when or meta.created_when
    return HistoryRecord(
        head_id=id,
        version=meta.version,
        op="baseline",
        model=model.__name__,
        at=changed_when
        if changed_when.tzinfo
        else changed_when.replace(tzinfo=datetime.UTC),
        who=meta.updated_by or meta.created_by,
        schema_position=position,
        content=serialise(payload),
    )


async def make_baseline(
    store: HistoryStore,
    position: dict[str, str],
    models: Sequence[Any] | None = None,
    dry_run: bool = False,
) -> Baseline:
    """Record a baseline of each head node of `models` (all with history, by default) that needs one"""
    result = Baseline()
    for model in models if models is not None else models_with_history():
        batch: list[HistoryRecord] = []
        for item in await head_nodes(model):
            result.looked_at += 1
            latest = store.latest_version(item.id)
            version = getattr(getattr(item, "meta", None), "version", None)
            if latest is not None and version is not None and latest >= version:
                result.up_to_date += 1
                continue
            try:
                payload, meta = await write_form(model, item.id)
            except Exception as error:  # (one that does not fit its model now is said, and the rest go on)
                result.failed.append(
                    (model.__name__, str(item.id), str(error).splitlines()[0])
                )
                continue
            if latest is not None and latest >= meta.version:
                result.up_to_date += 1
                continue
            result.recorded += 1
            batch.append(record_of(model, item.id, payload, meta, position))
        if batch and not dry_run:
            store.append(batch)
    return result
