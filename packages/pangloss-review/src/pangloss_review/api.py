"""`/api/review`: what to check, the state of a document, and changing it.

    GET  /api/review/queue?status=unchecked&type=Letter&page=1   the documents to check
    GET  /api/review/{id}                                          its state and comments (?resolved=true: all)
    POST /api/review/{id}/status        {"status": "checked", "comment": "..."}
    POST /api/review/{id}/comments      {"text": "...", "targetId": "<id of a part>"}
    POST /api/review/{id}/comments/{comment_id}/resolve

The state of a document is also in the `meta` of its read (`published`, `reviewStatus`), without the comments.
Everything needs a user who is logged in. A document is not given review by its create or update: the
server makes it `unchecked` when it is created, and an update leaves the state as it is.
"""

from typing import Annotated
from urllib.parse import parse_qs
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, Query, Request, status
from fastapi.responses import JSONResponse
from pangloss_api.dependencies import CurrentUser, get_current_user
from pangloss_models import hooks
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from starlette.types import ASGIApp, Receive, Scope, Send

from pangloss_review import service
from pangloss_review.exceptions import (
    PanglossCommentTargetError,
    PanglossNoSuchCommentError,
    PanglossNotReviewableError,
    PanglossReviewError,
    PanglossSelfReviewError,
)
from pangloss_review.status import Comment, Queue, ReviewDetail, ReviewStatus

router = APIRouter(
    prefix="/api/review", tags=["review"], dependencies=[Depends(get_current_user)]
)

STATUS_OF_ERROR: dict[type[PanglossReviewError], int] = {
    PanglossNotReviewableError: status.HTTP_404_NOT_FOUND,
    PanglossNoSuchCommentError: status.HTTP_404_NOT_FOUND,
    PanglossSelfReviewError: status.HTTP_403_FORBIDDEN,
    PanglossCommentTargetError: status.HTTP_422_UNPROCESSABLE_CONTENT,
}


async def review_error_handler(request: Request, error: Exception) -> JSONResponse:
    code = STATUS_OF_ERROR.get(type(error), status.HTTP_400_BAD_REQUEST)
    return JSONResponse(
        status_code=code, content={"detail": str(error), "error": type(error).__name__}
    )


class RequestedStatus:
    """`?review_status=checked` (or `unchecked`, `errors_found`) on a create (`POST /api/Letter`) or an update
    (`PUT /api/Letter/{id}`): the document is written with that status, `checked` published at once, for data that
    is known to be right when it is loaded. It applies to documents of reviewed classes only (for any other the
    parameter is ignored). Without it, a new document is `unchecked` and an update leaves the state alone."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] not in ("POST", "PUT")
            or not scope["path"].startswith("/api/")
            or scope["path"].startswith("/api/review")
        ):
            return await self.app(scope, receive, send)
        asked = parse_qs(scope["query_string"].decode()).get("review_status")
        if not asked:
            return await self.app(scope, receive, send)
        try:
            status_asked = ReviewStatus(asked[-1])
        except ValueError:
            allowed = ", ".join(s.value for s in ReviewStatus)
            return await JSONResponse(
                {"detail": f"review_status must be one of {allowed}"},
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            )(scope, receive, send)
        with hooks.requesting_review_status(status_asked.value):
            await self.app(scope, receive, send)


def configure_app(app: FastAPI, settings) -> None:
    app.add_exception_handler(PanglossReviewError, review_error_handler)
    app.add_middleware(RequestedStatus)


class _Body(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class StatusBody(_Body):
    status: ReviewStatus
    comment: str | None = None


class CommentBody(_Body):
    text: str
    target_id: UUID | None = None


@router.get("/queue", operation_id="review_queue")
async def get_queue(
    statuses: Annotated[
        list[ReviewStatus] | None,
        Query(alias="status", description="Default: unchecked; repeat for more"),
    ] = None,
    type: Annotated[str | None, Query(description="Only this class")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> Queue:
    return await service.queue(statuses, type, page, page_size)


@router.get("/{id}", operation_id="review_detail")
async def get_review(
    id: UUID,
    resolved: Annotated[bool, Query(description="Include resolved comments")] = False,
) -> ReviewDetail:
    return await service.get_detail(id, resolved)


@router.post("/{id}/status", operation_id="review_set_status")
async def set_status(id: UUID, body: StatusBody, user: CurrentUser) -> ReviewDetail:
    await service.set_status(id, body.status, user.username, body.comment)
    return await service.get_detail(id)


@router.post(
    "/{id}/comments",
    status_code=status.HTTP_201_CREATED,
    operation_id="review_add_comment",
)
async def add_comment(id: UUID, body: CommentBody, user: CurrentUser) -> Comment:
    return await service.add_comment(id, user.username, body.text, body.target_id)


@router.post("/{id}/comments/{comment_id}/resolve", operation_id="review_resolve")
async def resolve_comment(id: UUID, comment_id: UUID, user: CurrentUser) -> Comment:
    return await service.resolve_comment(id, comment_id, user.username)
