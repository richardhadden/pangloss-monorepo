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
        a 404 too, its reason logged). Login required: reconciling is the work of people logged in. The one thing it
        writes, after its answer is made and only when that answer's status is `"ok"`: what it offered this user for
        the stand-in (`decisions.keep_shown`, one record for each stand-in and user, replaced by the next request;
        not with `RECONCILE_KEEP_DECISIONS = False`; a failure to write it is logged and the answer still given)

A plan with more unknowns than `RECONCILE_MOST_UNKNOWNS` is a 422 that says how many it has and the most.

    POST /api/reconcile/suggest   body {"classes": [...], "again": false}, both optional
        the documents stored that hold a stand-in left for the worker (`suggesting.mark_stored`, step 10.5e): answers
        `{marked, already, standIns, forgotten}`; a class that can hold no stand-in is a 422 naming those that can.
        Admins only (403; 401 not logged in)
    GET /api/reconcile/suggest
        the state of the worker (`suggesting.status`): `{pending, claimed, oldest, waitingForVectors, rebuilding,
        profile, lease, tried, suggested}` (`profile`: `ok`, or `pending`, `rebuild_due`, while nothing is claimed).
        Admins only

And the worker that suggests (`suggesting.py`), as a background task (`RECONCILE_WORKER_IN_SERVER = False` to run it
in a process of its own, `pangloss reconcile worker`).

Both answer `{status, profile, unknowns: [{id, type, label, candidates: [{...reference view, score, scores,
shared}]}]}`, `shared` the first `RECONCILE_REASONS` entities of the payload the candidate is named with in stored
documents (`reasons.py`), the unknowns in the order of the plan, the candidates best first as the reader may see them
(the reference views as the similar route gives them), none scoring under `RECONCILE_LEAST_SCORE`. `status`: `"ok"`, `"pending"` (the profile has not been built: every list is empty) or
`"rebuild_due"` (the candidates are of the vectors in use).

