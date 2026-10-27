"""Review: what can be done with the state and the comments of a document.

The state is kept by the database backend (`DATABASE_MODULE`), which supplies, in its `exposed_functions`:
`get_review_state_in_db`, `set_review_status_in_db`, `add_review_comment_in_db`, `list_review_comments_in_db`,
`resolve_review_comment_in_db` and `review_queue_in_db`. What is decided here is who may do what.
"""

import importlib
from types import ModuleType
from uuid import UUID

from pangloss_core import settings as core_settings
from pangloss_models.model_registry import ModelRegistry

from pangloss_review import config
from pangloss_review.exceptions import (
    PanglossCommentTargetError,
    PanglossNoSuchCommentError,
    PanglossNotReviewableError,
    PanglossSelfReviewError,
)
from pangloss_review.meta import is_reviewable
from pangloss_review.status import (
    Comment,
    Queue,
    QueueItem,
    ReviewDetail,
    ReviewState,
    ReviewStatus,
)


def _backend() -> ModuleType:
    database = core_settings.SETTINGS.DATABASE_MODULE
    return importlib.import_module(f"{database}.exposed_functions")


def _reviewable(state: dict | None, id: UUID) -> ReviewState:
    model = ModelRegistry._model_dict.get(state["type"]) if state else None
    if state is None or model is None or not is_reviewable(model):
        raise PanglossNotReviewableError(
            f"{id} is not a document that is reviewed (there is no such document, or its class is not "
            "reviewable)"
        )
    return ReviewState(**state)


async def get_state(id: UUID) -> ReviewState:
    return _reviewable(await _backend().get_review_state_in_db(id), id)


async def set_status(
    id: UUID, status: ReviewStatus, user: str, comment: str | None = None
) -> ReviewState:
    """Check a document: `checked` publishes it, the others do not (and unpublish it, if it was). With
    `REVIEW_ALLOW_SELF_REVIEW` false, the user must not have created or last edited it. A comment is added
    with the change."""
    backend = _backend()
    current = _reviewable(await backend.get_review_state_in_db(id), id)
    if not config.allow_self_review() and user in (
        current.created_by,
        current.last_edited_by,
    ):
        raise PanglossSelfReviewError(
            f"{user} created or last edited this document, and cannot check it"
        )
    changed = await backend.set_review_status_in_db(
        id, status.value, status.published, user
    )
    if comment:
        await add_comment(id, user, comment)
        changed = await backend.get_review_state_in_db(id)
    return _reviewable(changed, id)


async def add_comment(
    id: UUID, username: str, text: str, target_id: UUID | None = None
) -> Comment:
    """A comment on a document, or on a part of it (`target_id`: a node of the document)"""
    backend = _backend()
    _reviewable(await backend.get_review_state_in_db(id), id)
    made = await backend.add_review_comment_in_db(id, username, text.strip(), target_id)
    if made == "target":
        raise PanglossCommentTargetError(
            f"{target_id} is not a part of the document {id}"
        )
    if made is None:
        raise PanglossNotReviewableError(f"No such document {id}")
    return Comment(**made)


async def list_comments(id: UUID, include_resolved: bool = False) -> list[Comment]:
    backend = _backend()
    _reviewable(await backend.get_review_state_in_db(id), id)
    found = await backend.list_review_comments_in_db(id, include_resolved)
    return [Comment(**c) for c in found]


async def resolve_comment(id: UUID, comment_id: UUID, user: str) -> Comment:
    found = await _backend().resolve_review_comment_in_db(id, comment_id, user)
    if found is None:
        raise PanglossNoSuchCommentError(f"No comment {comment_id} on {id}")
    return Comment(**found)


async def get_detail(id: UUID, include_resolved: bool = False) -> ReviewDetail:
    """The state, and the comments"""
    state = await get_state(id)
    comments = await list_comments(id, include_resolved)
    return ReviewDetail(**state.model_dump(), comments=comments)


async def queue(
    statuses: list[ReviewStatus] | None = None,
    type: str | None = None,
    page: int = 1,
    page_size: int = 25,
) -> Queue:
    """The documents to check (by default those `unchecked`), the oldest change first"""
    wanted = statuses or [ReviewStatus.UNCHECKED]
    found = await _backend().review_queue_in_db(
        [s.value for s in wanted], type, page, page_size
    )
    count = found["count"]
    last = -(-count // page_size)
    return Queue(
        results=[QueueItem(**item) for item in found["results"]],
        count=count,
        page=page,
        page_size=page_size,
        next_page=page + 1 if page < last else None,
        previous_page=page - 1 if page > 1 else None,
    )
