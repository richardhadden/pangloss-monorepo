"""Looking things up inside a transaction"""

from uuid import UUID

from pydantic import AnyHttpUrl, AnyUrl

from pangloss_memgraph.databases.memgraph.database import Transaction


async def resolve_id(tx: Transaction, id: UUID | AnyHttpUrl) -> UUID | None:
    """The id of a node, given its id or one of its URLs; or None if there is none"""
    if not isinstance(id, AnyUrl):
        return id

    result = await tx.run(
        "MATCH (:PGUrl {url: $url})<-[:has_url]-(node:PGIndexableNode) RETURN node.id AS id",
        url=str(id),
    )
    found = await result.value()
    return UUID(found[0]) if found else None
