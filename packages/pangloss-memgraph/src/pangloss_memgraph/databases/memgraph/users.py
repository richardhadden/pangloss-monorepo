"""Storing users (`PGUser` nodes).

A user is a node with the properties of `UserInDB` that are set: `username`,
`email`, `full_name`, `admin`, `disabled`, `created_when` and `hashed_password`.
`username` and `email` are unique. Users made by hand (as the tests do, with just
a `username`) are read with the other properties unset.
"""

from typing import Any

from neo4j.exceptions import ConstraintError
from pangloss_users.exceptions import (
    PanglossUserDoesNotExistError,
    PanglossUserExistsError,
)
from pangloss_users.models import UserInDB

from pangloss_memgraph.databases.memgraph.database import Transaction

# What `update_user` can change
UPDATABLE_PROPERTIES = frozenset(
    {"email", "full_name", "admin", "disabled", "hashed_password"}
)


def user_from_node(node: Any) -> UserInDB:
    properties = {
        key: value.to_native() if hasattr(value, "to_native") else value
        for key, value in dict(node).items()
    }
    return UserInDB(**properties)


async def user_properties_taken(
    tx: Transaction, username: str | None, email: str | None, excluding: str | None
) -> bool:
    result = await tx.run(
        """
        MATCH (user:PGUser)
        WHERE (user.username = $username OR user.email = $email)
          AND user.username <> coalesce($excluding, "")
        RETURN count(user) AS count
        """,
        username=username,
        email=email,
        excluding=excluding,
    )
    record = await result.single()
    return bool(record and record["count"])


async def create_user(tx: Transaction, user: UserInDB) -> None:
    if await user_properties_taken(tx, user.username, user.email, None):
        raise PanglossUserExistsError("That username or email is already in use")
    try:
        result = await tx.run(
            "CREATE (user:PGUser) SET user = $user",
            user=user.model_dump(exclude_none=True),
        )
        await result.consume()
    except ConstraintError as error:
        raise PanglossUserExistsError(
            "That username or email is already in use"
        ) from error


async def get_user(tx: Transaction, username: str) -> UserInDB | None:
    result = await tx.run(
        "MATCH (user:PGUser {username: $username}) RETURN user", username=username
    )
    record = await result.single()
    return user_from_node(record["user"]) if record else None


async def get_user_by_email(tx: Transaction, email: str) -> UserInDB | None:
    result = await tx.run(
        "MATCH (user:PGUser {email: $email}) RETURN user", email=email
    )
    record = await result.single()
    return user_from_node(record["user"]) if record else None


async def list_users(tx: Transaction) -> list[UserInDB]:
    result = await tx.run("MATCH (user:PGUser) RETURN user ORDER BY user.username")
    return [user_from_node(node) for node in await result.value()]


async def update_user(
    tx: Transaction, username: str, changes: dict[str, Any]
) -> UserInDB:
    unknown = set(changes) - UPDATABLE_PROPERTIES
    if unknown:
        raise ValueError(f"Cannot update user properties: {', '.join(sorted(unknown))}")

    if "email" in changes and await user_properties_taken(
        tx, None, changes["email"], username
    ):
        raise PanglossUserExistsError("That email is already in use")

    result = await tx.run(
        "MATCH (user:PGUser {username: $username}) SET user += $changes RETURN user",
        username=username,
        changes=changes,
    )
    record = await result.single()
    if record is None:
        raise PanglossUserDoesNotExistError(f"There is no user '{username}'")
    return user_from_node(record["user"])