The stored route's answer has `model` too (step 11.6, `none_of_these`): null when no fit is in use, otherwise `{id, at,
decisions, used}` of the fit in use (`fits.in_use()`, one read), `used` false when it is not of today
(`decisions.of_today`) or has no "none of these" model (`fits.usable`); and, when it is used, on each unknown whose
candidates as answered are not empty and give every feature the model weighs, `new` (the likelihood, from 0 to 1, that
the one meant is none of those offered) and `probablyNew` (`new` above `RECONCILE_NEW_ABOVE`), both of
`learning.probably_new` of the candidates answered, in the answer's order (what a suggestion is not made for, too:
`suggest.decide_for`); otherwise neither key. The ranking is the hand-set score's,
whatever fit is in use. The payload route's answer has neither (its features differ a little from the stored route's:
the challenger's fault 17)."""

import datetime
import logging
from collections.abc import Mapping
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, FastAPI, HTTPException, Query, status
from fastapi.exceptions import RequestValidationError
from pangloss_api import BackgroundTask, CurrentAdmin, CurrentUser
from pydantic import BaseModel, ValidationError

from pangloss_reconcile.candidates import Found, TooManyUnknowns

logger = logging.getLogger("pangloss.reconcile")

router = APIRouter(prefix="/api/reconcile", tags=["reconcile"])

# The most candidates a request may ask for, for each unknown
MAX_LIMIT = 100

Limit = Annotated[
    int,
    Query(ge=1, le=MAX_LIMIT, description="How many candidates, for each unknown"),
]


def configure_app(app: FastAPI, settings: Any) -> None:
    from pangloss_reconcile.settings import worker_in_server

    if worker_in_server(settings):
        from pangloss_reconcile.suggesting import worker

        app.state.background_tasks.append(BackgroundTask("reconcile", worker.run))


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


async def answer(found: list[Found], see_unpublished: bool) -> dict[str, Any]:
    """The answer of both routes: each unknown with the reference views of its candidates, as the reader may see
    them, each with the first `RECONCILE_REASONS` of what it shares with the plan (`Candidate.shared`, counted by
    `candidates_of`: nothing more is asked here), and the state of the profile"""
    return (await answered(found, see_unpublished))[0]


async def answered(
    found: list[Found], see_unpublished: bool
) -> tuple[dict[str, Any], Any]:
    """`answer`, and the states of the vectors it was made with (`pangloss_vectors.store.states()`, read once)"""
    from pangloss_vectors import store
    from pangloss_vectors.status import status_of
    from pangloss_vectors.views import reference_views

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
    most = reasons()
    why = {c.id: c.shared[:most] for each in found for c in each.candidates}
    views = await reference_views(
        sorted({*why, *(id for pairs in why.values() for id, _ in pairs)}),
        see_unpublished,
    )
    given = {
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
    return given, states


def _when(value: Any) -> Any:
    """A fit's `at` as the answer gives it: ISO 8601, UTC"""
    from pangloss_reconcile.decisions import _native, _utc

    found = _utc(_native(value))
    return found.isoformat() if isinstance(found, datetime.datetime) else found


def none_of_these(
    given: Mapping[str, Any],
    fit: Mapping[str, Any] | None,
    now: Mapping[str, Any],
    above: float,
) -> dict[str, Any]:
    """The stored route's answer `given` with what the fit in use (`fit`, `fits.in_use()`, or None) says of it: `model`
    (null, or `{id, at, decisions, used}`), and, when the fit is used (`fits.usable` of `now`, `decisions.today` of
    the states the answer was made with), on each unknown with a figure (`learning.probably_new` of its candidates as
    answered, in the answer's order) `new` and `probablyNew` (`new` > `above`). No database in it; nothing else of
    `given` changes"""
    from pangloss_learn import Model

    from pangloss_reconcile.fits import usable
    from pangloss_reconcile.learning import probably_new

    if fit is None:
        return {**given, "model": None}
    used = usable(fit, now)
    unknowns = list(given["unknowns"])
    if used:
        model = Model.from_json(fit["none"])
        unknowns = []
        for unknown in given["unknowns"]:
            said = probably_new(
                model,
                [(c["score"], c["scores"]) for c in unknown["candidates"]],
                above,
            )
            unknowns.append(
                unknown
                if said is None
                else {**unknown, "new": said[0], "probablyNew": said[1]}
            )
    return {
        **given,
        "model": {
            "id": fit["id"],
            "at": _when(fit["at"]),
            "decisions": fit["decisions"],
            "used": used,
        },
        "unknowns": unknowns,
    }


class SuggestStored(BaseModel):
    """What `POST /api/reconcile/suggest` marks: the heads of these classes and those below them (all that can hold a
    stand-in, when not given), and whether what was tried is forgotten first"""

    classes: list[str] | None = None
    again: bool = False


@router.post("/suggest", operation_id="reconcile_suggest")
async def suggest_stored(
    admin: CurrentAdmin,
    body: Annotated[SuggestStored | None, Body()] = None,
) -> dict[str, int]:
    """Leave for the worker the documents stored that hold a stand-in and have no mark of its kind
    (`suggesting.mark_stored`): how many were marked, how many were already, the stand-ins they hold, and the stand-ins
    tried that were forgotten (`again`). A class that can hold no stand-in is a 422 that names those that can"""
    from pangloss_reconcile.suggesting import NotSuggestible, mark_stored

    asked = body or SuggestStored()
    try:
        done = await mark_stored(asked.classes, again=asked.again)
    except NotSuggestible as error:
        raise unprocessable(str(error)) from None
    return done.as_json()


@router.get("/suggest", operation_id="reconcile_suggest_status")
async def suggest_status(admin: CurrentAdmin) -> dict[str, Any]:
    """What the worker that suggests has to do and has done (`suggesting.status`): the heads waiting and claimed, the
    oldest mark, how many wait for the vectors, whether a rebuild of them holds its lease, who holds the worker's lease,
    the stand-ins tried and left, and the suggestions not yet confirmed"""
    from pangloss_reconcile.suggesting import status, status_json

    return status_json(await status())


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
    return await answer(found, see_unpublished)


@router.get("/candidates/{id}", operation_id="reconcile_candidates_of_stored")
async def candidates_of_stored(
    id: UUID, user: CurrentUser, limit: Limit = 10
) -> dict[str, Any]:
    """The candidates of a stand-in already stored, as the reader may see them, with what the fit in use says of them
    (`none_of_these`); what was offered is kept for the user (`decisions.keep_shown`) when the answer is `"ok"`"""
    from pangloss_core import backend
    from pangloss_models import PanglossReferenceError

    from pangloss_reconcile import fits
    from pangloss_reconcile.candidates import candidates_of
    from pangloss_reconcile.decisions import keep_shown, today
    from pangloss_reconcile.settings import new_above
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
        # (the reasons, asked in it, resolve the plan's references again, and may meet one that is gone when no
        # part did)
        found = await candidates_of(
            plan, see_unpublished=see_unpublished, limit=limit, only=[str(id)]
        )
        if not found:
            raise missing
        given, states = await answered(found, see_unpublished)
    except (Unplannable, PanglossReferenceError) as error:
        # (a stored document is not refused: what would refuse it is said here, for whoever keeps the server)
        logger.warning("The candidates of %s cannot be found: %s", id, error)
        raise unplannable from None
    if given["status"] == "ok":
        await keep_shown(found[0], given, states, user.username)
    # (after what was offered is kept: that record holds no figure of it)
    try:
        return none_of_these(given, await fits.in_use(), today(states), new_above())
    except Exception:
        # (the answer is made: what a fit would say of it never fails it)
        logger.exception("What the fit in use says of %s could not be worked out", id)
        return {**given, "model": None}
