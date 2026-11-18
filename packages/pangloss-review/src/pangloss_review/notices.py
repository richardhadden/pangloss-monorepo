"""Notices: what an installed app says of a reviewed document that a person should look at (`hooks.give_notice`:
`pangloss-derived` says that a document was made from a derived one, the core that a derivation a document cites no
longer holds). Here one is an open comment on the document, with the `kind` the app gave: it is in the review panel,
counted in the queue (which can be asked for the documents that have one), and resolved as any comment is. The
document stays as it is: published, if it was.

Written in the transaction the notice comes from, which may be run again: a notice of one kind about one part is one
comment (its id is worked out), opened again if it had been resolved."""

import datetime
import uuid
from typing import Any

from pangloss_models import ModelRegistry, hooks

from pangloss_review.meta import is_reviewable

# (who says it, when nobody did what it comes from)
NOBODY = "pangloss"

NAMESPACE = uuid.UUID("6f1f0e0c-51a5-5d0a-9a35-6a3a1a1f4b0e")

NOTICE_QUERY = """
MATCH (head:HeadNode {id: $id})
MERGE (c:PGReviewComment {id: $comment_id})
SET c.username = $username, c.at = $at, c.text = $text, c.kind = $kind,
    c.target_id = $target_id, c.target_label = $target_label, c.resolved = false
REMOVE c.resolved_by, c.resolved_at
MERGE (c)-[:comment_on]->(head)
RETURN count(c) AS written
"""

CLEAR_QUERY = """
MATCH (c:PGReviewComment)-[:comment_on]->(head:HeadNode {id: $id})
WHERE c.kind IN $kinds AND coalesce(c.target_id, '') = $target_id AND NOT coalesce(c.resolved, false)
SET c.resolved = true, c.resolved_by = $username, c.resolved_at = $at
RETURN count(c) AS cleared
"""


def comment_id(notice: hooks.Notice) -> uuid.UUID:
    return uuid.uuid5(
        NAMESPACE, f"{notice.head_id}:{notice.target_id or ''}:{notice.kind}"
    )


async def notice(tx: Any, given: hooks.Notice) -> None:
    """(`hooks.notices`) nothing for a document of a class that is not reviewed: it has no comments"""
    model = ModelRegistry._model_dict.get(given.head_type)
    if model is None or not is_reviewable(model):
        return
    now = datetime.datetime.now(datetime.UTC)
    username = given.user or NOBODY
    target = str(given.target_id) if given.target_id else None
    if given.clears:
        result = await tx.run(
            CLEAR_QUERY,
            id=str(given.head_id),
            kinds=list(given.clears),
            target_id=target or "",
            username=username,
            at=now,
        )
        await result.consume()
    if given.kind:
        result = await tx.run(
            NOTICE_QUERY,
            id=str(given.head_id),
            comment_id=str(comment_id(given)),
            username=username,
            at=now,
            text=given.text,
            kind=given.kind,
            target_id=target,
            target_label=given.target_label,
        )
        await result.consume()


def install() -> None:
    if notice not in hooks.notices:
        hooks.notices.append(notice)
