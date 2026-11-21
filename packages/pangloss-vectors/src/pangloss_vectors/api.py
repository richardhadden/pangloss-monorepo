"""What the app adds to the server (implementation_docs/vectors.md, "The API"):

    GET /api/{NAME}/{id}/similar?profile=default&type=Person&limit=10
        the items nearest the item, of any Document or Entity class NAME (the item's own or one above it): {status,
        results}, `status` being "ok", "pending" (the item has no vector yet, or the profile has not been built) or
        "rebuild_due" (a rebuild is due: the results, if any, are of the vectors in use), and `results` the reference
        view of each, as a list gives it, with its `similarity` (the cosine of the two vectors), nearest first. What
        the reader may see, as for `GET /api/NAME/{id}`: 404 if the item is not there or the reader may not see it.
        The item may be a document nested in another (a statement in a factoid; what the reader may see of it is its
        head's), and so may the results: the reference view of a nested document is the one the core's search gives
        it, with `meta.headNodeId`, `meta.headNodeType` and `meta.isHeadNode` false (`views.py`).
        `type`: a group (a class with `VectorsMeta(searchable=True)`), 422 if it is not one; `limit` 1 to 100; an
        unknown profile is a 422
    GET /api/vectors/status
        for each part and profile, what is in use and whether a rebuild is due, and why (login)

And the worker that keeps the vectors current after writes, as a background task (`VECTORS_WORKER_IN_SERVER = False`
to run it in a process of its own, `pangloss vectors worker`).

(`pangloss-api` includes the routers of installed apps before those of the models, so the similar route is not taken
by a model's own.)
"""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, status
from pangloss_api import BackgroundTask, get_current_user
from pangloss_api.routes.models import routable_models

from pangloss_vectors import meta, store
from pangloss_vectors.parts import DEFAULT_PROFILE, profiles
from pangloss_vectors.settings import worker_in_server
from pangloss_vectors.status import status_of

router = APIRouter(prefix="/api", tags=["vectors"])

LOGGED_IN = [Depends(get_current_user)]


def configure_app(app: FastAPI, settings: Any) -> None:
    if worker_in_server(settings):
        from pangloss_vectors.worker import worker

        app.state.background_tasks.append(BackgroundTask("vectors", worker.run))


# The most items a request may ask for
MAX_LIMIT = 100


@router.get("/vectors/status", operation_id="vectors_status", dependencies=LOGGED_IN)
async def get_status() -> dict[str, Any]:
    """For each part and each profile: the generation in use, when it was built, how many vectors, and whether a
    rebuild is due, with the reasons"""
    return status_of(await store.states()).as_json()


def find_model(name: str) -> type:
    for model in routable_models():
        if model.__name__ == name:
            return model
    raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"There is no model '{name}'")


def unprocessable(message: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=message)


@router.get("/{model_name}/{id}/similar", operation_id="vectors_similar")
async def similar(
    model_name: str,
    id: UUID,
    profile: str = DEFAULT_PROFILE,
    group: Annotated[
        str | None,
        Query(
            alias="type",
            description="Only items of this group (a class with VectorsMeta(searchable=True), or one below it)",
        ),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 10,
) -> dict[str, Any]:
    """The items nearest this one, by a profile's vectors, as the reader may see them, nearest first"""
    from pangloss_core import backend

    from pangloss_vectors.search import nearest
    from pangloss_vectors.views import reference_views, visible_item

    model = find_model(model_name)
    known = profiles()
    if profile not in known:
        raise unprocessable(
            f"There is no profile named {profile!r}: the profiles are {', '.join(sorted(known))}"
        )
    if group is not None and group not in meta.groups():
        raise unprocessable(
            f"{group!r} is not a group a search can be narrowed to: the groups are "
            f"{', '.join(meta.groups()) or 'none'} (a class with VectorsMeta(searchable=True))"
        )
    see_unpublished = backend.current().unpublished_visible()
    item = await visible_item(model, id, see_unpublished)
    if item is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"There is no {model.__name__} with id {id}",
        )
    found = await nearest(
        item,
        profile=profile,
        group=group,
        k=limit,
        see_unpublished=see_unpublished,
    )
    answer_status = found.status
    if answer_status == "ok":
        state = status_of(await store.states()).profile(profile)
        if state is not None and state.rebuild_due:
            answer_status = "rebuild_due"
    views = await reference_views([hit.id for hit in found.hits], see_unpublished)
    return {
        "status": answer_status,
        "results": [
            {**views[hit.id], "similarity": hit.score}
            for hit in found.hits
            if hit.id in views
        ],
    }
