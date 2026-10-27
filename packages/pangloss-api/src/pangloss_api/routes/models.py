"""Routes for the Documents and Entities declared in the project.

For each one that is not abstract, `NAME` being its class name:

| | | |
|-|-|-|
| `GET`    | `/api/NAME`                       | list (`q`, `deep`, `page`, `page_size`) |
| `GET`    | `/api/NAME/{id}`         | the `HeadView` |
| `POST`   | `/api/NAME`              | create (`Create`); login required |
| `GET`    | `/api/NAME/{id}/edit`    | to edit: an entity's `EditView`, a document's `HeadView`; login required |
| `PUT`    | `/api/NAME/{id}`         | update (`Update`); login required, and `If-Match` |
| `DELETE` | `/api/NAME/{id}`         | delete; login required |
| `POST`   | `/api/NAME/{id}/undelete`| undelete; login required |

For an entity, `{id}` can also be one of its URLs, as it is, to get it:
`/api/Person/https://example.com/people/john`. Everything else (`/edit`, and
the changes: update, delete, undelete) is only ever at the id.

An update says which version it is based on, with the header `If-Match` (the `ETag` of
the edit view): if the object has been updated since, it is refused. Reading is open to
everyone. The functions they call are those bound to the models
by the database backend (`Model.get`, `Model.list`, `Model.Create(...).save()` ...).
"""

import inspect
import re
from typing import Annotated, Any, Union
from uuid import UUID

from fastapi import (
    APIRouter,
    Body,
    Depends,
    Header,
    HTTPException,
    Path,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import RedirectResponse
from pangloss_models.exceptions import PanglossInitialisationError
from pangloss_models.model_bases.base_models import _ListItems
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_registry import ModelRegistry
from pangloss_models.protection import changed_fields, protection_of
from pangloss_models.utils import get_concrete_types
from pydantic import AnyHttpUrl, TypeAdapter, ValidationError

from pangloss_api.dependencies import get_current_user

# The most items a page of a list may have
MAX_PAGE_SIZE = 500

logged_in = [Depends(get_current_user)]


# What else is at `/api/...` or in the root of the app
RESERVED_NAMES = {"users", "autocomplete", "sdk", "docs", "redoc", "openapi.json"}


def check_name_is_free(name: str) -> None:
    """A model's routes are at `/api/NAME`: it cannot have the name of something else"""
    if name.lower() in RESERVED_NAMES:
        raise PanglossInitialisationError(
            f"A model cannot be called '{name}': the routes at /api/{name} are used by "
            "the API itself"
        )


def routable_models() -> list[type[Document | Entity]]:
    """The registered Documents and Entities that routes are made for"""
    return [
        model
        for model in ModelRegistry.all_models().values()
        if isinstance(model, type)
        and issubclass(model, (Document, Entity))
        and not getattr(model._meta, "abstract", False)
        and hasattr(model, "HeadView")
    ]


async def called(value: Any) -> Any:
    """The result of a database function, which may or may not be async"""
    return await value if inspect.isawaitable(value) else value


def not_found(model: type, id: UUID | AnyHttpUrl) -> HTTPException:
    what = "id" if isinstance(id, UUID) else "URL"
    return HTTPException(
        status.HTTP_404_NOT_FOUND,
        detail=f"There is no {model.__name__} with {what} {id}",
    )


HTTP_SCHEME = re.compile(r"^(https?):/+", re.IGNORECASE)
URL_ADAPTER = TypeAdapter(AnyHttpUrl)


def parse_reference(reference: str, query: str = "") -> UUID | AnyHttpUrl:
    """What names an entity in a path: its id, or one of its URLs.

    A URL arrives as the rest of the path, so some changes are made to it: `http:/`
    is `http://` (servers and proxies often merge slashes), and the query string of
    the request is the URL's (an entity's URL with a `?` in it)."""
    try:
        return UUID(reference)
    except ValueError:
        pass

    candidate = HTTP_SCHEME.sub(lambda match: f"{match.group(1).lower()}://", reference)
    if query:
        candidate = f"{candidate}?{query}"
    try:
        return URL_ADAPTER.validate_python(candidate)
    except ValidationError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"'{reference}' is neither an id nor an http(s) URL",
        ) from None


async def entity_reference(
    request: Request,
    ref: Annotated[str, Path(description="The id of the entity, or one of its URLs")],
) -> UUID | AnyHttpUrl:
    return parse_reference(ref, request.url.query)


