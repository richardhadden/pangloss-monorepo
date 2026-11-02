"""Relinking: everything that has a relation to one node has it to another instead (`relink`), as a write to each head
that changes, a batch of heads at a time.

It is what a merge of two entities needs (a typology's `merge`: what had the first type has the second). Saving each
head that refers to the first is too slow for thousands of them, so the edges are rewired here, in batches; but each
head that changes is written as an update is:

- a `PGUpdate` (by the user of the request), so its version goes up by one, and an edit made from the version before is
  refused (`PanglossVersionConflictError`);
- a write event after each batch commits (`pangloss_models.hooks`), with what the head is now, so that `pangloss-history`
  records the version.

The head of a node is the node itself, or the head node of the document it is in (`head_node_id`). The properties of an
edge (a `ViaEdge`) go to the new edge, and its place in its list (`pg_position`, on the forward edge only). A node that already has the relation to the other node keeps the edge it has.
"""

import datetime
import logging
import uuid
from collections.abc import Awaitable, Callable, Collection
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pangloss_models import hooks
from pangloss_models.exceptions import PanglossWriteError
from pangloss_models.model_registry import ModelRegistry
from pangloss_users import current_request_username
from pydantic import ValidationError

from pangloss_cypher.build_tree import POSITION
from pangloss_cypher.checks import check_user_exists
from pangloss_cypher.fragments import field_edge
from pangloss_cypher.read_functions import get_document, get_entity_for_edit
from pangloss_cypher.transactions import Transaction, dialect, write_transaction
from pangloss_cypher.write_functions import announce

logger = logging.getLogger("pangloss.relink")

# The heads written in one transaction
RELINK_BATCH = 1000

type BeforeRelink = Callable[[Transaction], Awaitable[None]]


@dataclass(frozen=True)
class RelinkedHead:
    id: str
    type: str
    version: int
    """The version the relink made"""


def editable(value: Any) -> Any:
    """What was read, without what is only for reading (`meta`, and the fields of incoming relations): what an `Update`
    takes"""
    if isinstance(value, dict):
        return {
            k: editable(v)
            for k, v in value.items()
            if k != "meta" and not k.endswith("_reverse")
        }
    if isinstance(value, list):
        return [editable(v) for v in value]
    return value


async def written_form(model: Any, id: UUID) -> Any | None:
    """What the head is now, as an update of it would write it (the payload of a write event), or None if it cannot be
    read (deleted) or made into an update"""
    if model.__metatype__ == "Entity":
        view = await get_entity_for_edit(model, id)
    else:
        view = await get_document(model, id)
    if view is None:
        return None
    try:
        return model.Update(**editable(view.model_dump()))._to_db_model()
    except ValidationError:
        logger.warning(
            "%s %s was relinked, but what it is now could not be made into an update: "
            "its version is recorded without its content",
            model.__name__,
            id,
        )
        return None


async def announce_relinked(heads: list[RelinkedHead]) -> None:
    for head in heads:
        model = ModelRegistry.all_models().get(head.type)
        if model is None:
            logger.warning(
                "Relinked %s %s, which is not a model of now", head.type, head.id
            )
            continue
        # (what it is now is read only if something listens)
        payload = (
            await written_form(model, UUID(head.id)) if hooks.after_write else None
        )
        announce("update", model, UUID(head.id), head.version, payload)


