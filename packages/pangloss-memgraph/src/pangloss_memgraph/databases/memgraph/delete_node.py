"""Deleting (and undeleting) a head document or an entity.

Nothing is removed from the database. A deleted node has `deleted: true`, and a
`PGDeletion` record of who deleted it and when (as `PGCreation` and `PGUpdate` record
those of creating and updating it). Everything that reads the database leaves out
deleted nodes: a nested node is deleted with its head document, and has no flag of
its own.

- Only head documents can be deleted, not the documents nested in them.
- An entity can only be deleted if nothing refers to it: no document, and no other
  entity, that has not been deleted itself. If something does, it is not deleted, but
  is marked (`marked_for_deletion`, in its `meta`), so that it is known that someone
  wanted it gone.
- A deleted node can be undeleted: the flag is removed, and a `PGUndeletion` record is
  added (the `PGDeletion` record is kept, as history).
"""

import dataclasses
import datetime
import typing
import uuid
from uuid import UUID

from pangloss_models.exceptions import (
    PanglossNotDeletableError,
    PanglossNotDeletedError,
    PanglossNotFoundError,
)
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from pangloss_users import current_request_username
from pydantic import AnyHttpUrl

from pangloss_memgraph.databases.memgraph.database import Transaction
from pangloss_memgraph.databases.memgraph.lookup import resolve_id
from pangloss_memgraph.databases.memgraph.validate_write import check_user_exists

# How many of the things that refer to an entity are reported
MAX_REFERENCES_REPORTED = 10


@dataclasses.dataclass
class DeletionResult:
    deleted: bool
    # (if not deleted) what refers to the entity: dicts with `id`, `type` and `label`
    referenced_by: list[dict[str, typing.Any]] = dataclasses.field(default_factory=list)
    reference_count: int = 0


FIND_QUERY = """
    MATCH (node:PGIndexableNode {id: $id})
    WHERE $type IN labels(node)
    OPTIONAL MATCH (head:HeadNode {id: node.head_node_id})
    RETURN node:HeadNode AS is_head_node,
           coalesce(node.deleted, false) AS deleted,
           coalesce(head.deleted, false) AS head_deleted
"""

# What refers to an entity: the reverse edges leading out of it go to the nodes that
# hold each relation (possibly inside a document), whose head documents or entities
# count, unless they have been deleted
REFERENCES_QUERY = """
    MATCH (entity:PGIndexableNode {id: $id})-[reverse_edge]->(referrer)
    WHERE coalesce(reverse_edge.reverse, false)
    OPTIONAL MATCH (head:HeadNode {id: referrer.head_node_id})
    WITH entity,
         CASE WHEN referrer:Entity THEN referrer ELSE coalesce(head, referrer) END AS holder
    WHERE NOT coalesce(holder.deleted, false) AND holder <> entity
    RETURN DISTINCT holder.id AS id, holder.type AS type, holder.label AS label
    ORDER BY id
"""

MARK_QUERY = """
    MATCH (entity:PGIndexableNode {id: $id})
    SET entity.marked_for_deletion = true,
        entity.marked_for_deletion_by = $username,
        entity.marked_for_deletion_when = $when
"""

DELETE_QUERY = """
    MATCH (user:PGUser {username: $username})
    MATCH (node:PGIndexableNode {id: $id})
    CREATE (deletion:PGDeletion)
    SET deletion = $deletion
    CREATE (deletion)-[:is_deletion_of]->(node)
    CREATE (deletion)-[:deleted_by]->(user)
    SET node.deleted = true
    REMOVE node.marked_for_deletion,
           node.marked_for_deletion_by,
           node.marked_for_deletion_when
    RETURN node.id AS id
"""


async def soft_delete(
    tx: Transaction, cls: type[Document | Entity], id: UUID | AnyHttpUrl
) -> DeletionResult:
    """Delete a head document or entity, or, if it is an entity that is referred to,
    mark it. (An entity cannot be marked and then rejected inside a transaction: the
    caller raises the error, after the transaction has committed.)"""

    is_entity = cls.__metatype__ == "Entity"

    await check_user_exists(tx)

    resolved_id = await resolve_id(tx, id) if is_entity else id
    if resolved_id is None:
        raise PanglossNotFoundError(f"There is no {cls.__name__} with id {id}")
    node_id = str(resolved_id)

    result = await tx.run(FIND_QUERY, id=node_id, type=cls.__name__)
    found = await result.data()
    # (a document nested in a deleted document is gone with it)
    if not found or found[0]["deleted"] or (not is_entity and found[0]["head_deleted"]):
        raise PanglossNotFoundError(f"There is no {cls.__name__} with id {id}")

    if not is_entity and not found[0]["is_head_node"]:
        raise PanglossNotDeletableError(
            f"{cls.__name__} {id} is part of another document, and cannot be deleted "
            "on its own: only documents that are not nested in another can be deleted"
        )

    if is_entity:
        result = await tx.run(REFERENCES_QUERY, id=node_id)
        references = await result.data()
        if references:
            await tx.run(
                MARK_QUERY,
                id=node_id,
                username=current_request_username.get(),
                when=datetime.datetime.now(datetime.UTC),
            )
            return DeletionResult(
                deleted=False,
                referenced_by=references[:MAX_REFERENCES_REPORTED],
                reference_count=len(references),
            )

    result = await tx.run(
        DELETE_QUERY,
        id=node_id,
        username=current_request_username.get(),
        deletion={
            "id": str(uuid.uuid7()),
            "deleted_when": datetime.datetime.now(datetime.UTC),
        },
    )
    await result.consume()
    return DeletionResult(deleted=True)


UNDELETE_QUERY = """
    MATCH (user:PGUser {username: $username})
    MATCH (node:PGIndexableNode {id: $id})
    CREATE (undeletion:PGUndeletion)
    SET undeletion = $undeletion
    CREATE (undeletion)-[:is_undeletion_of]->(node)
    CREATE (undeletion)-[:undeleted_by]->(user)
    REMOVE node.deleted
    RETURN node.id AS id
"""


async def undelete(
    tx: Transaction, cls: type[Document | Entity], id: UUID | AnyHttpUrl
) -> None:
    """Restore a deleted head document or entity"""

    is_entity = cls.__metatype__ == "Entity"

    await check_user_exists(tx)

    resolved_id = await resolve_id(tx, id) if is_entity else id
    if resolved_id is None:
        raise PanglossNotFoundError(f"There is no {cls.__name__} with id {id}")
    node_id = str(resolved_id)

    result = await tx.run(FIND_QUERY, id=node_id, type=cls.__name__)
    found = await result.data()
    if not found:
        raise PanglossNotFoundError(f"There is no {cls.__name__} with id {id}")

    if not is_entity and not found[0]["is_head_node"]:
        raise PanglossNotDeletableError(
            f"{cls.__name__} {id} is part of another document, and cannot be "
            "deleted or undeleted on its own"
        )

    if not found[0]["deleted"]:
        raise PanglossNotDeletedError(f"{cls.__name__} {id} has not been deleted")

    result = await tx.run(
        UNDELETE_QUERY,
        id=node_id,
        username=current_request_username.get(),
        undeletion={
            "id": str(uuid.uuid7()),
            "undeleted_when": datetime.datetime.now(datetime.UTC),
        },
    )
    await result.consume()
