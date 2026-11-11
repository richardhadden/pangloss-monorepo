"""Checks made inside a write transaction"""

from pangloss_models import (
    PanglossUserDisabledError,
    PanglossUserNotFoundError,
    PanglossWriteRefused,
)
from pangloss_models.creators import requested_creators
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


async def check_creators_exist(tx: Transaction) -> None:
    """Those a write names as the creators (`pangloss_models.creators`) are users, and each is of the kind it is named
    as: a toolchain is not named as a person, nor a person as a toolchain"""
    asked = requested_creators.get()
    if asked is None:
        return
    result = await tx.run(
        """
        UNWIND $usernames AS username
        MATCH (user:PGUser {username: username})
        RETURN user.username AS username, coalesce(user.kind, 'user') AS kind
        """,
        usernames=[creator.username for creator in asked],
    )
    kinds = {username: kind for username, kind in await result.values()}
    for creator in asked:
        if creator.username not in kinds:
            raise PanglossWriteRefused(
                f"There is no user '{creator.username}' to name as a creator",
                field="created_by",
            )
        if kinds[creator.username] != creator.kind:
            raise PanglossWriteRefused(
                f"'{creator.username}' is a {kinds[creator.username]}, and cannot be named as a {creator.kind}",
                field="created_by",
            )
