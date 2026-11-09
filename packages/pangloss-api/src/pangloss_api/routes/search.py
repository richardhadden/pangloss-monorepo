"""`/api/search`: finding head documents or entities by a pattern (see docs/structured-search.md).

    POST /api/search
    {"type": "Letter", "where": {"date": {"gt": "1500-01-01"}}, "page": 1, "page_size": 25}

The answer is a page of reference views, as for the lists of a model. Reading is open to everyone, as for
the lists. A pattern that cannot be made (a field the type does not have, an operator that does not fit its
field, a value of the wrong type) is a 422 that says which.

    POST /api/search/types
    {"type": "Factoid", "field": "statements", "where": {...}}

The types that a relation of the nodes found points at, through wrappers, each with how many of the nodes point at
one: `{"types": {"Transfer": 12, "Meeting": 3}}`. The search form offers only those. `"parts": true` is of any node
of the type, parts of documents too (what a relation of a search points at), as a nested pattern is.
"""

from fastapi import APIRouter, HTTPException, status
from pangloss_models import Match, PanglossSearchError, PanglossUnknownTypeError
from pangloss_core import storage_of
from pangloss_models.search import (
    FieldTypesRequest,
    SearchRequest,
    resolve_search_type,
)

from pangloss_api.routes.models import called

router = APIRouter(prefix="/api/search", tags=["search"])


@router.post("", operation_id="search", response_model=None)
async def search(request: SearchRequest):
    if request.type is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "The type to search is needed"
        )
    try:
        model = resolve_search_type(request.type)
        return await called(
            model.search(  # type: ignore
                Match(
                    type=request.type,
                    where=request.where,
                    order_by=request.order_by,
                ),
                page_number=request.page,
                page_size=request.page_size,
                used_only=request.used_only,
                use_counts=request.use_counts,
            )
        )
    except (PanglossUnknownTypeError, PanglossSearchError) as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)
        ) from error


@router.post("/types", operation_id="search_field_types", response_model=None)
async def field_types(request: FieldTypesRequest):
    try:
        model = resolve_search_type(request.type, parts=True)
        types = await called(
            storage_of().operations.field_types(
                model, request.field, request.where, request.parts
            )
        )
    except (PanglossUnknownTypeError, PanglossSearchError) as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)
        ) from error
    return {"types": types}
