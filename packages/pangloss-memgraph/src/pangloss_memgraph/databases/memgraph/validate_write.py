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
    PanglossUserDisabledError,
    PanglossUserNotFoundError,
)
from pangloss_users import current_request_username

from pangloss_memgraph.databases.memgraph.build_create_query import (
    ExistingEntity,
    InlineEntity,
    InlineEntityKey,
    QueryObject,
)
from pangloss_memgraph.databases.memgraph.build_update_query import (
    build_head_query,
    build_tree_meta_query,
)
from pangloss_memgraph.databases.memgraph.database import Transaction


@dataclasses.dataclass
class ExistingHead:
    created_by: str | None
    created_when: typing.Any
    version: int = 1


async def check_user_exists(tx: Transaction) -> None:
    username = current_request_username.get()
    result = await tx.run(
        """
        MATCH (user:PGUser {username: $username})
        RETURN coalesce(user.disabled, false) AS disabled
        """,
        username=username,
    )
    found = await result.value()
    if not found:
        raise PanglossUserNotFoundError(f"There is no user '{username}'")
    if found[0]:
        raise PanglossUserDisabledError(f"The user '{username}' is disabled")


async def check_references_exist(tx: Transaction, query_object: QueryObject) -> None:
    """Check that every existing entity referred to exists and is of an allowed type"""

    by_id = [r for r in query_object.references if not r.is_url]
    by_url = [r for r in query_object.references if r.is_url]

    found: dict[str, list[set[str]]] = {}
    deleted_values: set[str] = set()

    if by_id:
        result = await tx.run(
            """
            UNWIND $values AS value
            OPTIONAL MATCH (node:PGIndexableNode {id: value})
            RETURN value, labels(node) AS labels, node.deleted AS deleted
            """,
            values=sorted({r.value for r in by_id}),
        )
        for value, labels, deleted in await result.values():
            found.setdefault(value, []).append(set(labels or []))
            if deleted:
                deleted_values.add(value)

    if by_url:
        result = await tx.run(
            """
            UNWIND $values AS value
            OPTIONAL MATCH (:PGUrl {url: value})<-[:has_url]-(node:PGIndexableNode)
            RETURN value, labels(node) AS labels, node.deleted AS deleted
            """,
            values=sorted({r.value for r in by_url}),
        )
        for value, labels, deleted in await result.values():
            found.setdefault(value, []).append(set(labels or []))
            if deleted:
                deleted_values.add(value)

    problems = []
    for reference in query_object.references:
        matches = [labels for labels in found.get(reference.value, []) if labels]
        if not matches:
            problems.append(f"{reference.field_name}: '{reference.value}' not found")
        elif reference.value in deleted_values:
            problems.append(
                f"{reference.field_name}: '{reference.value}' has been deleted"
            )
        elif not any(set(reference.allowed_types) & labels for labels in matches):
            problems.append(
                f"{reference.field_name}: '{reference.value}' is not of an allowed type "
                f"({', '.join(reference.allowed_types)})"
            )
    if problems:
        raise PanglossReferenceError(
            "Invalid references to existing objects: " + "; ".join(problems)
        )


async def find_existing_entities(
    tx: Transaction, inline_entities: list[InlineEntity]
) -> dict[InlineEntityKey, ExistingEntity]:
    """Which of the entities written in a document (by their id or URL) exist"""
    ids = sorted({e.key[1] for e in inline_entities if e.key[0] == "id"})
    urls = sorted({e.key[1] for e in inline_entities if e.key[0] == "url"})
    existing: dict[InlineEntityKey, ExistingEntity] = {}

    for kind, values, query in (
        (
            "id",
            ids,
            """
            UNWIND $values AS value
            MATCH (node:PGIndexableNode {id: value})
            RETURN value, node.id AS id, labels(node) AS labels, node.deleted AS deleted
            ORDER BY id
            """,
        ),
        (
            "url",
            urls,
            """
            UNWIND $values AS value
            MATCH (:PGUrl {url: value})<-[:has_url]-(node:PGIndexableNode)
            RETURN value, node.id AS id, labels(node) AS labels, node.deleted AS deleted
            ORDER BY id
            """,
        ),
    ):
        if not values:
            continue
        result = await tx.run(query, values=values)  # type: ignore
        for value, id, labels, deleted in await result.values():
            existing.setdefault(
                (kind, value),
                ExistingEntity(id=id, labels=frozenset(labels), deleted=bool(deleted)),
            )
    return existing


def check_inline_entities(
    inline_entities: list[InlineEntity],
    existing: dict[InlineEntityKey, ExistingEntity],
) -> None:
    """Check that an entity written in a document, if it exists, can be the one the
    document means: it is an entity, of an allowed type, that has not been deleted"""
    problems = []
    for entity in inline_entities:
        found = existing.get(entity.key)
        if found is None:
            continue
        name = f"{entity.field_name}: '{entity.key[1]}'"
        if "Entity" not in found.labels:
            problems.append(f"{name} is used by something that is not an entity")
        elif found.deleted:
            problems.append(f"{name} has been deleted")
        elif not set(entity.allowed_types) & found.labels:
            problems.append(
                f"{name} is an entity of another type (not "
                f"{', '.join(entity.allowed_types)})"
            )
    if problems:
        raise PanglossConflictError(
            "Entities in the document are not the existing ones: " + "; ".join(problems)
        )


async def check_urls_available(tx: Transaction, query_object: QueryObject) -> None:
    """Check that no URL of a new entity is already the URL of an entity"""
    if not query_object.urls_to_write:
        return
    result = await tx.run(
        "UNWIND $urls AS url MATCH (node:PGUrl {url: url}) RETURN node.url AS url",
        urls=sorted(set(query_object.urls_to_write)),
    )
    in_use = [url for (url,) in await result.values()]
    if in_use:
        raise PanglossConflictError(f"URLs {in_use} are already in use")


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
    if not records or head_type not in records[0][0] or records[0][3]:
        raise PanglossNotFoundError(f"There is no {head_type} with id {head_id}")
    _, created_when, created_by, _, version = records[0]
    return ExistingHead(
        created_by=created_by, created_when=created_when, version=version
    )


async def get_tree_meta(
    tx: Transaction, head_id: uuid.UUID
) -> dict[str, dict[str, typing.Any]]:
    query, params = build_tree_meta_query(head_id)
    result = await tx.run(query, **params)
    return {id: meta for id, meta in await result.values()}