async def entity_id(
    request: Request,
    ref: Annotated[str, Path(description="The id of the entity")],
) -> UUID:
    """The id of an entity for a route that is only at an id (a change, or loading it
    to edit): a URL is refused"""
    reference = parse_reference(ref, request.url.query)
    if not isinstance(reference, UUID):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="This is done at the id of an entity, not at a URL: get the entity "
            "at the URL to find its id",
        )
    return reference


def etag(version: int) -> str:
    return f'"{version}"'


def expected_version(if_match: str | None) -> int | None:
    """The version that an update is based on, from the header `If-Match`: the `ETag`
    that the edit view had (`"3"`); or `*`, to update whatever the version is (None).

    The header is required: without it, whoever updates last would silently undo the
    changes of whoever updated before."""
    if if_match is None:
        raise HTTPException(
            status.HTTP_428_PRECONDITION_REQUIRED,
            detail="An update must say which version it is based on, with the header "
            'If-Match: the ETag of the edit view ("3"), or * to update whatever the '
            "version is",
        )
    value = if_match.strip()
    if value == "*":
        return None
    if value.startswith("W/"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail='If-Match must be a strong ETag, such as "3"',
        )
    try:
        version = int(value.strip('"'))
    except ValueError:
        version = 0
    if version < 1 or (value.count('"') not in (0, 2)):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail='If-Match must be the version in quotes ("3"), or *',
        )
    return version


def refuse_if_protected(fields: list[str]) -> None:
    """Refuse a request that changes fields that something other than a person keeps up to date"""
    if fields:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail=f"{', '.join(fields)} cannot be changed here: kept up to date by something else",
        )


def list_response_model(model: type[Document | Entity]) -> Any:
    reference_views = [t.ReferenceView for t in get_concrete_types(model)]  # type: ignore[attr-defined]
    return _ListItems[Union[*reference_views]]  # type: ignore[valid-type]


