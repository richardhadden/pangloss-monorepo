"""`/api/review`: what to check, the state of a document, and changing it.

    GET  /api/review/queue?status=unchecked&type=Letter&page=1   the documents to check
    GET  /api/review/types                                         the classes that are reviewed
    GET  /api/review/{id}                                          its state and comments (?resolved=true: all)
    POST /api/review/{id}/status        {"status": "published", "comment": "..."}
    POST /api/review/{id}/comments      {"text": "...", "targetId": "<id of a part>"}
    POST /api/review/{id}/comments/{comment_id}/resolve

The state of a document is also in the `meta` of its read (`published`, `reviewStatus`), without the comments.
Everything needs a user who is logged in. A document is not given review by its create or update: the
server makes it `unchecked` when it is created, and an update leaves the state as it is.
"""

from typing import Annotated, Any
from urllib.parse import parse_qsl, urlencode
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, Query, Request, status
from fastapi.responses import JSONResponse
from pangloss_api import CurrentUser, get_current_user
from pangloss_models import hooks
from pangloss_users import User
from pangloss_users import service as user_service
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from starlette.types import ASGIApp, Receive, Scope, Send

from pangloss_review import identify, reconcile, service
from pangloss_review.exceptions import (
    PanglossAssignmentError,
    PanglossCommentTargetError,
    PanglossNoSuchCommentError,
    PanglossNoSuchTaskError,
    PanglossNotReviewableError,
    PanglossReconcileError,
    PanglossReviewError,
    PanglossSelfReviewError,
)
from pangloss_review.status import (
    Comment,
    Confirmed,
    Mention,
    Mentions,
    Queue,
    Reconciled,
    Ref,
    ReviewDetail,
    ReviewStatus,
    SimilarMention,
    SimilarSuggestion,
    Suggestion,
    Suggestions,
    TaskCounts,
)

router = APIRouter(
    prefix="/api/review", tags=["review"], dependencies=[Depends(get_current_user)]
)

STATUS_OF_ERROR: dict[type[PanglossReviewError], int] = {
    PanglossNotReviewableError: status.HTTP_404_NOT_FOUND,
    PanglossNoSuchCommentError: status.HTTP_404_NOT_FOUND,
    PanglossSelfReviewError: status.HTTP_403_FORBIDDEN,
    PanglossAssignmentError: status.HTTP_403_FORBIDDEN,
    PanglossNoSuchTaskError: status.HTTP_404_NOT_FOUND,
    PanglossReconcileError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    PanglossCommentTargetError: status.HTTP_422_UNPROCESSABLE_CONTENT,
}


async def review_error_handler(request: Request, error: Exception) -> JSONResponse:
    code = STATUS_OF_ERROR.get(type(error), status.HTTP_400_BAD_REQUEST)
    return JSONResponse(
        status_code=code, content={"detail": str(error), "error": type(error).__name__}
    )


# (in either case, as every parameter is: this may be reached before the API has put the names in snake_case)
STATUS_PARAMETER = ("review_status", "reviewStatus")
ASSIGNEE_PARAMETER = ("review_assigned_to", "reviewAssignedTo")


