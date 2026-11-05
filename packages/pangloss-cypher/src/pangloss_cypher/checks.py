"""Checks made inside a write transaction"""

from pangloss_models import PanglossUserDisabledError, PanglossUserNotFoundError
from pangloss_users import current_request_username

from pangloss_cypher.transaction import Transaction


async def check_user_exists(tx: Transaction) -> None:
    username = current_request_username.get()
    result = await tx.run(
        """
        MATCH (user:PGUser {username: $username})
        RETURN coalesce(user.disabled, false) AS disabled
        """,
        username=username,
    )
    found = await result.value()
    if not found:
        raise PanglossUserNotFoundError(f"There is no user '{username}'")
    if found[0]:
        raise PanglossUserDisabledError(f"The user '{username}' is disabled")
