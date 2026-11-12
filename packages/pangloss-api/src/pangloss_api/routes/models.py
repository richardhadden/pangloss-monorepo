"""Routes for the Documents and Entities declared in the project.

For each one, `NAME` being its class name (an abstract class has only those that read, and
they give the items of its subclasses; a document with `create_directly=False` has no `POST`).
An entity class also has the routes of a merge (`pangloss_api.routes.merges`), abstract or not:

| | | |
|-|-|-|
| `GET`    | `/api/NAME`                       | list (`q`, `deep`, `used_only`, `use_counts`, `page`, `page_size`) |
| `GET`    | `/api/NAME/{id}`         | the `HeadView` (an entity: `incoming_limit` cuts what refers to it, 0 leaves it out; `extras=false` leaves out what apps add) |
| `GET`    | `/api/NAME/{id}/incoming` | an entity: what refers to it, the first `limit` of every relation, with the counts |
| `GET`    | `/api/NAME/{id}/incoming/{field}` | an entity: what refers to it by one relation (`page`, `page_size`) |
| `POST`   | `/api/NAME`              | create (`Create`); login required |
| `GET`    | `/api/NAME/{id}/edit`    | to edit: an entity's `EditView`, a document's `HeadView`; login required |
| `PUT`    | `/api/NAME/{id}`         | update (`Update`); login required, and `If-Match` |
| `DELETE` | `/api/NAME/{id}`         | delete; login required |
| `POST`   | `/api/NAME/{id}/undelete`| undelete; login required |
| `GET`    | `/api/NAME/{id}/deletable`| whether it can be deleted, and if not why; login required |

For an entity, `{id}` can also be one of its URLs, as it is, to get it:
`/api/Person/https://example.com/people/john`. Everything else (`/edit`, and
the changes: update, delete, undelete) is only ever at the id.

An update says which version it is based on, with the header `If-Match` (the `ETag` of
the edit view): if the object has been updated since, it is refused. Reading is open to
everyone. The functions they call are those bound to the models
by the database backend (`Model.get`, `Model.list`, `Model.Create(...).save()` ...).
"""

import datetime
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
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.exceptions import RequestValidationError
from pangloss_models import (
    Document,
    Entity,
    ModelRegistry,
    PanglossWriteRefused,
    create_heads,
    PanglossInitialisationError,
    PanglossReferenceError,
    hooks,
    protection_of,
)
from pangloss_models.companions import companion_create, companions_of
from pangloss_models.merging import noting_resolved
from pangloss_models.creators import Creator, ToolchainRun, creators_asked, writing_as
from pangloss_models.model_bases.base_models import _ListItems
from pangloss_models.protection import changed_fields
from pangloss_models.utils import get_concrete_types
from pangloss_core import storage_of
from pangloss_users import User
from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    TypeAdapter,
    ValidationError,
)
from pydantic import create_model as make_model
from pydantic.alias_generators import to_camel

from pangloss_api.dependencies import CurrentUser, get_current_user
from pangloss_api.routes.merges import add_merge_routes


class Deletable(BaseModel):
    """Whether something can be deleted (`GET /api/NAME/{id}/deletable`), and if not why"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    deletable: bool
    reason: str | None = None
    # (an entity that is referred to) up to ten of what refers to it: `id`, `type` and `label`
    referenced_by: list[dict[str, str]] = []
    reference_count: int = 0


class IncomingPage(BaseModel):
    """Some of what refers to an entity by one relation (`GET /api/NAME/{id}/incoming/{field}`)"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    field: str
    count: int
    page: int
    page_size: int
    # (as they are in that field of the entity's `HeadView`)
    results: list[Any]


class IncomingFields(BaseModel):
    """What refers to an entity, the first of each relation (`GET /api/NAME/{id}/incoming`)"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    limit: int
    # (how many there are in each incoming field that has any, by the field's key)
    counts: dict[str, int]
    # (the first `limit` of each, by the field's key, as they are in that field of the entity's `HeadView`)
    fields: dict[str, list[Any]]


# How many of what refers to an entity a page has, if the request does not say
DEFAULT_INCOMING_PAGE = 50

# The most items a page of a list may have
MAX_PAGE_SIZE = 500

logged_in = [Depends(get_current_user)]


# What else is at `/api/...` or in the root of the app
RESERVED_NAMES = {
    "users",
    "autocomplete",
    "references",
    "search",
    "merges",
    "rdf",
    "sdk",
    "docs",
    "redoc",
    "openapi.json",
}


def check_name_is_free(name: str) -> None:
    """A model's routes are at `/api/NAME`: it cannot have the name of something else"""
    if name.lower() in RESERVED_NAMES:
        raise PanglossInitialisationError(
            f"A model cannot be called '{name}': the routes at /api/{name} are used by "
            "the API itself"
        )


