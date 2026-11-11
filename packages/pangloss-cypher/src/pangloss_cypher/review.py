"""Storing review (`pangloss-review`, implementation_docs/review.md): the state is properties of the head node
(`review_status`, `published`, `reviewed_by`, `reviewed_at`), and a comment is a `(:PGReviewComment)` node
with an edge `comment_on` to the head node. A comment is not an indexable node, so a document's tree, its
searches and its deletion never meet it.
"""

import datetime
from typing import Any
from uuid import UUID, uuid7

from pangloss_models.creators import usernames

from pangloss_cypher.values import native_datetime
from pangloss_cypher.transaction import Transaction
from pangloss_cypher import fragments

# (a document written before review was used is published: no status, and not `published: false`)
STATE_QUERY = f"""
MATCH (head:HeadNode:PGIndexableNode {{id: $id}})
WHERE NOT head:Entity AND {fragments.not_deleted("head")}
OPTIONAL MATCH (head)<-[:is_creation_of]-(creation:PGCreation)
CALL {{
    WITH head
    OPTIONAL MATCH (head)<-[:is_update_of]-(update:PGUpdate)-[:updated_by]->(editor:PGUser)
    RETURN editor.username AS last_edited_by
    ORDER BY update.updated_when DESC
    LIMIT 1
}}
RETURN head.id AS id, head.type AS type, head.label AS label,
       coalesce(head.review_status, CASE WHEN coalesce(head.published, true) THEN 'published' ELSE 'unchecked' END) AS status,
       coalesce(head.published, true) AS published,
       {fragments.creators("creation")} AS created_by,
       last_edited_by AS last_edited_by,
       head.reviewed_by AS reviewed_by, head.reviewed_at AS reviewed_at,
       head.review_assigned_to AS assigned_to, head.review_assigned_by AS assigned_by,
       head.review_assigned_at AS assigned_at,
       size([(head)<-[:comment_on]-(c:PGReviewComment) WHERE NOT coalesce(c.resolved, false) | c]) AS open_comments
"""


def state_from(record: Any) -> dict[str, Any]:
    state = dict(record)
    state["reviewed_at"] = native_datetime(state["reviewed_at"])
    state["assigned_at"] = native_datetime(state["assigned_at"])
    # (never edited: those who made it wrote it last, the first of them standing for all)
    if state["last_edited_by"] is None:
        state["last_edited_by"] = next(iter(usernames(state["created_by"])), None)
    return state


async def get_review_state(tx: Transaction, id: UUID) -> dict[str, Any] | None:
    result = await tx.run(STATE_QUERY, id=str(id))  # ty: ignore[invalid-argument-type]
    record = await result.single()
    return state_from(record) if record else None


async def set_review_status(
    tx: Transaction, id: UUID, status: str, published: bool, user: str
) -> dict[str, Any] | None:
    """Set the status, and with it whether the document is published. Gives the state, or None if there is no
    such document"""
    result = await tx.run(
        f"""
        MATCH (head:HeadNode:PGIndexableNode {{id: $id}})
        WHERE NOT head:Entity AND {fragments.not_deleted("head")}
        SET head.review_status = $status, head.published = $published,
            head.reviewed_by = $user, head.reviewed_at = $at
        RETURN head.id AS id
        """,  # ty: ignore[invalid-argument-type]
        id=str(id),
        status=status,
        published=published,
        user=user,
        at=datetime.datetime.now(datetime.UTC),
    )
    if not await result.single():
        return None
    return await get_review_state(tx, id)


async def assign_review(
    tx: Transaction, id: UUID, assignee: str | None, by: str
) -> dict[str, Any] | str | None:
    """Give a document to a user to review, or (None) to no one. Gives the state; None if there is no such document;
    or "user" if there is no such user"""
    if assignee is not None:
        found = await tx.run(
            "MATCH (user:PGUser {username: $username}) "
            "WHERE coalesce(user.kind, 'user') = 'user' AND NOT coalesce(user.disabled, false) "
            "RETURN user.username AS username",
            username=assignee,
        )
        if not await found.single():
            return "user"
    result = await tx.run(
        f"""
        MATCH (head:HeadNode:PGIndexableNode {{id: $id}})
        WHERE NOT head:Entity AND {fragments.not_deleted("head")}
        SET head.review_assigned_to = $assignee,
            head.review_assigned_by = CASE WHEN $assignee IS NULL THEN null ELSE $by END,
            head.review_assigned_at = CASE WHEN $assignee IS NULL THEN null ELSE $at END
        RETURN head.id AS id
        """,  # ty: ignore[invalid-argument-type]
        id=str(id),
        assignee=assignee,
        by=by,
        at=datetime.datetime.now(datetime.UTC),
    )
    if not await result.single():
        return None
    return await get_review_state(tx, id)


COMMENT_FIELDS = """
c.id AS id, c.username AS username, c.at AS at, c.text AS text,
c.target_id AS target_id, c.target_label AS target_label,
coalesce(c.resolved, false) AS resolved, c.resolved_by AS resolved_by, c.resolved_at AS resolved_at
"""


def comment_from(record: Any) -> dict[str, Any]:
    comment = dict(record)
    for key in ("at", "resolved_at"):
        comment[key] = native_datetime(comment[key])
    return comment


