"""Checks made inside a write transaction before anything is written, so that
a write that cannot succeed fails with a useful error, instead of silently
writing nothing (or, for an update, deleting data and writing nothing)."""

import dataclasses
import typing
import uuid

from pangloss_models.exceptions import (
    PanglossConflictError,
    PanglossNotFoundError,
    PanglossReferenceError,
    PanglossUserNotFoundError,
)
from pangloss_users import current_request_username

from pangloss_memgraph.databases.memgraph.build_create_query import QueryObject
from pangloss_memgraph.databases.memgraph.build_update_query import (
    build_head_query,
    build_tree_meta_query,
)
from pangloss_memgraph.databases.memgraph.database import Transaction


@dataclasses.dataclass
class ExistingHead:
    created_by: str | None
    created_when: typing.Any


async def check_user_exists(tx: Transaction) -> None:
    username = current_request_username.get()
    result = await tx.run(
        "MATCH (user:PGUser {username: $username}) RETURN user.username AS username",
        username=username,
    )
    if not await result.value():
        raise PanglossUserNotFoundError(f"There is no user '{username}'")


async def check_references_exist(tx: Transaction, query_object: QueryObject) -> None:
    """Check that every existing entity referred to exists and is of an allowed type"""

    by_id = [r for r in query_object.references if not r.is_url]
    by_url = [r for r in query_object.references if r.is_url]

    found: dict[str, list[set[str]]] = {}

    if by_id:
        result = await tx.run(
            """
            UNWIND $values AS value
            OPTIONAL MATCH (node:PGIndexableNode {id: value})
            RETURN value, labels(node) AS labels
            """,
            values=sorted({r.value for r in by_id}),
        )
        for value, labels in await result.values():
            found.setdefault(value, []).append(set(labels or []))

    if by_url:
        result = await tx.run(
            """
            UNWIND $values AS value
            OPTIONAL MATCH (node:PGIndexableNode)
            WHERE value IN node.urls
            RETURN value, labels(node) AS labels
            """,
            values=sorted({r.value for r in by_url}),
        )
        for value, labels in await result.values():
            found.setdefault(value, []).append(set(labels or []))

    problems = []
    for reference in query_object.references:
        matches = [labels for labels in found.get(reference.value, []) if labels]
        if not matches:
            problems.append(f"{reference.field_name}: '{reference.value}' not found")
        elif not any(set(reference.allowed_types) & labels for labels in matches):
            problems.append(
                f"{reference.field_name}: '{reference.value}' is not of an allowed type "
                f"({', '.join(reference.allowed_types)})"
            )
    if problems:
        raise PanglossReferenceError(
            "Invalid references to existing objects: " + "; ".join(problems)
        )


async def check_ids_available(
    tx: Transaction, query_object: QueryObject, is_update: bool
) -> None:
    """Check that no id given for a new node is already used.

    When updating, nodes already below the head node being updated may be given
    again (they are replaced), but nodes belonging to anything else may not.
    Entities written inline are not checked: one that exists is left as it is."""

    ids = {str(query_object.head_id)}
    ids.update(n.id for n in query_object.nodes_to_write if not n.is_entity)

    result = await tx.run(
        """
        UNWIND $ids AS id
        MATCH (node:PGIndexableNode {id: id})
        RETURN node.id AS id, node.head_node_id AS head_node_id
        """,
        ids=sorted(ids),
    )
    head_id = str(query_object.head_id)
    in_use = [
        id
        for id, head_node_id in await result.values()
        if not (is_update and (id == head_id or head_node_id == head_id))
    ]
    if in_use:
        if is_update:
            raise PanglossConflictError(
                f"Ids {in_use} belong to objects that are not part of {head_id}"
            )
        raise PanglossConflictError(f"Ids {in_use} are already in use")


async def get_existing_head(
    tx: Transaction, head_id: uuid.UUID, head_type: str
) -> ExistingHead:
    query, params = build_head_query(head_id)
    result = await tx.run(query, **params)
    records = await result.values()
    if not records or head_type not in records[0][0]:
        raise PanglossNotFoundError(f"There is no {head_type} with id {head_id}")
    _, created_when, created_by = records[0]
    return ExistingHead(created_by=created_by, created_when=created_when)


async def get_tree_meta(
    tx: Transaction, head_id: uuid.UUID
) -> dict[str, dict[str, typing.Any]]:
    query, params = build_tree_meta_query(head_id)
    result = await tx.run(query, **params)
    return {id: meta for id, meta in await result.values()}
