"""`/api/typology/{name}`: the hierarchy of a typology (`name` is the name of its entity, `RoleType`; the name of
the typology itself, `RoleTypology`, is taken for it too).

A type is an entity, so its ordinary endpoints (`/RoleType`, ...) are there as for any entity; these are the hierarchy that
those cannot do: the whole tree, a type as it is viewed (parents, subtypes, the entities that have it), its path, moving
it, and switching it on as another class. Reading is open, with the visibility of any search; changing needs a user who is
logged in.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pangloss_api import get_current_user
from pydantic import BaseModel, StringConstraints

from pangloss_typology import service
from pangloss_typology.typology import Typology

router = APIRouter(prefix="/api/typology", tags=["typology"])
logged_in = [Depends(get_current_user)]


def typology_named(name: str) -> type[Typology]:
    found = Typology.named(name)
    if found is None:
        known = ", ".join(sorted(Typology.registry)) or "(none)"
        raise HTTPException(
            status_code=404, detail=f"There is no typology {name}. Known: {known}"
        )
    return found


def typology_of(name: str) -> type[Typology]:
    return typology_named(name)


Named = Annotated[type[Typology], Depends(typology_of)]


def failed(error: Exception) -> HTTPException:
    if isinstance(error, service.NotFound):
        return HTTPException(status_code=404, detail=str(error))
    return HTTPException(status_code=409, detail=str(error))


class Move(BaseModel):
    to: UUID | None = None
    """The new supertype; none makes it a root"""


class Edit(BaseModel):
    """What to change; what is not given is left as it is"""

    label: str | None = None
    description: str | None = None
    labels: dict[str, str] | None = None
    """By language code: `{"de": "Sekretär"}`"""


class Switch(BaseModel):
    on: bool


class New(BaseModel):
    """A new type: below `supertype`, or at the top level without one"""

    label: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    supertype: UUID | None = None
    description: str | None = None
    labels: dict[str, str] | None = None
    """By language code: `{"de": "Sekretär"}`"""


@router.get("/{name}/tree")
async def get_tree(typology: Named):
    """The whole hierarchy, nested, each level by label: `[{id, label, children}]`"""
    return await service.tree_of(typology)


@router.get("/{name}/{id}", response_model=service.TypeView)
async def get_type(
    typology: Named,
    id: UUID,
    include_subtypes: Annotated[
        bool,
        Query(
            description="List the entities of the subtypes too (and count them in the subtypes)"
        ),
    ] = True,
    entity_type: Annotated[
        str | None, Query(description="Only the entities of this class")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=service.MAX_LIMIT)] = service.LIMIT,
    after: Annotated[
        str | None, Query(description="`next` of the previous page")
    ] = None,
):
    try:
        return await service.view(
            typology,
            id,
            include_subtypes=include_subtypes,
            entity_type=entity_type,
            limit=limit,
            after=after,
        )
    except (service.NotFound, service.Refused) as error:
        raise failed(error) from error


@router.get("/{name}/{id}/path", response_model=list[service.TypeRef])
async def get_path(typology: Named, id: UUID):
    """From the root to the type"""
    try:
        return await service.path(typology, id)
    except service.NotFound as error:
        raise failed(error) from error


@router.post(
    "/{name}",
    response_model=service.TypeOut,
    status_code=201,
    dependencies=logged_in,
)
async def post_type(typology: Named, body: New):
    """Make a type, below another or at the top level (404 if the supertype is not there, 409 for a label in a language
    the typology does not have)"""
    try:
        return await service.create(
            typology,
            body.label,
            supertype=body.supertype,
            description=body.description,
            labels=body.labels,
        )
    except (service.NotFound, service.Refused) as error:
        raise failed(error) from error


@router.patch("/{name}/{id}", response_model=service.TypeOut, dependencies=logged_in)
async def patch_type(typology: Named, id: UUID, body: Edit):
    """Change a type's label, description or labels in other languages (a new version of the entity)"""
    try:
        return await service.update(typology, id, **body.model_dump(exclude_unset=True))
    except (service.NotFound, service.Refused) as error:
        raise failed(error) from error


@router.post(
    "/{name}/{id}/move", response_model=service.TypeOut, dependencies=logged_in
)
async def post_move(typology: Named, id: UUID, body: Move):
    """Move the type below another (409 with the reason if that would put it below itself)"""
    try:
        return await service.move(typology, id, body.to)
    except (service.NotFound, service.Refused) as error:
        raise failed(error) from error


@router.put(
    "/{name}/{id}/concrete", response_model=service.TypeOut, dependencies=logged_in
)
async def put_concrete(typology: Named, id: UUID, body: Switch):
    """Switch the type on or off as the other class it can be (`also`)"""
    try:
        return await service.set_concrete(typology, id, body.on)
    except (service.NotFound, service.Refused) as error:
        raise failed(error) from error
