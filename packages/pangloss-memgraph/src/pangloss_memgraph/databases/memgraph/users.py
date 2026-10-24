"""Storing users (`PGUser` nodes).

A user is a node with the properties of `UserInDB` that are set: `username`,
`email`, `full_name`, `admin`, `disabled`, `created_when` and `hashed_password`.
`username` and `email` are unique. Users made by hand (as the tests do, with just
a `username`) are read with the other properties unset.
"""

import datetime
from typing import Any

from neo4j.exceptions import ConstraintError
from pangloss_users.exceptions import (
    PanglossUserDoesNotExistError,
    PanglossUserExistsError,
)
from pangloss_users.models import AccessTokenRecord, UserInDB

from pangloss_memgraph.databases.memgraph.database import Transaction

# What `update_user` can change
UPDATABLE_PROPERTIES = frozenset(
    {"email", "full_name", "admin", "disabled", "hashed_password", "token_generation"}
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


# ---------------------------------------------------------------------------
# Revoked tokens (`PGRevokedSession`) and personal access tokens (`PGAccessToken`)
# ---------------------------------------------------------------------------


async def revoke_session(tx: Transaction, jti: str, expires: datetime.datetime) -> None:
    # (one that would have expired anyway need not be kept)
    await (
        await tx.run(
            "MATCH (revoked:PGRevokedSession) WHERE revoked.expires < $now DELETE revoked",
            now=datetime.datetime.now(datetime.UTC),
        )
    ).consume()
    await (
        await tx.run(
            "MERGE (revoked:PGRevokedSession {jti: $jti}) SET revoked.expires = $expires",
            jti=jti,
            expires=expires,
        )
    ).consume()


async def is_session_revoked(tx: Transaction, jti: str) -> bool:
    result = await tx.run(
        "MATCH (revoked:PGRevokedSession {jti: $jti}) RETURN count(revoked) AS count",
        jti=jti,
    )
    record = await result.single()
    return bool(record and record["count"])


def token_from_node(node: Any) -> AccessTokenRecord:
    properties = {
        key: value.to_native() if hasattr(value, "to_native") else value
        for key, value in dict(node).items()
    }
    return AccessTokenRecord(**properties)


async def create_access_token(tx: Transaction, record: AccessTokenRecord) -> None:
    await (
        await tx.run(
            "CREATE (token:PGAccessToken) SET token = $token",
            token=record.model_dump(exclude_none=True),
        )
    ).consume()


async def get_access_token_by_hash(
    tx: Transaction, token_hash: str
) -> AccessTokenRecord | None:
    result = await tx.run(
        "MATCH (token:PGAccessToken {token_hash: $token_hash}) RETURN token",
        token_hash=token_hash,
    )
    record = await result.single()
    return token_from_node(record["token"]) if record else None


async def list_access_tokens(tx: Transaction, username: str) -> list[AccessTokenRecord]:
    result = await tx.run(
        "MATCH (token:PGAccessToken {username: $username}) RETURN token "
        "ORDER BY token.created_when",
        username=username,
    )
    return [token_from_node(node) for node in await result.value()]


async def touch_access_token(tx: Transaction, id: str, when: datetime.datetime) -> None:
    await (
        await tx.run(
            "MATCH (token:PGAccessToken {id: $id}) SET token.last_used_when = $when",
            id=id,
            when=when,
        )
    ).consume()


async def delete_access_token(tx: Transaction, username: str, id: str) -> bool:
    result = await tx.run(
        "MATCH (token:PGAccessToken {username: $username, id: $id}) "
        "DELETE token RETURN count(*) AS deleted",
        username=username,
        id=id,
    )
    record = await result.single()
    return bool(record and record["deleted"])
