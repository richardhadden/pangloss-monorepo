"""What the app adds to the server (implementation_docs/reconcile.md, "The routes"):

    POST /api/reconcile/candidates?limit=10
        the body a `Create` payload, its `type` the class (one that has a create route): validated as that create
        route validates it (the same 422), checked as its create would be without writing (`checked_create`, with
        the creators and the user the create route gives it: `?created_by=`, `?toolchain=` for an admin, and review's
        `?review_status=` read by its middleware), refused as the create route refuses (401, 403, and each
        `PanglossWriteError` answered by the API's own handlers), then the candidates of its unknowns. Login required
    GET /api/reconcile/candidates/{id}?limit=10
        the candidates of a stand-in already stored, by its id: a node below a head, its head read as the reader
        (404 if the node is not there, is no unknown, or the reader may not see its head, as `GET /api/NAME/{head}`
        would refuse it), planned as an update of it would be (`stored.py`; a document that cannot be planned so is
        a 404 too, its reason logged), nothing written. Login required: reconciling is the work of people logged in

A plan with more unknowns than `RECONCILE_MOST_UNKNOWNS` is a 422 that says how many it has and the most.

Both answer `{status, profile, unknowns: [{id, type, label, candidates: [{...reference view, score, scores,
shared}]}]}`, `shared` the entities of the payload the candidate is named with in stored documents (`reasons.py`), the
unknowns in the order of the plan, the candidates best first as the reader may see them (the reference views as the
similar route gives them). `status`: `"ok"`, `"pending"` (the profile has not been built: every list is empty) or
`"rebuild_due"` (the candidates are of the vectors in use)."""

import datetime
import logging
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from fastapi.exceptions import RequestValidationError
from pangloss_api import CurrentUser, get_current_user
from pydantic import ValidationError

from pangloss_reconcile.candidates import Found, TooManyUnknowns

logger = logging.getLogger("pangloss.reconcile")

router = APIRouter(prefix="/api/reconcile", tags=["reconcile"])

LOGGED_IN = [Depends(get_current_user)]

# The most candidates a request may ask for, for each unknown
MAX_LIMIT = 100

Limit = Annotated[
    int,
    Query(ge=1, le=MAX_LIMIT, description="How many candidates, for each unknown"),
]


def unprocessable(message: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=message)


def creatable_model(type_name: Any) -> Any:
    """The model of a class that has a create route (`POST /api/NAME`), by the `type` of a body; 422 otherwise"""
    from pangloss_api.routes.models import routable_models
    from pangloss_models import hooks

    if not isinstance(type_name, str):
        raise unprocessable(
            "The body is a Create payload: its `type` names the class it would create"
        )
    for model in routable_models():
        if model.__name__ != type_name:
            continue
        meta: Any = model._meta  # type: ignore[attr-defined]
        if (
            not getattr(meta, "abstract", False)
            and getattr(meta, "create_directly", True)
            and hooks.written_by_people(model)
        ):
            return model
        break
    raise unprocessable(
        f"{type_name!r} is no class that can be created (POST /api/{type_name}): the body is a Create payload of one"
    )


async def answer(
    found: list[Found], see_unpublished: bool, plan: Any
) -> dict[str, Any]:
    """The answer of both routes: each unknown with the reference views of its candidates, as the reader may see
    them, each with what it shares with the plan (`reasons.py`), and the state of the profile"""
    from pangloss_vectors import store
    from pangloss_vectors.status import status_of
    from pangloss_vectors.views import reference_views

    from pangloss_reconcile.reasons import shared
    from pangloss_reconcile.settings import profile, reasons

    name = profile()
    states = await store.states()
    statuses = {each.status for each in found}
    if name not in states.profiles or "pending" in statuses:
        answer_status = "pending"
    else:
        state = status_of(states).profile(name)
        due = "rebuild_due" in statuses or (state is not None and state.rebuild_due)
        answer_status = "rebuild_due" if due else "ok"
    candidates = sorted({c.id for each in found for c in each.candidates})
    why = await shared(plan, candidates, see_unpublished, reasons())
    views = await reference_views(
        sorted({*candidates, *(id for pairs in why.values() for id, _ in pairs)}),
        see_unpublished,
    )
    return {
        "status": answer_status,
        "profile": name,
        "unknowns": [
            {
                "id": each.unknown.id,
                "type": each.unknown.type,
                "label": each.unknown.label,
                "candidates": [
                    {
                        **views[c.id],
                        "score": c.score,
                        "scores": c.scores,
                        "shared": [
                            {**views[id], "documents": documents}
                            for id, documents in why.get(c.id, [])
                            if id in views
                        ],
                    }
                    for c in each.candidates
                    if c.id in views
                ],
            }
            for each in found
        ],
    }


