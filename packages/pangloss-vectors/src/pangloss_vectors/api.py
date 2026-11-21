"""What the app adds to the server (implementation_docs/vectors.md, "The API"):

    GET /api/{NAME}/{ref}/similar?profile=default&type=Person&type=Group&field=Activity.carried_out_by&limit=10
        the items nearest the item, of any Document or Entity class NAME (the item's own or one above it): {status,
        results, profiles, groups}, `status` being "ok", "pending" (the item has no vector yet, or the profile has not
        been built), "rebuild_due" (a rebuild is due: the results, if any, are of the vectors in use) or "excluded"
        (the item's own class has no vectors, `meta.included`: `VectorsMeta(include=False)`, `VECTORS_EXCLUDE`, a
        stand-in: it has none and never will, and no search is made), and `results` the reference view of each, as a
        list gives it, with its `similarity` (the cosine of the two vectors), nearest first, never one of a class that
        has no vectors (left out by `nearest`, before a rebuild has removed its vectors), those of a similarity of 0 (below 0.005) or less left out; `profiles` the names of the profiles (`default` first, then the others in order)
        and `groups` those a search can be narrowed to, for what the interface offers. What
        the reader may see, as for `GET /api/NAME/{id}`: 404 if the item is not there or the reader may not see it.
        The item may be a document nested in another (a statement in a factoid; what the reader may see of it is its
        head's), and so may the results: the reference view of a nested document is the one the core's search gives
        it, with `meta.headNodeId`, `meta.headNodeType` and `meta.isHeadNode` false (`views.py`).
        `type`: a class of documents or entities (its concrete classes: it and those below it that are not
        abstract; a trait, the classes that have it), and may be given more than once; `field`: `Model.field`, the
        entity classes that relation of that model can hold (through wrappers, the stand-ins left out: `fields.py`);
        with both, the classes of either. One `type` that is a group (a class with `VectorsMeta(searchable=True)`) and
        no `field` is searched through the group's index, as it always was; anything else as `search.nearest(types=)`
        does it, through the indexes of the groups it covers and an exact scan of the rest (step 7a.4). A class that
        the names given reach only as a class it is *by use* (a typology's `RoleType` below `Role`, by its
        `__labels_unmanaged__`) is given only where something uses it as one (`by_use.py`, step 7a.5): `type=Role` or a
        field that holds roles gives a type only where a relation that takes a role points at it; `type=RoleType`, or
        no `type`, every type. A name that is
        no such class, and a field that is no model's, no field of it, not a relation or reaches no entity, are a 422
        that names it. `limit` 1 to 100; an unknown profile is a 422.
        `ref` is what `GET /api/NAME/{ref}` takes: the item's id, or, of an entity, one of its URLs (the rest of the
        path, read by `pangloss_api.routes.models.reference_from`: `http:/` is `http://`, and the query string is the
        URL's but for the route's own parameters); a URL at a document class is a 422 (a document is found by its id),
        and a URL no entity has is a 404. A URL of an entity merged into another names its survivor. The path is
        matched to its last `/similar`, so an entity whose own URL ends in `/similar` is not read at
        `GET /api/NAME/{that URL}` (this route takes it, without the `/similar`): it is read by its id, and its
        similar are at `…/similar/similar`
    GET /api/vectors/status
        for each part and profile, what is in use and whether a rebuild is due, and why; `rebuilding`, the holder
        (`by`) and start (`since`) of the lease of a rebuild running now, or null (login)

And the worker that keeps the vectors current after writes, as a background task (`VECTORS_WORKER_IN_SERVER = False`
to run it in a process of its own, `pangloss vectors worker`).

(`pangloss-api` includes the routers of installed apps before those of the models, so the similar route is not taken
by a model's own; and the similar route matches only where NAME is a model's (`ModelRoute`), so that an app's route
ending in `/similar` after it, `/api/review/unreconciled/{id}/similar`, is not taken by it either.)
"""

from typing import Annotated, Any
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    HTTPException,
    Path,
    Query,
    Request,
    status,
)
from fastapi.routing import APIRoute
from pangloss_api import BackgroundTask, get_current_user
from pangloss_api.routes.models import not_found, reference_from, routable_models
from starlette.routing import Match
from starlette.types import Scope

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

# The least similarity an item is given at: one that would be written 0.00, or less, has nothing in common with the
# item asked about, and is left out (the user, 2026-11-21)
MIN_SIMILARITY = 0.005


@router.get("/vectors/status", operation_id="vectors_status", dependencies=LOGGED_IN)
async def get_status() -> dict[str, Any]:
    """For each part and each profile: the generation in use, when it was built, how many vectors, and whether a
    rebuild is due, with the reasons; and the rebuild running now, if one is"""
    from pangloss_vectors.status import status as reading

    return (await reading()).as_json()


