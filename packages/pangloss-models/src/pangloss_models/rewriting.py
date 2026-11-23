"""A head written again with a part of it replaced, as a person would in a form: the head is read, dumped as an
`Update` takes it (`editable`), the parts chosen are replaced in that tree, the `Update` is made, and it is saved
based on the version read (a new version, a write event, a record in the history).

`pangloss-review` reconciles a mention so (`reconcile.rewrite_part`), `pangloss-criteria` resolves and shares a
description so (`resolving.resolve`, `sharing.share`). `prepare_rewrite` does all of it but the save, for a caller
that only asks whether a place would take a replacement.

The tree functions (`replaced_where`, `replaced`) are pure: they change a copy, never what they are given.
"""

import dataclasses
from collections.abc import Awaitable, Callable
from typing import Any, Literal
from uuid import UUID

from pangloss_models.utils import editable

type Replace = Callable[[dict[str, Any]], dict[str, Any]]
"""What a node chosen becomes (given the node, as an `Update` takes it)"""

type Change = Callable[[Any], tuple[Any, bool]]
"""What a rewrite does to the tree of a head (as an `Update` takes it): the tree changed, and whether anything was"""


def replaced_where(
    value: Any, chosen: Callable[[dict[str, Any]], bool], replace: Replace
) -> tuple[Any, bool]:
    """`value` with every node `chosen` says is one replaced by what `replace` makes of it, and whether any was. A
    node replaced is not looked into"""
    if isinstance(value, dict):
        if chosen(value):
            return replace(value), True
        found = False
        changed = {}
        for key, item in value.items():
            changed[key], item_found = replaced_where(item, chosen, replace)
            found = found or item_found
        return changed, found
    if isinstance(value, list):
        items = [replaced_where(item, chosen, replace) for item in value]
        return [item for item, _ in items], any(found for _, found in items)
    return value, False


def replaced(value: Any, id: str, replace: Replace) -> tuple[Any, bool]:
    """`value` (what an update takes) with the node of that id replaced by what `replace` makes of it, and whether
    it was found"""
    return replaced_where(value, lambda part: str(part.get("id")) == id, replace)


async def read_head(model: Any, id: UUID) -> Any:
    """A head as it is now, to be written again: an entity as it is edited (without what refers to it), a document as
    it is read"""
    read = model.get_for_edit if model.__metatype__ == "Entity" else model.get
    return await read(id)


@dataclasses.dataclass(frozen=True)
class Prepared:
    """A rewrite made and not saved"""

    view: Any
    """The head as it was read"""
    update: Any
    """The `Update` of it with the change made"""
    version: int
    """The version read"""


@dataclasses.dataclass(frozen=True)
class Missing:
    """Why there is nothing to rewrite: the head is not there (`"head"`: none of that id the reader may see, or it is
    deleted), or the change found nothing in it to change (`"part"`)"""

    what: Literal["head", "part"]


async def prepare_rewrite(
    model: Any,
    head_id: UUID,
    change: Change,
    *,
    read: Callable[[Any, UUID], Awaitable[Any]] | None = None,
) -> Prepared | Missing:
    """The head of the class `model` and id `head_id` read (`read_head`), `change` made to its tree, and its `Update`
    made of that: nothing is written. `Missing` if the head is not there or nothing was changed. A
    `pydantic.ValidationError` of the `Update` (the head does not take what the change put in it) is raised, for the
    caller to say in its own words. `read`: what reads the head, if not `read_head`"""
    view = await (read or read_head)(model, head_id)
    if view is None:
        return Missing("head")
    data, found = change(editable(view.model_dump()))
    if not found:
        return Missing("part")
    return Prepared(view=view, update=model.Update(**data), version=view.meta.version)


async def rewrite(
    model: Any,
    head_id: UUID,
    change: Change,
    *,
    version: int | None = None,
    read: Callable[[Any, UUID], Awaitable[Any]] | None = None,
    **save_options: Any,
) -> Prepared | Missing:
    """`prepare_rewrite`, then the `Update` saved based on `version`, or the version read
    (`PanglossVersionConflictError` if the head has moved on since), with `save_options` (`instructions=`,
    `acknowledge_citations=`...). Gives what was prepared, or `Missing` (nothing written)"""
    prepared = await prepare_rewrite(model, head_id, change, read=read)
    if isinstance(prepared, Prepared):
        await prepared.update.save(
            expected_version=prepared.version if version is None else version,
            **save_options,
        )
    return prepared


__all__ = [
    "Change",
    "Missing",
    "Prepared",
    "Replace",
    "prepare_rewrite",
    "read_head",
    "replaced",
    "replaced_where",
    "rewrite",
]