def routable_models() -> list[type[Document | Entity]]:
    """The registered Documents and Entities that routes are made for: all of them, but the
    abstract ones only have the routes that read, and one that nothing is a kind of (such as
    `DateCharacterisation`, until the project subclasses it) has none"""
    return [
        model
        for model in ModelRegistry.all_models().values()
        if isinstance(model, type)
        and issubclass(model, (Document, Entity))
        and hasattr(model, "HeadView")
        and (not model._meta.abstract or get_concrete_types(model))  # type: ignore[attr-defined]
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


# The parameters of the route that reads an entity: they are the request's, not part of a URL that names the entity
OWN_PARAMETERS = {"incoming_limit", "extras"}


async def entity_reference(
    request: Request,
    ref: Annotated[str, Path(description="The id of the entity, or one of its URLs")],
) -> UUID | AnyHttpUrl:
    query = "&".join(
        part
        for part in request.url.query.split("&")
        if part.split("=")[0] not in OWN_PARAMETERS
    )
    return parse_reference(ref, query)


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


# What a write answers with when it named entities that have been merged into others: each id it gave and the id of
# the survivor it was written as (`given=survivor`, with commas between)
RESOLVED_HEADER = "Pangloss-Resolved-References"


def say_resolved(response: Response, noted: list[tuple[str, str]]) -> None:
    if noted:
        response.headers[RESOLVED_HEADER] = ", ".join(
            f"{given}={survivor}" for given, survivor in noted
        )


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


def named_creators(
    user: User,
    created_by: list[str] | None,
    toolchain: str | None,
    version: str | None,
    date: datetime.date | None,
) -> tuple[Creator, ...] | None:
    """Those a create names as the makers of the item (`?created_by=`, `?toolchain=`), which only an admin may"""
    if toolchain is None and (version is not None or date is not None):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="toolchain_version and toolchain_date are of a toolchain: name it with toolchain=",
        )
    try:
        creators = creators_asked(
            created_by,
            ToolchainRun(toolchain, version, date) if toolchain is not None else None,
        )
    except ValueError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error
    if creators is not None and not user.admin:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Only an admin can say that an item was made by someone else",
        )
    return creators


def list_response_model(model: type[Document | Entity]) -> Any:
    reference_views = [t.ReferenceView for t in get_concrete_types(model)]  # type: ignore[attr-defined]
    return _ListItems[Union[*reference_views]]  # type: ignore[valid-type]


def with_extras(found: Any, extras: dict[str, Any], response: Response) -> JSONResponse:
    """The view, as the response would have been, with what installed apps add to it (`hooks.head_view_extras`:
    `_derived` of `pangloss-derived`)"""
    content = TypeAdapter(type(found)).dump_python(found, mode="json", by_alias=True)
    content.update(extras)
    return JSONResponse(content, headers=dict(response.headers))


class CompanionSent(BaseModel):
    """A companion of the entity, by its name, as the interface sends it: the parts that are filled in, without the
    entity, which the server puts in them"""

    model_config = ConfigDict(extra="forbid")
    name: str
    document: dict[str, Any]


