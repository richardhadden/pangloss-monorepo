"""Mentions that cite a shared description (`Description`: implementation_docs/matches-criteria.md, "Shared
descriptions").

    MatchesCriteria(description={"type": "Description", "id": ...}, criteria=<its own, extra conditions, or none>)

A mention's **effective criteria** are the shared ones and its own (`pattern.combined`): what it is evaluated, checked,
chosen, hashed and explained by. Here, so that there is one of each:

- `cited_id(d)`: the fragment of Cypher by which every query reads which description a mention cites (by its
  citation, a `PGCitation` node below it: `target_id`);
- `shared_of(tx, ids)`: the one read of those descriptions' criteria;
- `effective(...)`: the criteria a mention is evaluated by, from its own, what it cites and the classes its place
  takes; raises for criteria that cannot be (the description cited is gone, a class that does not fit);
- `fill(node, allowed)`: on a save, what is worked out of the effective criteria (`models.worked_out`), set on the
  node before it is written (`MatchesCriteria.with_the_shared_criteria`), so that what is stored, and the basis the
  candidates are kept by, are of what the mention means;
- `in_write`: in the transaction of a write of a description, what is worked out of the effective criteria of every
  mention that cites it is written again, a mention that no longer fits is `broken` (one that fits again is
  cleared), and their documents are left for the worker. In the transaction of a write of a document that cites
  one, the same if the description has changed since the save read it (a write of it that came between).
"""

import contextvars
import dataclasses
from collections.abc import Iterable
from typing import Any

from pangloss_core import Transaction, backend
from pangloss_cypher import fragments, pending
from pangloss_models import ModelRegistry, PanglossSearchError, PanglossWriteRefused
from pangloss_models.citations import CITATION

from pangloss_criteria.holders import KIND
from pangloss_criteria.models import (
    DESCRIPTION,
    NAME,
    WORKED_OUT,
    worked_out,
)
from pangloss_criteria.pattern import SearchPattern, combined

# The field of a mention that cites a shared description
FIELD = "description"


def cited_id(d: str) -> str:
    """An expression: the id of the shared description the mention `d` cites (the `target_id` of its citation), or
    null. (From the mention, along its own edge: a query that reads mentions reads what they cite with this)"""
    edge, node = f"cited_edge_{d}", f"cited_node_{d}"
    return (
        f"head([({d})-[{edge}:{FIELD}]->({node}:{CITATION}) "
        f"WHERE NOT coalesce({edge}.reverse, false) | {node}.target_id])"
    )


@dataclasses.dataclass(frozen=True)
class Shared:
    """A shared description, as it is stored"""

    id: str
    label: str | None
    criteria: str | None
    deleted: bool


SHARED_QUERY = f"""
    UNWIND $ids AS id
    MATCH (s:PGIndexableNode {{id: id}})
    WHERE s:{DESCRIPTION}
    RETURN s.id AS id, s.label AS label, s.criteria AS criteria, {fragments.deleted("s")} AS deleted
"""


async def shared_of(tx: Transaction, ids: Iterable[Any]) -> dict[str, Shared]:
    """The shared descriptions of these ids, by id (one that is not there is left out)"""
    asked = sorted({str(id) for id in ids if id is not None})
    found: dict[str, Shared] = {}
    if asked:
        async for row in await tx.run(SHARED_QUERY, ids=asked):
            found[row["id"]] = Shared(
                id=row["id"],
                label=row["label"],
                criteria=row["criteria"],
                deleted=bool(row["deleted"]),
            )
    return found


def database() -> Any:
    return backend.current().database()


async def read_shared(ids: Iterable[Any]) -> dict[str, Shared]:
    """`shared_of`, in a transaction of its own"""

    @database().read_transaction
    async def read(tx: Transaction) -> dict[str, Shared]:
        return await shared_of(tx, ids)

    return await read()


def fits_place(pattern: SearchPattern, stands_for: Iterable[str]) -> None:
    """Raises `PanglossSearchError` if the criteria are of a class that the mention's place does not take
    (`stands_for`: the names of the classes it takes, as it was saved). Not checked if one of them is no class of the
    models now (a migration renamed it: the next save says what the place takes)"""
    names = list(stands_for or [])
    if not names:
        return
    models = ModelRegistry.all_models()
    classes = [models.get(name) for name in names]
    if any(not isinstance(cls, type) for cls in classes):
        return
    root = models.get(pattern.type)
    if not (isinstance(root, type) and any(issubclass(root, cls) for cls in classes)):  # ty: ignore[invalid-argument-type]
        raise PanglossSearchError(
            f"description: the criteria are of {pattern.type}, which is not taken here ({', '.join(sorted(names))})"
        )


