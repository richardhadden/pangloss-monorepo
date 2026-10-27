"""`/api/search`: finding head documents or entities by a pattern (see docs/structured-search.md).

    POST /api/search
    {"type": "Letter", "where": {"date": {"gt": "1500-01-01"}}, "page": 1, "page_size": 25}

The answer is a page of reference views, as for the lists of a model. Reading is open to everyone, as for
the lists. A pattern that cannot be made (a field the type does not have, an operator that does not fit its
field, a value of the wrong type) is a 422 that says which.
"""

from fastapi import APIRouter, HTTPException, status
from pangloss_models.exceptions import PanglossSearchError, PanglossUnknownTypeError
from pangloss_models.search import Match, SearchRequest, resolve_search_type

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
                Match(type=request.type, where=request.where),
                page_number=request.page,
                page_size=request.page_size,
            )
        )
    except (PanglossUnknownTypeError, PanglossSearchError) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error))
