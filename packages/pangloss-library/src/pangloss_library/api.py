"""`/api/identity`: reading through claims of identity (`pangloss_library.clusters`).

    GET /api/identity/{id}/cluster               the cluster of an entity: those it is said to be the same as, those
                                                 they are said to be the same as, and so on; the claims that join
                                                 them; what to warn of
    GET /api/identity/{id}/cluster?steps=one     only what a statement says of the entity itself

Reading is open, and sees what the reader sees: a claim in a deleted document, or in one not published for a reader
who is not logged in, joins nothing.
"""

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException

from pangloss_library.clusters import NoSuchEntity, cluster

router = APIRouter(prefix="/api/identity", tags=["identity"])


@router.get("/{id}/cluster", operation_id="identity_cluster")
async def get_cluster(id: UUID, steps: Literal["all", "one"] = "all") -> dict[str, Any]:
    """The entities joined to this one by statements that say two entities are the same"""
    try:
        found = await cluster(id, steps)
    except NoSuchEntity as error:
        raise HTTPException(status_code=404, detail=str(error)) from None
    return found.to_wire()
