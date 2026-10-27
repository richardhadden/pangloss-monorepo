"""The review state of a document, and its comments"""

import datetime
import enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class _Camel(BaseModel):
    """(Like the models of the API: camelCase in JSON, either way in Python)"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ReviewStatus(enum.StrEnum):
    UNCHECKED = "unchecked"
    ERRORS_FOUND = "errors_found"
    CHECKED = "checked"

    @property
    def published(self) -> bool:
        """A document is published when it has been checked and no errors were found"""
        return self is ReviewStatus.CHECKED


class ReviewState(_Camel):
    id: UUID
    type: str
    label: str | None
    status: ReviewStatus
    published: bool
    created_by: str | None
    last_edited_by: str | None
    reviewed_by: str | None = None
    reviewed_at: datetime.datetime | None = None
    open_comments: int = 0


class Comment(_Camel):
    id: UUID
    username: str
    at: datetime.datetime
    text: str
    # the id of the part of the document it is about, and what the part was called when it was made
    target_id: UUID | None = None
    target_label: str | None = None
    resolved: bool = False
    resolved_by: str | None = None
    resolved_at: datetime.datetime | None = None


class ReviewDetail(ReviewState):
    """The state of a document, and its comments (the open ones, unless more were asked for)"""

    comments: list[Comment] = []


class QueueItem(_Camel):
    id: UUID
    type: str
    label: str | None
    status: ReviewStatus
    created_by: str | None
    changed_when: datetime.datetime | None
    reviewed_by: str | None = None
    open_comments: int = 0


class Queue(_Camel):
    results: list[QueueItem]
    count: int
    page: int
    page_size: int
    next_page: int | None
    previous_page: int | None
