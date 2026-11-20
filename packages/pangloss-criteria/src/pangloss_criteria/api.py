"""What the app adds to the server: the routes of descriptions, and the worker, as a background task
(`CRITERIA_WORKER_IN_SERVER = False` to run it in a process of its own, `pangloss criteria worker`).

    POST /api/criteria/preview            {"criteria": {"type": "Person", "where": {...}}, "named": [id, ...]}
                                          what the criteria would find if saved now: {count, candidates (the first
                                          five by label), tooBroad} (login)
    GET  /api/criteria/{id}/candidates?page=1&page_size=25
                                          the linked candidates of a saved description (the id of its
                                          `MatchesCriteria`), by label, as the reader sees them: {count, tooBroad,
                                          pending, evaluatedWhen, broken, page, pageSize, candidates, criteria,
                                          places}: `criteria` ({type, where}) are what it is evaluated by, its own
                                          or, for a place with none (`sameOne`), those of the place of its mark
                                          that holds them; `places`, how many places of its document share its mark
    POST /api/criteria/{id}/resolve       {"entity": {"type": "Person", "id": ...}, "version": 3}
                                          "This is…": the entity takes the description's place (every place of its
                                          mark, `sameOne`), and its document is
                                          written again as an update (from `version`, the one the choice was made
                                          on, if given: 412 if it has changed since): {head, entity, version} (login).
                                          404 for no description the reader sees; 422 for what the field does not
                                          take there
    GET  /api/criteria/settled/{head_id}  whether the descriptions of a head have their result since its last save:
                                          {settled} (login; what `pangloss_criteria.settled` asks through the SDK)

Criteria a description could not store (a field the class lacks, a path through another description, a class that
may not be described) are a 422 with the path, and `error: "PanglossSearchError"`.
(implementation_docs/matches-criteria.md, "The API")
"""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pangloss_api import BackgroundTask, get_current_user
from pangloss_models import PanglossSearchError
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from pangloss_criteria import reading, resolving
from pangloss_criteria.access import Reference, Resolved
from pangloss_criteria.worker import is_pending, worker

router = APIRouter(prefix="/api/criteria", tags=["criteria"])

LOGGED_IN = [Depends(get_current_user)]


def configure_app(app: FastAPI, settings: Any) -> None:
    if getattr(settings, "CRITERIA_WORKER_IN_SERVER", True):
        app.state.background_tasks.append(BackgroundTask("criteria", worker.run))


class PreviewBody(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    criteria: Any = None
    """A pattern as a description stores it: `{"type": ..., "where": {...}}`"""
    named: list[UUID] = []
    """The ids of the entities the document being edited names: never candidates"""


def refused(error: PanglossSearchError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": str(error), "error": type(error).__name__},
    )


@router.post(
    "/preview",
    operation_id="criteria_preview",
    dependencies=LOGGED_IN,
    response_model=reading.Preview,
)
async def preview(body: PreviewBody) -> Any:
    """What the criteria would find if a description with them were saved now, under the rules of an evaluation"""
    try:
        return await reading.preview(body.criteria, body.named)
    except PanglossSearchError as error:
        return refused(error)


class ResolveBody(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    entity: Reference
    """What takes the description's place"""
    version: int | None = None
    """The version of the document the choice was made on (as `If-Match` of an update); the version now if not given"""


@router.post(
    "/{id}/resolve",
    operation_id="criteria_resolve",
    dependencies=LOGGED_IN,
    response_model=Resolved,
)
async def resolve(id: UUID, body: ResolveBody) -> Any:
    """Resolving, "This is…": the entity takes the place of the description in its document, as an update by the user (the
    description stays in the document's history). It need not be a candidate; it must be what the field takes"""
    return await resolving.resolve(id, body.entity, body.version)


@router.get(
    "/settled/{head_id}", operation_id="criteria_settled", dependencies=LOGGED_IN
)
async def settled(head_id: UUID) -> dict[str, bool]:
    """Whether the descriptions of the head have their result since its last write (none pending)"""
    return {"settled": not await is_pending(head_id)}


@router.get("/{id}/candidates", operation_id="criteria_candidates")
async def candidates(
    id: UUID,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> reading.CandidatesPage:
    """The linked candidates of a description, by label, in pages: those the reader may see"""
    found = await reading.candidates(id, page, page_size)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"There is no description {id}")
    return found