async def add_review_comment(
    tx: Transaction, id: UUID, username: str, text: str, target_id: UUID | None
) -> dict[str, Any] | str | None:
    """Add a comment. Gives it; None if there is no such document; or "target" if `target_id` is not a node
    of the document (what it is called is kept with the comment)"""
    result = await tx.run(
        f"""
        MATCH (head:HeadNode:PGIndexableNode {{id: $id}})
        WHERE NOT head:Entity AND {fragments.not_deleted("head")}
        OPTIONAL MATCH (part:PGIndexableNode {{id: $target_id, head_node_id: $id}})
        RETURN head.id AS id, part.label AS part_label, part IS NOT NULL AS part_found
        """,  # ty: ignore[invalid-argument-type]
        id=str(id),
        target_id=str(target_id) if target_id else None,
    )
    found = await result.single()
    if not found:
        return None
    if target_id and not found["part_found"]:
        return "target"
    comment_id = uuid7()
    result = await tx.run(
        f"""
        MATCH (head:HeadNode:PGIndexableNode {{id: $id}})
        CREATE (c:PGReviewComment {{
            id: $comment_id, username: $username, at: $at, text: $text,
            target_id: $target_id, target_label: $target_label, resolved: false
        }})-[:comment_on]->(head)
        RETURN {COMMENT_FIELDS}
        """,
        id=str(id),
        comment_id=str(comment_id),
        username=username,
        at=datetime.datetime.now(datetime.UTC),
        text=text,
        target_id=str(target_id) if target_id else None,
        target_label=found["part_label"] if target_id else None,
    )
    return comment_from(await result.single())


async def list_review_comments(
    tx: Transaction, id: UUID, include_resolved: bool
) -> list[dict[str, Any]]:
    result = await tx.run(
        f"""
        MATCH (c:PGReviewComment)-[:comment_on]->(head:HeadNode {{id: $id}})
        WHERE $include_resolved OR NOT coalesce(c.resolved, false)
        RETURN {COMMENT_FIELDS}
        ORDER BY c.at, c.id
        """,
        id=str(id),
        include_resolved=include_resolved,
    )
    return [comment_from(record) async for record in result]


async def resolve_review_comment(
    tx: Transaction, id: UUID, comment_id: UUID, user: str
) -> dict[str, Any] | None:
    result = await tx.run(
        f"""
        MATCH (c:PGReviewComment {{id: $comment_id}})-[:comment_on]->(head:HeadNode {{id: $id}})
        SET c.resolved = true, c.resolved_by = $user, c.resolved_at = $at
        RETURN {COMMENT_FIELDS}
        """,
        id=str(id),
        comment_id=str(comment_id),
        user=user,
        at=datetime.datetime.now(datetime.UTC),
    )
    record = await result.single()
    return comment_from(record) if record else None


async def review_queue(
    tx: Transaction,
    statuses: list[str],
    type: str | None,
    page: int,
    page_size: int,
    assigned_to: str | None = None,
    words: list[str] | None = None,
) -> dict[str, Any]:
    """Documents in the given statuses (those with a review status: not documents of classes not reviewed), the
    oldest change first. `assigned_to`: only those given to that user to review, or (an empty name) to no one.
    `words`: only those whose label has every one of them (whatever the case), anywhere in it"""
    result = await tx.run(
        f"""
        MATCH (head:HeadNode:PGIndexableNode)
        WHERE NOT head:Entity AND {fragments.not_deleted("head")}
          AND head.review_status IN $statuses
          AND ($type IS NULL OR $type IN labels(head))
          AND ($assigned_to IS NULL OR coalesce(head.review_assigned_to, '') = $assigned_to)
          AND all(word IN $words WHERE toLower(coalesce(head.label, '')) CONTAINS word)
        OPTIONAL MATCH (head)<-[:is_creation_of]-(creation:PGCreation)
        CALL {{
            WITH head
            OPTIONAL MATCH (head)<-[:is_update_of]-(update:PGUpdate)
            RETURN update.updated_when AS updated_when
            ORDER BY update.updated_when DESC
            LIMIT 1
        }}
        WITH head, creation, coalesce(updated_when, creation.created_when) AS changed_when
        ORDER BY changed_when, head.id
        WITH collect({{
            id: head.id, type: head.type, label: head.label, status: head.review_status,
            created_by: {fragments.creators("creation")}, changed_when: changed_when,
            reviewed_by: head.reviewed_by, assigned_to: head.review_assigned_to,
            open_comments: size([(head)<-[:comment_on]-(c:PGReviewComment) WHERE NOT coalesce(c.resolved, false) | c])
        }}) AS items
        RETURN size(items) AS count, items[($page - 1) * $page_size .. $page * $page_size] AS results
        """,  # ty: ignore[invalid-argument-type]
        statuses=statuses,
        type=type,
        page=page,
        page_size=page_size,
        assigned_to=assigned_to,
        words=[word.lower() for word in words or []],
    )
    record = await result.single()
    assert record is not None
    queue = dict(record)
    for item in queue["results"]:
        item["changed_when"] = native_datetime(item["changed_when"])
    return queue