def effective(
    own: Any,
    cited: Any,
    shared: dict[str, Shared],
    stands_for: Iterable[str] = (),
) -> SearchPattern | None:
    """The criteria a mention is evaluated by: its own (`own`, as stored, or None) and, if it cites a shared
    description (`cited`: its id), those of that one (`shared`, as `shared_of` read them). None for a mention with
    neither (a place of a mark that another place holds them for). Raises `PanglossSearchError` (or `ValueError`) if
    they cannot be: the description cited is not there, or deleted; its own are of a class that is not the shared
    one's nor below it; or what they are of is not what the place takes"""
    mine = None if own is None else SearchPattern(own)
    if cited is None:
        return mine
    found = shared.get(str(cited))
    if found is None or found.deleted or found.criteria is None:
        raise PanglossSearchError(
            f"description: the shared description {cited} that it cites is not there"
        )
    pattern = combined(SearchPattern(found.criteria), mine)
    fits_place(pattern, stands_for)
    return pattern


# --- on a save ----------------------------------------------------------------------------------------------------------

# What the saves of this request read of the descriptions their mentions cite: by head, the description's id and its
# criteria then. The write checks again in its transaction (`in_write`), where a write of the description cannot come
# between
_read_when_saved: contextvars.ContextVar[dict[str, dict[str, str | None]] | None] = (
    contextvars.ContextVar("pangloss_criteria_read_when_saved", default=None)
)


def _cited_of(node: Any) -> str | None:
    citation = getattr(node, FIELD, None)
    if citation is None:
        return None
    target = getattr(citation, "target_id", None)
    if target is None:
        raise PanglossWriteRefused(
            "A mention cites a shared description itself (a Description), not what stands for one",
            field=FIELD,
        )
    return str(target)


def forget_read(head_id: Any) -> None:
    """(after a write has committed, or failed) what its save read is no longer needed"""
    seen = _read_when_saved.get()
    if seen is not None:
        seen.pop(str(head_id), None)


def note_read(head_id: Any, shared: Shared) -> None:
    seen = _read_when_saved.get()
    if seen is None:
        seen = {}
        _read_when_saved.set(seen)
    seen.setdefault(str(head_id), {})[shared.id] = shared.criteria


async def fill(node: Any, allowed: Any, head_id: Any = None) -> None:
    """(`MatchesCriteria.with_the_shared_criteria`, before a save) for a mention that cites a shared description:
    its effective criteria checked against what its place takes (`allowed`), and what is worked out of them set on
    the node, to be written with it. Raises `PanglossWriteRefused` at the field that is wrong. A description that is
    not there is left for the write to refuse (the citation is checked when it is written)"""
    cited = _cited_of(node)
    if cited is None:
        return
    shared = await read_shared([cited])
    found = shared.get(cited)
    if found is None or found.deleted:
        return
    if head_id is not None:
        note_read(head_id, found)
    names = [cls.__name__ for cls in allowed or () if isinstance(cls, type)]
    try:
        values = worked_out(effective(node.criteria, cited, shared, names), allowed)
    except (PanglossSearchError, ValueError) as error:
        message = str(error)
        field = "criteria" if node.criteria is not None else FIELD
        if message.startswith(f"{FIELD}:"):
            field = FIELD
        raise PanglossWriteRefused(
            f"The criteria of this mention with those of the shared description it cites: {message}",
            field=field,
        ) from None
    for name, value in values.items():
        setattr(node, name, value)


async def fill_all(db_instance: Any) -> None:
    """What `fill` sets, on every mention of a head that cites a shared description, in a write form made outside a
    save (the step after a migration renews the bases of the candidates from one: `migrating`). One that does not
    fit is left as it is"""
    from pangloss_models import classes_stood_for, nodes_of

    for _, node in nodes_of(db_instance):
        owner = getattr(type(node), "_owner", None)
        if (
            getattr(owner, "__name__", None) != NAME
            or getattr(node, FIELD, None) is None
        ):
            continue
        try:
            await fill(node, classes_stood_for(node, "T"))
        except PanglossWriteRefused:
            continue


# --- in the transaction of a write --------------------------------------------------------------------------------------

