"""`/api/autocomplete`: finding existing entities by their label while it is being typed.

    GET /api/autocomplete?q=smi&type=Person&type=Organisation&page=1&page_size=10

`type` (at least one, repeated for more) names entity classes, or traits that only entities have; what
is found is an entity of one of them or of a subclass. Every word of `q` has to occur in the label.
Reading is open to everyone, as for the lists. See docs/autocomplete.md.
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pangloss_models.autocomplete import AutocompleteResults, resolve_entity_types
from pangloss_models.exceptions import PanglossUnknownTypeError
from pangloss_models.model_bases.entity import Entity

from pangloss_api.routes.models import called

# The most items a page may have: it is for a list under a text field
MAX_AUTOCOMPLETE_PAGE_SIZE = 50

router = APIRouter(prefix="/api/autocomplete", tags=["autocomplete"])


@router.get("", response_model=AutocompleteResults, operation_id="autocomplete")
async def autocomplete(
    q: Annotated[str, Query(min_length=1, description="What has been typed")],
    type: Annotated[
        list[str],
        Query(
            min_length=1, description="An entity class to search; repeat for several"
        ),
    ],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_AUTOCOMPLETE_PAGE_SIZE)] = 10,
):
    try:
        types = resolve_entity_types(type)
    except PanglossUnknownTypeError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error))
    return await called(
        Entity.autocomplete(  # type: ignore
            search_terms=q, types=types, page_number=page, page_size=page_size
        )
    )