def build_router(model: type[Document | Entity]) -> APIRouter:
    is_entity = issubclass(model, Entity)
    name = model.__name__

    check_name_is_free(name)
    router = APIRouter(prefix=f"/api/{name}", tags=[name])

    head_view = model.HeadView
    reference_view = model.ReferenceView
    create_model = model.Create
    update_model = model.Update
    edit_response = model.EditView if is_entity else head_view  # type: ignore[attr-defined]
    protection = protection_of(model)
    # A read by a class gives a node of a subclass as that subclass: its view is of the subclass
    # (`type` says which), it is edited at the subclass's route, and it cannot be updated as this class
    has_subclasses = bool(get_concrete_types(model, include_abstract=True) - {model})
    head_views = [t.HeadView for t in get_concrete_types(model)]  # type: ignore[attr-defined]
    get_response = Union[*head_views] if len(head_views) > 1 else head_view  # type: ignore[valid-type]

    # The entity in a path is its id, or, to get it, one of its URLs (which has slashes
    # in it, so the path continues to the end, or to `/edit` or `/undelete`: those
    # routes come first). Anything else is only at an id. A document is only found
    # by its id.
    if is_entity:
        item = "/{ref:path}"
        ItemId = Annotated[UUID | AnyHttpUrl, Depends(entity_reference)]
        ChangeId = Annotated[UUID, Depends(entity_id)]
    else:
        item = "/{id}"
        ItemId = ChangeId = UUID

    @router.get(
        "", response_model=list_response_model(model), operation_id=f"list_{name}"
    )
    async def list_items(
        q: Annotated[str | None, Query(description="Search the labels")] = None,
        deep: Annotated[bool, Query(description="Search more than the labels")] = False,
        page: Annotated[int | None, Query(ge=1)] = None,
        page_size: Annotated[int | None, Query(ge=1, le=MAX_PAGE_SIZE)] = None,
    ):
        return await called(
            model.list(  # type: ignore[call-arg]
                search_terms=q, page_number=page, page_size=page_size, deep_search=deep
            )
        )

    @router.post(
        "",
        status_code=status.HTTP_201_CREATED,
        response_model=Union[reference_view, head_view],  # type: ignore[valid-type]
        dependencies=logged_in,
        operation_id=f"create_{name}",
    )
    async def create_item(
        body: Annotated[create_model, Body()],  # type: ignore[valid-type]
        response: Response,
        detail: Annotated[
            bool, Query(description="Return the whole HeadView, not a summary")
        ] = False,
    ):
        if protection.read_only:
            refuse_if_protected(changed_fields(model, body, None))
        created = await called(body.save(detail=detail))  # type: ignore[attr-defined]
        response.headers["ETag"] = etag(1)
        return created

    @router.get(
        f"{item}/edit",
        response_model=edit_response,
        dependencies=logged_in,
        operation_id=f"edit_{name}",
    )
    async def edit_item(id: ChangeId, response: Response):  # type: ignore[valid-type]
        """What to edit. Its `ETag` is the version, which an update says it is based
        on (`If-Match`)."""
        read = model.get_for_edit if is_entity else model.get  # type: ignore[attr-defined]
        found = await called(read(id))
        if found is None:
            raise not_found(model, id)
        if found.type != name:
            # (a subclass: its edit view, and the body of its update, are its own)
            return RedirectResponse(
                f"/api/{found.type}/{found.id}/edit",
                status_code=status.HTTP_308_PERMANENT_REDIRECT,
            )
        response.headers["ETag"] = etag(found.meta.version)
        return found

    @router.post(
        f"{item}/undelete",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=logged_in,
        operation_id=f"undelete_{name}",
    )
    async def undelete_item(id: ChangeId):  # type: ignore[valid-type]
        await called(model.undelete(id))  # type: ignore[attr-defined]
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.get(item, response_model=get_response, operation_id=f"get_{name}")
    async def get_item(id: ItemId, response: Response):  # type: ignore[valid-type]
        """The item, as the class it is: for a class that has subclasses, the view of the subclass (its
        `type` says which; `Content-Location` is where it is edited)."""
        found = await called(model.get(id))  # type: ignore[arg-type]
        if found is None:
            raise not_found(model, id)
        if found.type != name:
            response.headers["Content-Location"] = f"/api/{found.type}/{found.id}"
        return found

    @router.put(
        item,
        response_model=Union[reference_view, head_view],  # type: ignore[valid-type]
        dependencies=logged_in,
        operation_id=f"update_{name}",
    )
    async def update_item(
        id: ChangeId,  # type: ignore[valid-type]
        body: Annotated[update_model, Body()],  # type: ignore[valid-type]
        response: Response,
        if_match: Annotated[
            str | None,
            Header(
                alias="If-Match",
                description="The version this update is based on: the ETag of the "
                'edit view ("3"). `*` updates whatever the version is. 412 if it is '
                "not the latest.",
            ),
        ] = None,
        detail: Annotated[
            bool, Query(description="Return the whole HeadView, not a summary")
        ] = False,
    ):
        if body.id != id:  # type: ignore[attr-defined]
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="The id in the body is not the id in the path",
            )
        based_on = expected_version(if_match)
        if protection.read_only or has_subclasses:
            read = model.get_for_edit if is_entity else model.get  # type: ignore[attr-defined]
            stored = await called(read(id))
            if stored is None:
                raise not_found(model, id)
            if has_subclasses and stored.type != name:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    detail=f"This is a {stored.type}, not a {name}: update it at "
                    f"/api/{stored.type}/{id}, with a {stored.type}",
                )
            if protection.read_only:
                refuse_if_protected(changed_fields(model, body, stored))
        updated = await called(
            body.save(detail=detail, expected_version=based_on)  # type: ignore[attr-defined]
        )
        # The new version, to go on editing from (not known after a forced update,
        # unless the whole thing is returned)
        if detail:
            response.headers["ETag"] = etag(updated.meta.version)
        elif based_on is not None:
            response.headers["ETag"] = etag(based_on + 1)
        return updated

    @router.delete(
        item,
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=logged_in,
        operation_id=f"delete_{name}",
        responses={409: {"description": "An entity that is referred to"}},
    )
    async def delete_item(id: ChangeId):  # type: ignore[valid-type]
        if protection.delete_only_if:
            found = await called(model.get(id))  # type: ignore[arg-type]
            if found is not None and not getattr(
                found, protection.delete_only_if, False
            ):
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    detail=f"A {name} is kept in step with something outside Pangloss, so it cannot be "
                    f"deleted here until '{protection.delete_only_if}' is true",
                )
        await called(model.delete(id))  # type: ignore[arg-type]
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
