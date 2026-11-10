"""`/api/search-everything`: what the box of the homepage asks.

    GET /api/search-everything?q=smi&type=Person&page_size=25

Head documents and entities of any class, except those with `global_search=False`, whose label has every word of `q`,
the most connected first. `type` (repeat for more) narrows it to classes and their subclasses, including what is inside documents. Without words the most connected of
`type` are listed, and without a `type` too nothing is found. Reading is open to everyone, as for the lists. See implementation_docs/homepage-and-pages.md.
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pangloss_models import PanglossSearchError, PanglossUnknownTypeError
from pangloss_models.autocomplete import AutocompleteResults, search_everything
from pangloss_models.search import resolve_search_type

from pangloss_api.routes.models import called

MAX_PAGE_SIZE = 50

router = APIRouter(prefix="/api/search-everything", tags=["search"])


@router.get("", response_model=AutocompleteResults, operation_id="search_everything")
async def search_everything_route(
    q: Annotated[str, Query(description="The words of the label")] = "",
    type: Annotated[
        list[str] | None,
        Query(description="A class to narrow it to; repeat for several"),
    ] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 25,
):
    try:
        types = [resolve_search_type(name, parts=True) for name in type or []]
    except (PanglossUnknownTypeError, PanglossSearchError) as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)
        ) from error
    return await called(
        search_everything(q, types or None, page_number=page, page_size=page_size)
    )