def add_with_companions_route(
    router: APIRouter, model: type[Entity], read_only: Any
) -> None:
    """`POST /api/NAME/with-companions`: the entity and its companions, made in one transaction
    (implementation_docs/companion-documents.md)"""
    name = model.__name__
    companion_types = sorted({c.document for c in companions_of(model)})
    companion_views = [
        ModelRegistry.all_models()[t].ReferenceView for t in companion_types
    ]  # type: ignore[attr-defined]
    companion_heads = [ModelRegistry.all_models()[t].HeadView for t in companion_types]  # type: ignore[attr-defined]
    body_model = make_model(
        f"{name}WithCompanions",
        __config__=ConfigDict(extra="forbid"),
        item=(model.Create, ...),  # type: ignore[attr-defined]
        companions=(list[CompanionSent], []),
    )
    answer = make_model(
        f"{name}WithCompanionsMade",
        item=(Union[model.ReferenceView, model.HeadView], ...),  # type: ignore[attr-defined,valid-type]
        companions=(list[Union[*companion_views, *companion_heads]], ...),  # type: ignore[valid-type]
    )

    @router.post(
        "/with-companions",
        status_code=status.HTTP_201_CREATED,
        response_model=answer,
        dependencies=logged_in,
        operation_id=f"create_{name}_with_companions",
    )
    async def create_with_companions(
        body: Annotated[body_model, Body()],  # type: ignore[valid-type]
        request: Request,
        response: Response,
        user: CurrentUser,
        detail: Annotated[
            bool, Query(description="Return the whole HeadViews, not summaries")
        ] = False,
        created_by: Annotated[
            list[str] | None, Query(description="As for a create")
        ] = None,
        toolchain: Annotated[str | None, Query(description="As for a create")] = None,
        toolchain_version: Annotated[str | None, Query()] = None,
        toolchain_date: Annotated[datetime.date | None, Query()] = None,
    ):
        """Make the entity and the companions sent, in one transaction: each companion is the document of a
        `Companion` of the class, by its name, with the entity put in the field of each part that is for it"""
        item = body.item  # type: ignore[attr-defined]
        sent: list[CompanionSent] = body.companions  # type: ignore[attr-defined]
        if read_only:
            refuse_if_protected(changed_fields(model, item, None))
        names = [c.name for c in sent]
        for index, given in enumerate(sent):
            if names.index(given.name) != index:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=[
                        {
                            "loc": ["body", "companions", index, "name"],
                            "msg": f"{given.name!r} is given twice",
                            "type": "refused",
                        }
                    ],
                )
        creators = named_creators(
            user, created_by, toolchain, toolchain_version, toolchain_date
        )
        with writing_as(creators):
            entity = item._to_db_model()
        made = []
        for index, given in enumerate(sent):
            where = ("companions", index, "document")
            try:
                companion = companion_create(
                    model, entity.id, given.name, given.document
                )
            except PanglossWriteRefused as error:
                error.path = (*where, *error.path)
                raise
            except ValidationError as error:
                raise RequestValidationError(
                    [{**e, "loc": ("body", *where, *e["loc"])} for e in error.errors()],
                    body=await request.json(),
                ) from error
            protection = protection_of(type(companion)._owner)  # type: ignore[attr-defined]
            if protection.read_only:
                refuse_if_protected(
                    changed_fields(type(companion)._owner, companion, None)
                )  # type: ignore[attr-defined]
            made.append(companion)
        try:
            with writing_as(creators), noting_resolved() as resolved:
                written = await create_heads(entity, *made, detail=detail)
        except PanglossWriteRefused as error:
            index = getattr(error, "item_index", None)
            if index == 0:
                error.path = ("item", *error.path)
            elif index is not None:
                error.path = ("companions", index - 1, "document", *error.path)
            raise
        response.headers["ETag"] = etag(1)
        say_resolved(response, resolved)
        return {"item": written[0], "companions": written[1:]}


