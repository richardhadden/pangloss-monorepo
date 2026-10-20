"""Routes for the Documents and Entities declared in the project.

For each one that is not abstract, `NAME` being its class name:

| | | |
|-|-|-|
| `GET`    | `/api/{documents,entities}/NAME`              | list (`q`, `deep`, `page`, `page_size`) |
| `GET`    | `/api/{documents,entities}/NAME/{id}`         | the `HeadView` |
| `POST`   | `/api/{documents,entities}/NAME`              | create (`Create`); login required |
| `GET`    | `/api/{documents,entities}/NAME/{id}/edit`    | to edit: an entity's `EditView`, a document's `HeadView`; login required |
| `PUT`    | `/api/{documents,entities}/NAME/{id}`         | update (`Update`); login required |
| `DELETE` | `/api/{documents,entities}/NAME/{id}`         | delete; login required |
| `POST`   | `/api/{documents,entities}/NAME/{id}/undelete`| undelete; login required |

Reading is open to everyone. The functions they call are those bound to the models
by the database backend (`Model.get`, `Model.list`, `Model.Create(...).save()` ...).
"""

import inspect
from typing import Annotated, Any, Union
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from pangloss_models.model_bases.base_models import _ListItems
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_registry import ModelRegistry
from pangloss_models.utils import get_concrete_types

from pangloss_api.dependencies import get_current_user

KINDS = {Document: "documents", Entity: "entities"}

# The most items a page of a list may have
MAX_PAGE_SIZE = 500

logged_in = [Depends(get_current_user)]


def routable_models() -> list[type[Document] | type[Entity]]:
    """The registered Documents and Entities that routes are made for"""
    return [
        model
        for model in ModelRegistry.all_models().values()
        if isinstance(model, type)
        and issubclass(model, (Document, Entity))
        and not getattr(model._meta, "abstract", False)
        and hasattr(model, "HeadView")
    ]


def kind_of(model: type[Document] | type[Entity]) -> str:
    return KINDS[Entity if issubclass(model, Entity) else Document]


async def called(value: Any) -> Any:
    """The result of a database function, which may or may not be async"""
    return await value if inspect.isawaitable(value) else value


def not_found(model: type, id: UUID) -> HTTPException:
    return HTTPException(
        status.HTTP_404_NOT_FOUND, detail=f"There is no {model.__name__} with id {id}"
    )


def list_response_model(model: type[Document] | type[Entity]) -> Any:
    reference_views = [t.ReferenceView for t in get_concrete_types(model)]  # type: ignore[attr-defined]
    return _ListItems[Union[*reference_views]]  # type: ignore[valid-type]


def build_router(model: type[Document] | type[Entity]) -> APIRouter:
    is_entity = issubclass(model, Entity)
    name = model.__name__

    router = APIRouter(
        prefix=f"/api/{kind_of(model)}/{name}", tags=[f"{kind_of(model)}: {name}"]
    )

    head_view = model.HeadView
    reference_view = model.ReferenceView
    create_model = model.Create
    update_model = model.Update
    edit_response = model.EditView if is_entity else head_view  # type: ignore[attr-defined]

    @router.get("", response_model=list_response_model(model), operation_id=f"list_{name}")
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

    @router.get("/{id}", response_model=head_view, operation_id=f"get_{name}")
    async def get_item(id: UUID):
        item = await called(model.get(id))  # type: ignore[arg-type]
        if item is None:
            raise not_found(model, id)
        return item

    @router.post(
        "",
        status_code=status.HTTP_201_CREATED,
        response_model=Union[reference_view, head_view],  # type: ignore[valid-type]
        dependencies=logged_in,
        operation_id=f"create_{name}",
    )
    async def create_item(
        body: Annotated[create_model, Body()],  # type: ignore[valid-type]
        detail: Annotated[
            bool, Query(description="Return the whole HeadView, not a summary")
        ] = False,
    ):
        return await called(body.save(detail=detail))  # type: ignore[attr-defined]

    @router.get(
        "/{id}/edit",
        response_model=edit_response,
        dependencies=logged_in,
        operation_id=f"edit_{name}",
    )
    async def edit_item(id: UUID):
        read = model.get_for_edit if is_entity else model.get  # type: ignore[attr-defined]
        item = await called(read(id))
        if item is None:
            raise not_found(model, id)
        return item

    @router.put(
        "/{id}",
        response_model=Union[reference_view, head_view],  # type: ignore[valid-type]
        dependencies=logged_in,
        operation_id=f"update_{name}",
    )
    async def update_item(
        id: UUID,
        body: Annotated[update_model, Body()],  # type: ignore[valid-type]
        detail: Annotated[
            bool, Query(description="Return the whole HeadView, not a summary")
        ] = False,
    ):
        if body.id != id:  # type: ignore[attr-defined]
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="The id in the body is not the id in the path",
            )
        return await called(body.save(detail=detail))  # type: ignore[attr-defined]

    @router.delete(
        "/{id}",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=logged_in,
        operation_id=f"delete_{name}",
        responses={409: {"description": "An entity that is referred to"}},
    )
    async def delete_item(id: UUID):
        await called(model.delete(id))  # type: ignore[arg-type]
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.post(
        "/{id}/undelete",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=logged_in,
        operation_id=f"undelete_{name}",
    )
    async def undelete_item(id: UUID):
        await called(model.undelete(id))  # type: ignore[attr-defined]
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