@router.post("/candidates", operation_id="reconcile_candidates")
async def candidates_of_payload(
    user: CurrentUser,
    body: Annotated[dict[str, Any], Body(description="A Create payload")],
    limit: Limit = 10,
    created_by: Annotated[
        list[str] | None, Query(description="As for a create")
    ] = None,
    toolchain: Annotated[str | None, Query(description="As for a create")] = None,
    toolchain_version: Annotated[str | None, Query()] = None,
    toolchain_date: Annotated[datetime.date | None, Query()] = None,
) -> dict[str, Any]:
    """The candidates of each unknown of a payload, checked as its create would be, and nothing written"""
    from pangloss_api.routes.models import named_creators, refuse_if_protected
    from pangloss_core import backend, storage_of
    from pangloss_models import protection_of
    from pangloss_models.creators import writing_as
    from pangloss_models.protection import changed_fields

    from pangloss_reconcile.candidates import candidates_of

    model = creatable_model(body.get("type"))
    try:
        instance = model.Create.model_validate(body, from_attributes=True)
    except ValidationError as error:
        # (as the create route's body is validated: FastAPI's errors, at the body)
        raise RequestValidationError(
            [
                {**e, "loc": ("body", *e["loc"])}
                for e in error.errors(include_url=False)
            ],
            body=body,
        ) from None
    if protection_of(model).read_only:
        refuse_if_protected(changed_fields(model, instance, None))
    creators = named_creators(
        user, created_by, toolchain, toolchain_version, toolchain_date
    )
    with writing_as(creators):
        _, plan, _ = await storage_of().operations.checked_create(instance)
    see_unpublished = backend.current().unpublished_visible()
    try:
        found = await candidates_of(plan, see_unpublished=see_unpublished, limit=limit)
    except TooManyUnknowns as error:
        raise unprocessable(str(error)) from None
    return await answer(found, see_unpublished, plan)


@router.get(
    "/candidates/{id}",
    operation_id="reconcile_candidates_of_stored",
    dependencies=LOGGED_IN,
)
async def candidates_of_stored(id: UUID, limit: Limit = 10) -> dict[str, Any]:
    """The candidates of a stand-in already stored, as the reader may see them"""
    from pangloss_core import backend
    from pangloss_models import PanglossReferenceError

    from pangloss_reconcile.candidates import candidates_of
    from pangloss_reconcile.stored import Unplannable, stored_plan

    missing = HTTPException(
        status.HTTP_404_NOT_FOUND,
        detail=f"There is no stand-in with id {id} in a document that can be read",
    )
    unplannable = HTTPException(
        status.HTTP_404_NOT_FOUND,
        detail=f"The document of the stand-in {id} cannot be planned as it is stored",
    )
    see_unpublished = backend.current().unpublished_visible()
    try:
        plan = await stored_plan(str(id))
        if plan is None:
            raise missing
        found = await candidates_of(
            plan, see_unpublished=see_unpublished, limit=limit, only=[str(id)]
        )
        if not found:
            raise missing
        # (the reasons resolve the plan's references again, and may meet one that is gone when no part did)
        return await answer(found, see_unpublished, plan)
    except (Unplannable, PanglossReferenceError) as error:
        # (a stored document is not refused: what would refuse it is said here, for whoever keeps the server)
        logger.warning("The candidates of %s cannot be found: %s", id, error)
        raise unplannable from None