def build_router(model: type[Document | Entity]) -> APIRouter:
    is_entity = issubclass(model, Entity)
    name = model.__name__

    check_name_is_free(name)
    router = APIRouter(prefix=f"/api/{name}", tags=[name])

    head_view = model.HeadView
    reference_view = model.ReferenceView
    # An abstract class has no items of its own, so it can only be read: listed, and found
    # (as the subclass the item is); everything that changes or edits one is at its subclass
    writable = not getattr(model._meta, "abstract", False)
    create_model = model.Create if writable else None
    update_model = model.Update if writable else None
    edit_response = (model.EditView if is_entity else head_view) if writable else None  # type: ignore[attr-defined]
    protection = protection_of(model) if writable else None
    # A document that is only ever part of another (`create_directly=False`) is not made here:
    # what there is of it can still be edited, updated and deleted
    creatable = writable and getattr(model._meta, "create_directly", True)
    # A read by a class gives a node of a subclass as that subclass: its view is of the subclass
    # (`type` says which), it is edited at the subclass's route, and it cannot be updated as this class
    has_subclasses = bool(get_concrete_types(model, include_abstract=True) - {model})
    head_views = [t.HeadView for t in get_concrete_types(model)]  # type: ignore[attr-defined]
    get_response = Union[*head_views] if len(head_views) > 1 else head_view  # type: ignore[valid-type]
    own_types = {t.__name__ for t in get_concrete_types(model)}

    # The entity in a path is its id, or, to get it, one of its URLs (which has slashes
    # in it, so the path continues to the end, or to `/edit`, `/undelete` or `/deletable`: those
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
        published: Annotated[
            bool | None,
            Query(description="Only those that are (or are not) published"),
        ] = None,
        review_status: Annotated[
            str | None,
            Query(description="Only those with this review status (pangloss-review)"),
        ] = None,
        used_only: Annotated[
            bool, Query(description="Only those that something refers to")
        ] = False,
        use_counts: Annotated[
            bool,
            Query(description="With how many things refer to each (`useCounts`)"),
        ] = False,
        page: Annotated[int | None, Query(ge=1)] = None,
        page_size: Annotated[int | None, Query(ge=1, le=MAX_PAGE_SIZE)] = None,
    ):
        return await called(
            model.list(  # type: ignore[call-arg]
                search_terms=q,
                page_number=page,
                page_size=page_size,
                deep_search=deep,
                published=published,
                review_status=review_status,
                used_only=used_only,
                use_counts=use_counts,
            )
        )

    if creatable:

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
            user: CurrentUser,
            detail: Annotated[
                bool, Query(description="Return the whole HeadView, not a summary")
            ] = False,
            created_by: Annotated[
                list[str] | None,
                Query(
                    description="For an admin: the users it is recorded as made by, "
                    "instead of the admin (repeat for several)"
                ),
            ] = None,
            toolchain: Annotated[
                str | None,
                Query(description="For an admin: the toolchain that made it"),
            ] = None,
            toolchain_version: Annotated[
                str | None, Query(description="The version of the toolchain")
            ] = None,
            toolchain_date: Annotated[
                datetime.date | None, Query(description="The date of the toolchain")
            ] = None,
        ):
            if protection.read_only:
                refuse_if_protected(changed_fields(model, body, None))
            creators = named_creators(
                user, created_by, toolchain, toolchain_version, toolchain_date
            )
            with writing_as(creators), noting_resolved() as resolved:
                created = await called(body.save(detail=detail))  # type: ignore[attr-defined]
            response.headers["ETag"] = etag(1)
            say_resolved(response, resolved)
            return created

    if creatable and is_entity and companions_of(model):
        add_with_companions_route(
            router, model, protection.read_only if protection else ()
        )

    if writable:

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

        @router.get(
            f"{item}/deletable",
            response_model=Deletable,
            dependencies=logged_in,
            operation_id=f"deletable_{name}",
        )
        async def deletable_item(id: ChangeId):  # type: ignore[valid-type]
            """Whether a delete would go through, and if not why (to ask before deleting). Nothing is changed: an
            entity that is referred to is not marked for deletion, as a delete would mark it"""
            if protection.delete_only_if:
                found = await called(model.get(id))  # type: ignore[arg-type]
                if found is not None and not getattr(
                    found, protection.delete_only_if, False
                ):
                    return Deletable(
                        deletable=False,
                        reason="This is kept in step with something outside Pangloss, so it cannot be deleted "
                        f"here until '{protection.delete_only_if}' is true.",
                    )
            if protection.delete_refused:
                reason = await called(protection.delete_refused(model, id))
                if reason:
                    return Deletable(deletable=False, reason=reason)
            check = await called(storage_of().operations.check_deletable(model, id))
            return Deletable(
                deletable=check.deletable,
                reason=check.reason,
                referenced_by=[
                    {key: str(value) for key, value in reference.items()}
                    for reference in check.referenced_by
                ],
                reference_count=check.reference_count,
            )

    if is_entity:

        @router.get(
            f"{item}/incoming/{{field}}",
            response_model=IncomingPage,
            operation_id=f"incoming_{name}",
        )
        async def incoming_of_item(
            id: ChangeId,  # type: ignore[valid-type]
            field: Annotated[
                str,
                Path(
                    description="An incoming field of the entity's view: `givenToReverse`"
                ),
            ],
            page: Annotated[int, Query(ge=1)] = 1,
            page_size: Annotated[
                int, Query(ge=1, le=MAX_PAGE_SIZE)
            ] = DEFAULT_INCOMING_PAGE,
        ):
            """What refers to the entity by one relation, a page at a time, by the label of what refers: the items
            as they are in that field of the entity's view, and how many there are (`count`). For an entity that
            many documents refer to, read with `?incoming_limit=`"""
            try:
                found = await called(
                    storage_of().operations.get_incoming(
                        model, id, field, skip=(page - 1) * page_size, limit=page_size
                    )
                )
            except PanglossReferenceError as error:
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND, detail=str(error)
                ) from error
            if found is None:
                raise not_found(model, id)
            annotation = found.model.HeadView.model_fields[found.field].annotation
            return JSONResponse(
                {
                    "field": to_camel(found.field),
                    "count": found.count,
                    "page": page,
                    "pageSize": page_size,
                    "results": TypeAdapter(annotation).dump_python(
                        found.items, mode="json", by_alias=True
                    ),
                }
            )

    if is_entity:

        @router.get(
            f"{item}/incoming",
            response_model=IncomingFields,
            operation_id=f"incoming_fields_{name}",
        )
        async def incoming_of_item_by_field(
            id: ChangeId,  # type: ignore[valid-type]
            limit: Annotated[
                int, Query(ge=1, le=MAX_PAGE_SIZE)
            ] = DEFAULT_INCOMING_PAGE,
        ):
            """What refers to the entity, in every incoming field at once: no more than `limit` of each (the first
            by label), as they are in that field of the entity's view, and how many there are in each (`counts`).
            The other half of `GET /api/NAME/{id}?incoming_limit=0`, for a page that reads the entity first and
            what refers to it apart; `GET .../incoming/{field}` reads the rest of a field a page at a time"""
            found = await called(
                storage_of().operations.get_incoming_fields(model, id, limit)
            )
            if found is None:
                raise not_found(model, id)
            views = found.model.HeadView.model_fields
            return JSONResponse(
                {
                    "limit": limit,
                    "counts": {
                        to_camel(field): count
                        for field, count in sorted(found.counts.items())
                    },
                    "fields": {
                        to_camel(field): TypeAdapter(
                            views[field].annotation
                        ).dump_python(items, mode="json", by_alias=True)
                        for field, items in sorted(found.fields.items())
                    },
                }
            )

    if is_entity:
        add_merge_routes(router, model, item, ChangeId)  # type: ignore[arg-type]

    @router.get(item, response_model=get_response, operation_id=f"get_{name}")
    async def get_item(
        id: ItemId,  # type: ignore[valid-type]
        response: Response,
        incoming_limit: Annotated[
            int | None,
            Query(
                ge=0,
                le=MAX_PAGE_SIZE,
                description="For an entity: no more than this many of what refers to it in each incoming "
                "field (the first by label), with how many there are in each as `incomingCounts`; 0 reads "
                "none of it (`incomingCounts` is null: `GET .../incoming` reads it apart)",
            ),
        ] = None,
        extras: Annotated[
            bool,
            Query(
                description="Whether the view has what installed apps add to it (`_derived`): false leaves "
                "them out, for a reader that asks the apps itself"
            ),
        ] = True,
    ):
        """The item, as the class it is: for a class that has subclasses, the view of the subclass (its
        `type` says which; `Content-Location` is where it is edited). An entity that was merged into another gives
        that one (`meta.mergedFrom` has the id asked for, and `Content-Location` is the other's).

        An entity has everything that refers to it, in its incoming fields. For one that thousands of documents
        refer to, `incoming_limit` cuts each field, and `GET .../incoming/{field}` reads the rest a page at a time;
        `incoming_limit=0` leaves them all to `GET .../incoming`."""
        found_extras: dict[str, Any] = {}
        if is_entity and incoming_limit == 0:
            found = await called(
                storage_of().operations.get_entity_without_incoming(model, id)
            )
            # (null: not read, as against read whole (no key) or cut (the counts))
            found_extras["incomingCounts"] = None
        elif is_entity and incoming_limit is not None:
            read = await called(
                storage_of().operations.get_entity_with_some(model, id, incoming_limit)
            )
            found = read[0] if read is not None else None
            if read is not None:
                # (every field that has something, so that a reader can tell which it has all of)
                found_extras["incomingCounts"] = {
                    to_camel(field): count for field, count in sorted(read[1].items())
                }
        else:
            found = await called(model.get(id))  # type: ignore[arg-type]
        if found is None:
            raise not_found(model, id)
        # (where it is: another class's route for an item of a subclass, another entity's for one that was merged)
        if found.type != name or (isinstance(id, UUID) and found.id != id):
            response.headers["Content-Location"] = f"/api/{found.type}/{found.id}"
        if extras:
            for extra in hooks.head_view_extras:
                found_extras.update(await extra(found._owner, found))
        # (an entity merged into one of a wider class is given as that class, which is not one of this route's)
        if found_extras or found.type not in own_types:
            return with_extras(found, found_extras, response)
        return found

    if writable:

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
            with noting_resolved() as resolved:
                updated = await called(
                    body.save(detail=detail, expected_version=based_on)  # type: ignore[attr-defined]
                )
            say_resolved(response, resolved)
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
            responses={
                409: {
                    "description": "An entity that is referred to (it is marked for deletion), or one that the "
                    "rule of its package refuses to delete (nothing is changed)"
                }
            },
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
            if protection.delete_refused:
                # (the rule of the package the model is of: refused, and nothing marked)
                reason = await called(protection.delete_refused(model, id))
                if reason:
                    raise HTTPException(status.HTTP_409_CONFLICT, detail=reason)
            await called(model.delete(id))  # type: ignore[arg-type]
            return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