@write_transaction
async def relink_batch(
    tx: Transaction,
    field: str,
    reverse: str,
    from_id: str,
    to_id: str,
    keep: list[str],
    before: BeforeRelink | None,
    batch_size: int,
) -> list[RelinkedHead]:
    """One batch of `relink`, in one transaction: the heads it wrote"""
    await check_user_exists(tx)
    if before is not None:
        await before(tx)
    forward, backward = field_edge(field), field_edge(reverse)
    found = await tx.run(
        f"""
        MATCH (:PGIndexableNode {{id: $from_id}})<-[old:{forward}]-(e:PGIndexableNode)
        WHERE NOT coalesce(old.reverse, false) AND NOT e.id IN $keep
        WITH DISTINCT e
        LIMIT $batch_size
        RETURN e.id AS id, coalesce(e.head_node_id, e.id) AS head
        """,  # ty: ignore[invalid-argument-type]
        from_id=from_id,
        keep=keep,
        batch_size=batch_size,
    )
    rows = await found.data()
    if not rows:
        return []
    ids = [row["id"] for row in rows]
    heads = sorted({row["head"] for row in rows})
    # (as an update does: Neo4j takes the lock of each head, so that an update of one waits for this, or this for it)
    for head in heads:
        await dialect().before_replace(tx, head)

    # The new pair of edges, with the properties of the old edge, unless the node has the relation to the other already
    await (
        await tx.run(
            f"""
            UNWIND $ids AS node_id
            MATCH (e:PGIndexableNode {{id: node_id}})-[old:{forward}]->(:PGIndexableNode {{id: $from_id}})
            WHERE NOT coalesce(old.reverse, false)
            WITH e, collect(old)[0] AS old
            MATCH (b:PGIndexableNode {{id: $to_id}})
            WHERE NOT EXISTS {{ MATCH (e)-[already:{forward}]->(b) WHERE NOT coalesce(already.reverse, false) }}
            CREATE (e)-[new:{forward}]->(b)
            SET new = properties(old)
            CREATE (e)<-[new_reverse:{backward}]-(b)
            SET new_reverse = properties(old), new_reverse.reverse = true
            REMOVE new_reverse.{POSITION}
            """,  # ty: ignore[invalid-argument-type]
            ids=ids,
            from_id=from_id,
            to_id=to_id,
        )
    ).consume()
    # The old pairs go
    deleted = await (
        await tx.run(
            f"""
            UNWIND $ids AS node_id
            MATCH (e:PGIndexableNode {{id: node_id}})-[old:{forward}]->(a:PGIndexableNode {{id: $from_id}})
            WHERE NOT coalesce(old.reverse, false)
            OPTIONAL MATCH (a)-[old_reverse:{backward}]->(e)
            WHERE coalesce(old_reverse.reverse, false)
            WITH collect(DISTINCT old) + collect(DISTINCT old_reverse) AS gone
            UNWIND gone AS edge
            DELETE edge
            RETURN count(*) AS deleted
            """,  # ty: ignore[invalid-argument-type]
            ids=ids,
            from_id=from_id,
        )
    ).single()
    if not deleted or not deleted["deleted"]:
        # (else the next batch would find the same edges, for ever)
        raise PanglossWriteError(f"The {field} edges to {from_id} were not removed")
    # A record of the update of each head, as an update makes
    await (
        await tx.run(
            """
            MATCH (user:PGUser {username: $username})
            UNWIND $updates AS made
            MATCH (head:HeadNode {id: made.head})
            CREATE (update:PGUpdate)
            SET update = {id: made.id, updated_when: $when}
            CREATE (update)-[:is_update_of]->(head)
            CREATE (update)-[:updated_by]->(user)
            """,
            username=current_request_username.get(),
            updates=[{"head": head, "id": str(uuid.uuid7())} for head in heads],
            when=datetime.datetime.now(datetime.UTC),
        )
    ).consume()
    versions = await tx.run(
        """
        UNWIND $heads AS head_id
        MATCH (head:HeadNode {id: head_id})
        RETURN head.id AS id, head.type AS type,
               size([(head)<-[:is_update_of]-(update:PGUpdate) | update]) + 1 AS version
        """,
        heads=heads,
    )
    return [
        RelinkedHead(id=row["id"], type=row["type"], version=row["version"])
        for row in await versions.data()
    ]


async def relink(
    field: str,
    reverse: str,
    from_id: UUID | str,
    to_id: UUID | str,
    *,
    keep: Collection[UUID | str] = (),
    before: BeforeRelink | None = None,
    batch_size: int = RELINK_BATCH,
) -> int:
    """Everything that has the relation `field` (whose reverse edge is `reverse`) to the node `from_id` has it to `to_id`
    instead, except the nodes in `keep`. Each head that changes gets a new version, and its write event when its batch
    has committed. `before` is called first in the transaction of each batch (to take a lock, and check what the lock
    keeps true). Gives the number of heads written.

    The batches are transactions of their own: if one fails, those before it stay written, and running it again goes on
    from there."""
    written = 0
    while True:
        heads = await relink_batch(
            field,
            reverse,
            str(from_id),
            str(to_id),
            [str(k) for k in keep],
            before,
            batch_size,
        )
        if not heads:
            return written
        written += len(heads)
        await announce_relinked(heads)
