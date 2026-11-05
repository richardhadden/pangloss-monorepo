"""`/api/references`: which of some entities are still there, and what they are called now.

    POST /api/references
    {"ids": ["0190…", "0190…"]}

The answer is the entities with those ids that are not deleted, each with its type and label as they are now, in the
order asked for; an id that is not a (living) entity's is left out. For what holds references to entities by a copy
of their label, made some time ago (a stashed form in the interface): one request for them all. Reading is open to
everyone, as for autocomplete.
"""

from uuid import UUID

from fastapi import APIRouter
from pangloss_models.autocomplete import AutocompleteItem
from pangloss_models.model_bases.base_models import _BaseObject
from pangloss_models import Entity
from pydantic import Field

from pangloss_api.routes.models import called

# The most ids one request may ask about
MAX_REFERENCES = 1000

router = APIRouter(prefix="/api/references", tags=["references"])


class ReferencesRequest(_BaseObject):
    ids: list[UUID] = Field(max_length=MAX_REFERENCES)


class ReferencesFound(_BaseObject):
    found: list[AutocompleteItem]


@router.post("", response_model=ReferencesFound, operation_id="references")
async def references(request: ReferencesRequest):
    return ReferencesFound(
        found=await called(Entity.references(request.ids))  # type: ignore
    )