def find_model(name: str) -> type:
    for model in routable_models():
        if model.__name__ == name:
            return model
    raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"There is no model '{name}'")


def unprocessable(message: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=message)


class ModelRoute(APIRoute):
    """A route whose path begins with the name of a model (`/{model_name}/...`): a request whose first part is not the
    name of a routable model is no match, and goes on to the routes after it (an app's route that ends as this one
    does: `/api/review/unreconciled/{id}/similar`, whose `model_name` would be `review`)"""

    def matches(self, scope: Scope) -> tuple[Match, Scope]:
        match, child = super().matches(scope)
        if match is Match.NONE:
            return match, child
        name = child.get("path_params", {}).get("model_name")
        if not any(model.__name__ == name for model in routable_models()):
            return Match.NONE, {}
        return match, child


# The query parameters of the similar route: the rest of the query string is the URL's that names the item
SIMILAR_PARAMETERS = {"profile", "type", "field", "limit"}

# What a 404 at a URL adds: the path is matched to its last `/similar`
URL_ENDING_IN_SIMILAR = (
    " (an entity whose URL itself ends in /similar is read by its id: at its URL, this route takes the URL without "
    "the /similar)"
)

# (a router of its own, for the route class: it is included in `router`)
models_router = APIRouter(route_class=ModelRoute)


@models_router.get("/{model_name}/{ref:path}/similar", operation_id="vectors_similar")
async def similar(
    request: Request,
    model_name: str,
    ref: Annotated[
        str,
        Path(description="The id of the item, or, of an entity, one of its URLs"),
    ],
    profile: str = DEFAULT_PROFILE,
    types: Annotated[
        list[str] | None,
        Query(
            alias="type",
            description="Only items of these classes of documents or entities (or of a class below one); may be given "
            "more than once",
        ),
    ] = None,
    field: Annotated[
        str | None,
        Query(
            description="Only items of the entity classes this field can hold, as Model.field "
            "(Activity.carried_out_by); with `type`, of either",
        ),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 10,
) -> dict[str, Any]:
    """The items nearest this one, by a profile's vectors, as the reader may see them, nearest first"""
    from pangloss_core import backend
    from pangloss_models import Entity

    from pangloss_vectors.search import nearest
    from pangloss_vectors.views import reference_views, visible_item

    model = find_model(model_name)
    reference = reference_from(request, ref, SIMILAR_PARAMETERS)
    if not isinstance(reference, UUID) and not issubclass(model, Entity):
        raise unprocessable(
            f"{model.__name__} is a document class: a document is found by its id, not by a URL"
        )
    known = profiles()
    if profile not in known:
        raise unprocessable(
            f"There is no profile named {profile!r}: the profiles are {', '.join(sorted(known))}"
        )
    group, narrowed_to = narrowing(types, field)
    see_unpublished = backend.current().unpublished_visible()
    item = await visible_item(model, reference, see_unpublished)
    if item is None:
        missing = not_found(model, reference)
        if not isinstance(reference, UUID):
            missing.detail += URL_ENDING_IN_SIMILAR
        raise missing
    # (what the interface's controls offer, in the one answer)
    offered = {
        "profiles": sorted(known, key=lambda name: (name != DEFAULT_PROFILE, name)),
        "groups": meta.groups(),
    }
    if not meta.included(item.type):
        return {"status": "excluded", "results": [], **offered}
    found = await nearest(
        item.id,
        profile=profile,
        group=group,
        types=narrowed_to,
        k=limit,
        see_unpublished=see_unpublished,
        # (the names asked, which say whether a class is asked as itself or only by use: `by_use.given_by_use`)
        asked=[*(types or []), *([field] if field is not None else [])] or None,
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
            if hit.id in views and hit.score >= MIN_SIMILARITY
        ],
        **offered,
    }


def narrowing(
    types: list[str] | None, field: str | None
) -> tuple[str | None, list[str] | None]:
    """What a search is narrowed to by `type` and `field`: one `type` that is a group (and no `field`), as the group,
    its index asked as it always was; otherwise the concrete classes of each `type` and those `field` can hold, all of
    them, as types (`search.narrowed` says how they are searched); or neither. A 422 that names what is wrong"""
    from pangloss_vectors.fields import NotAClass, NotAField, classes_of, field_types

    if not types and field is None:
        return None, None
    if types is not None and len(types) == 1 and field is None:
        if types[0] in meta.groups():
            return types[0], None
    named: set[str] = set()
    try:
        for name in types or []:
            classes = classes_of(name)
            if not classes:
                raise NotAClass(
                    f"{name!r} has no classes that are not abstract: there are no items of it to find"
                )
            named |= set(classes)
        if field is not None:
            named |= set(field_types(field))
    except (NotAClass, NotAField) as refused:
        raise unprocessable(str(refused)) from None
    return None, sorted(named)


router.include_router(models_router)