_COLUMNS = f"""
    d.id AS id, d.head_node_id AS head, d.criteria AS criteria, d.stands_for AS stands_for,
    d.broken AS broken, d.broken_since AS broken_since,
    {", ".join(f"d.{name} AS {name}" for name in WORKED_OUT)}
"""

# The mentions that cite a description (by its citations: the index on `target_id`)
CITING_QUERY = f"""
    MATCH (citation:{CITATION} {{target_id: $id}})<-[edge:{FIELD}]-(d:{NAME})
    WHERE NOT coalesce(edge.reverse, false)
    RETURN $id AS cites, {_COLUMNS}
"""

# The mentions of a head that cite one
CITING_IN_HEAD_QUERY = f"""
    MATCH (d:PGIndexableNode {{head_node_id: $head}})
    WHERE d:{NAME}
    WITH d, {cited_id("d")} AS cites
    WHERE cites IS NOT NULL
    RETURN cites, {_COLUMNS}
"""

SET_QUERY = """
    UNWIND $rows AS row
    MATCH (d:PGIndexableNode {id: row.id})
    SET d += row.values
"""


def stored(value: Any) -> Any:
    """(as stored: an empty list and none are the same)"""
    if value is None or value == []:
        return None
    return list(value) if isinstance(value, (list, tuple)) else value


async def rework(tx: Transaction, rows: list[dict[str, Any]]) -> list[str]:
    """For mentions as read (`CITING_QUERY`): what is worked out of their effective criteria written again where it
    is another; a mention whose effective criteria no longer pass the check is `broken` (the reason; no
    `broken_since`: no migration did it), and one that was and passes now is cleared. Gives the heads of those that
    changed, which are marked for the worker (the others' criteria are what they were: their result is too)"""
    shared = await shared_of(tx, {row["cites"] for row in rows})
    updates: list[dict[str, Any]] = []
    heads: dict[str, None] = {}
    for row in rows:
        try:
            pattern = effective(
                row["criteria"], row["cites"], shared, row["stands_for"] or ()
            )
            found = worked_out(pattern)
        except (PanglossSearchError, ValueError) as error:
            if row["broken"] is None:
                updates.append({"id": row["id"], "values": {"broken": str(error)}})
                heads.setdefault(row["head"], None)
            continue
        values = {
            name: value
            for name, value in found.items()
            if stored(row[name]) != stored(value)
        }
        if row["broken"] is not None:
            values |= {"broken": None, "broken_since": None}
        if values:
            updates.append({"id": row["id"], "values": values})
            heads.setdefault(row["head"], None)
    if updates:
        await (await tx.run(SET_QUERY, rows=updates)).consume()
    marked = list(heads)
    await pending.mark(tx, KIND, marked)
    return marked


async def rework_citers(tx: Transaction, description_id: Any) -> list[str]:
    """`rework` of every mention that cites the description"""
    rows = [
        dict(row) async for row in await tx.run(CITING_QUERY, id=str(description_id))
    ]
    return await rework(tx, rows)


def is_description_class(model: Any) -> bool:
    """Whether a class is the shared description's (or one below it)"""
    base = ModelRegistry.all_models().get(DESCRIPTION)
    return (
        isinstance(base, type) and isinstance(model, type) and issubclass(model, base)
    )


async def in_write(tx: Transaction, op: str, model: type, id: Any) -> None:
    """(`hooks.in_write`) a write of a shared description: the mentions that cite it worked out again (`rework`).
    A create or update of a document whose mentions cite one: the same, if a description its save read has been
    written since (in this transaction it is as it is now). Safe to run twice"""
    if is_description_class(model):
        await rework_citers(tx, id)
        return
    if op not in ("create", "update"):
        return
    seen = _read_when_saved.get()
    # (not taken off here: the transaction may be run again. `forget_read`, once it has committed)
    read = None if seen is None else seen.get(str(id))
    if not read:
        return
    now = await shared_of(tx, read)
    if all(
        found is not None and not found.deleted and found.criteria == read[key]
        for key, found in ((key, now.get(key)) for key in read)
    ):
        return
    rows = [dict(row) async for row in await tx.run(CITING_IN_HEAD_QUERY, head=str(id))]
    await rework(tx, rows)


__all__ = [
    "FIELD",
    "Shared",
    "cited_id",
    "effective",
    "fill",
    "fill_all",
    "fits_place",
    "in_write",
    "read_shared",
    "rework",
    "rework_citers",
    "shared_of",
    "stored",
]
