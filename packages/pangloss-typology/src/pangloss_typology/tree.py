"""The hierarchy of a typology as plain data (pure: no database, no models).

A type is a `Row`; the vocabulary is the rows by id. Each type has at most one supertype, so the hierarchy is a forest.
The service reads all the types of a typology (a vocabulary is hundreds to thousands) and answers from these; the
database checks a move again, in the transaction that makes it.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Row:
    id: str
    label: str
    parent: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)
    """Every property of the node (the labels in other languages, the description, `is_concrete`)"""


type Rows = dict[str, Row]


def sort_key(row: Row) -> tuple[str, str]:
    return (row.label.casefold(), row.id)


def children_of(rows: Rows, id: str | None) -> list[Row]:
    """The direct subtypes (the roots, for `None`), by label"""
    return sorted((r for r in rows.values() if r.parent == id), key=sort_key)


def ancestors(rows: Rows, id: str) -> list[Row]:
    """The supertypes, from the type's own parent up to the root. A parent that is not in `rows` (deleted) ends it; a
    loop (which a move never makes) ends it too"""
    found: list[Row] = []
    seen = {id}
    current = rows[id].parent if id in rows else None
    while current is not None and current in rows and current not in seen:
        seen.add(current)
        found.append(rows[current])
        current = rows[current].parent
    return found


def path(rows: Rows, id: str) -> list[Row]:
    """From the root to the type itself"""
    return [*reversed(ancestors(rows, id)), rows[id]]


def descendants(rows: Rows, id: str) -> list[Row]:
    """Everything below the type, depth first, each level by label"""
    found: list[Row] = []
    stack = children_of(rows, id)[::-1]
    seen = {id}
    while stack:
        row = stack.pop()
        if row.id in seen:
            continue
        seen.add(row.id)
        found.append(row)
        stack.extend(children_of(rows, row.id)[::-1])
    return found


def subtree_ids(rows: Rows, id: str) -> list[str]:
    """The type and everything below it"""
    return [id, *(r.id for r in descendants(rows, id))]


def would_loop(rows: Rows, id: str, to: str | None) -> bool:
    """Whether making `to` the supertype of `id` would make a loop: `to` is the type itself or below it"""
    return to is not None and (to == id or to in {r.id for r in descendants(rows, id)})


def nested(rows: Rows) -> list[dict[str, Any]]:
    """The whole hierarchy as nested dicts: `[{"id", "label", "children": [...]}]`, each level by label"""

    def node(row: Row) -> dict[str, Any]:
        return {
            "id": row.id,
            "label": row.label,
            "children": [node(c) for c in children_of(rows, row.id)],
        }

    roots = [r for r in rows.values() if r.parent is None or r.parent not in rows]
    return [node(r) for r in sorted(roots, key=sort_key)]