class RequestedStatus:
    """`?review_status=published` (or `unchecked`, `errors_found`) on a create (`POST /api/Letter`) or an update
    (`PUT /api/Letter/{id}`): the document is written with that status, `published` at once, for data that
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
        query = parse_qsl(scope["query_string"].decode(), keep_blank_values=True)
        asked = [value for name, value in query if name in STATUS_PARAMETER]
        assignee = [value for name, value in query if name in ASSIGNEE_PARAMETER]
        if not asked and not assignee:
            return await self.app(scope, receive, send)
        # (the parameters are read here: the route does not have them, and would refuse them)
        ours = (*STATUS_PARAMETER, *ASSIGNEE_PARAMETER)
        rest = urlencode([pair for pair in query if pair[0] not in ours])
        scope = {**scope, "query_string": rest.encode()}

        def refused(detail: str) -> JSONResponse:
            return JSONResponse(
                {"detail": detail}, status_code=status.HTTP_422_UNPROCESSABLE_CONTENT
            )

        status_asked = None
        if asked:
            try:
                status_asked = ReviewStatus(asked[-1]).value
            except ValueError:
                allowed = ", ".join(s.value for s in ReviewStatus)
                return await refused(f"review_status must be one of {allowed}")(
                    scope, receive, send
                )
        if assignee:
            if scope["method"] != "POST":
                return await refused(
                    "review_assigned_to is of a new document: an existing one is given to someone at "
                    "/api/review/{id}/assign"
                )(scope, receive, send)
            found = await user_service.get_user(assignee[-1])
            if found is None or found.kind != "user" or found.disabled:
                return await refused(f"There is no user '{assignee[-1]}' to review it")(
                    scope, receive, send
                )
        with (
            hooks.requesting_review_status(status_asked),
            hooks.requesting_review_assignee(assignee[-1] if assignee else None),
        ):
            await self.app(scope, receive, send)


def configure_app(app: FastAPI, settings) -> None:
    app.add_exception_handler(PanglossReviewError, review_error_handler)
    app.add_middleware(RequestedStatus)


class _Body(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class StatusBody(_Body):
    status: ReviewStatus
    comment: str | None = None


class AssignBody(_Body):
    # (null: to no one)
    username: str | None = None


class CommentBody(_Body):
    text: str
    target_id: UUID | None = None


def assignee_asked(assigned_to: str | None, user: User) -> str | None:
    """Whose tasks a list is of, from `?assigned_to=`: `me`, `none` (no one's: an empty name), or a username, which
    only an admin may ask of someone else"""
    if assigned_to is None:
        return None
    if assigned_to == "me":
        return user.username
    if assigned_to == "none":
        return ""
    if assigned_to != user.username and not user.admin:
        raise PanglossAssignmentError("Only an admin can see the tasks of someone else")
    return assigned_to


@router.get("/queue", operation_id="review_queue")
async def get_queue(
    statuses: Annotated[
        list[ReviewStatus] | None,
        Query(alias="status", description="Default: unchecked; repeat for more"),
    ] = None,
    type: Annotated[str | None, Query(description="Only this class")] = None,
    assigned_to: Annotated[
        str | None,
        Query(
            description="Only those given to this user to review: `me`, a username (another's: for an "
            "admin), or `none` for those given to no one"
        ),
    ] = None,
    q: Annotated[
        str | None,
        Query(
            description="Only those whose label has each of these words", max_length=200
        ),
    ] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    *,
    user: CurrentUser,
) -> Queue:
    return await service.queue(
        statuses, type, page, page_size, assignee_asked(assigned_to, user), q
    )


@router.get("/types", operation_id="review_types")
async def get_types() -> list[str]:
    """The names of the classes whose documents are reviewed (for a filter of the queue)"""
    return service.reviewable_types()


# --- unreconciled mentions --------------------------------------------------------------------------------------------


class ReconcileBody(_Body):
    # the entity that takes the place of the mention
    entity: Ref
    # other mentions (from `similar`) to reconcile with the same entity, in the background
    also: list[UUID] = []
    # it is reconciled in a form of its document, saved later: the document is not written here
    in_form: bool = False
    # identifications a toolchain suggested that name its URI, to confirm as the entity (from `.../suggestions`)
    suggestions: list[UUID] = []


@router.get("/unreconciled", operation_id="review_unreconciled")
async def get_unreconciled(
    type: Annotated[str | None, Query(description="Only of this entity class")] = None,
    q: Annotated[str | None, Query(description="With this in the label")] = None,
    assigned_to: Annotated[
        str | None, Query(description="As for the queue: `me`, a username, `none`")
    ] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    *,
    user: CurrentUser,
) -> Mentions:
    """The unreconciled mentions: each is in a document, and is a task until an entity takes its place"""
    return await reconcile.list_mentions(
        type, q, assignee_asked(assigned_to, user), page, page_size
    )


@router.get("/unreconciled/types", operation_id="review_unreconciled_types")
async def get_unreconciled_types() -> list[str]:
    """The names of the entity classes that may be left unreconciled (for a filter)"""
    return reconcile.unreconciled_types()


@router.get("/unreconciled/{id}", operation_id="review_unreconciled_one")
async def get_mention(id: UUID) -> Mention:
    return await reconcile.get_mention(id)


@router.get("/unreconciled/{id}/similar", operation_id="review_unreconciled_similar")
async def get_similar_mentions(id: UUID) -> list[SimilarMention]:
    """Other mentions that may be of the same thing, to reconcile in one go: the same entity class, the same label
    or one much like it"""
    return await reconcile.similar(id)


@router.post("/unreconciled/{id}/reconcile", operation_id="review_reconcile")
async def reconcile_mention(id: UUID, body: ReconcileBody) -> Reconciled:
    """Put an entity in the place of the mention (an update of its document, by the user), and give the entity the
    mention's URIs. The others named are done in the background. With `inForm`, its own document is left to the
    form that holds the change"""
    return await reconcile.reconcile(
        id, body.entity.type, body.entity.id, body.also, body.in_form, body.suggestions
    )


@router.get(
    "/unreconciled/{id}/suggestions", operation_id="review_unreconciled_suggestions"
)
async def get_suggestions_of_mention(id: UUID) -> list[SimilarSuggestion]:
    """The identifications a toolchain suggested that name a URI of the mention: of the same person, to be confirmed
    as the entity it is reconciled with"""
    return await reconcile.suggestions_of_mention(id)


# --- identifications that a toolchain suggested ------------------------------------------------------------------------


class ConfirmBody(_Body):
    # other suggestions (from `similar`) to give the same identification, in the background
    also: list[UUID] = []


@router.get("/identifications", operation_id="review_identifications")
async def get_identifications(
    assigned_to: Annotated[
        str | None, Query(description="As for the queue: `me`, a username, `none`")
    ] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    *,
    user: CurrentUser,
) -> Suggestions:
    """The identifications a toolchain suggested: each is a task until a person confirms it"""
    return await identify.list_suggestions(
        assignee_asked(assigned_to, user), page, page_size
    )


@router.get("/identifications/{id}", operation_id="review_identification")
async def get_identification(id: UUID) -> Suggestion:
    return await identify.get_suggestion(id)


@router.get(
    "/identifications/{id}/similar", operation_id="review_identification_similar"
)
async def get_similar_identifications(id: UUID) -> list[SimilarSuggestion]:
    """Other suggestions of the same candidates, each about as likely: to give the same identification in one go.
    (Also of an identification that has been confirmed: by the candidates it has now.)"""
    return await identify.similar(id)


@router.post("/identifications/{id}/confirm", operation_id="review_confirm")
async def confirm_identification(
    id: UUID, body: ConfirmBody, user: CurrentUser
) -> Confirmed:
    """Confirm the suggestion as it is: it becomes an identification by the user (an update of its document). The
    others named are given the same, in the background"""
    return await identify.confirm(id, user.username, body.also)


class GiveBody(_Body):
    # other suggestions (from `similar`) to give this identification
    also: list[UUID] = []
    # what the identification is of, as the form has it
    target: list[dict[str, Any]]
    # unreconciled mentions that name its URI (from `.../mentions`), to reconcile with `entity`: the one it is of
    mentions: list[UUID] = []
    entity: Ref | None = None


class Given(_Body):
    queued: int


@router.post("/identifications/{id}/give", operation_id="review_give_identification")
async def give_identification(id: UUID, body: GiveBody, user: CurrentUser) -> Given:
    """For a suggestion that is being confirmed in a form (it is confirmed by saving its document as an
    identification): give the others named the same identification now, in the background. Those in the same
    document are left to the form"""
    return Given(
        queued=await identify.give_to_others(
            id,
            user.username,
            body.also,
            body.target,
            body.mentions,
            {"type": body.entity.type, "id": str(body.entity.id)}
            if body.entity
            else None,
        )
    )


@router.get(
    "/identifications/{id}/mentions", operation_id="review_identification_mentions"
)
async def get_mentions_of_identification(id: UUID) -> list[Mention]:
    """The unreconciled mentions that name a URI of the suggestion: of the same person, to be reconciled with the
    one it is confirmed as"""
    return await identify.mentions_of_suggestion(id)


@router.get("/tasks/summary", operation_id="review_task_counts")
async def get_task_counts(
    assigned_to: Annotated[
        str | None, Query(description="As for the queue: `me`, a username, `none`")
    ] = None,
    *,
    user: CurrentUser,
) -> TaskCounts:
    """How many tasks there are of each kind (for the tabs of the Review page)"""
    return await reconcile.task_counts(assignee_asked(assigned_to, user))


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


@router.post("/{id}/assign", operation_id="review_assign")
async def assign(id: UUID, body: AssignBody, user: CurrentUser) -> ReviewDetail:
    """Give the document to a user to review, or (`null`) to no one. Anyone may take it for themselves; an admin
    gives it to anyone"""
    await service.assign(id, body.username, user.username, user.admin)
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
