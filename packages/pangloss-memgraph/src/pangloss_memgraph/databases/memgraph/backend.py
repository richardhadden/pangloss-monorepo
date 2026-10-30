"""What the packages that write their own queries (typology, calendar) take from this backend: see `pangloss_core.backend`"""

from pangloss_memgraph.databases.memgraph.database import (
    Database,
    Transaction,
    timeout_from_setting,
)
from pangloss_memgraph.databases.memgraph.visibility import unpublished_visible

__all__ = [
    "Database",
    "Transaction",
    "timeout_from_setting",
    "unpublished_visible",
    "user_exists",
]


async def user_exists(username: str) -> bool:
    database = Database.default
    async with database.driver.session(
        database=database.settings.DATABASE.DATABASE_NAME
    ) as session:
        result = await session.run(
            "MATCH (u:PGUser {username: $username}) RETURN u LIMIT 1",
            username=username,
        )
        return await result.single() is not None
