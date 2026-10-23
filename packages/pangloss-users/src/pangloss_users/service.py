"""Creating, finding and changing users, and checking their passwords.

The users are kept by the database backend (`DATABASE_MODULE`), which supplies, in its
`exposed_functions`:

- `create_user_in_db(user: UserInDB) -> None`, raising `PanglossUserExistsError` if
  the username or email is taken
- `get_user_in_db(username) -> UserInDB | None`
- `get_user_in_db_by_email(email) -> UserInDB | None`
- `update_user_in_db(username, changes: dict) -> UserInDB`, raising
  `PanglossUserDoesNotExistError` or `PanglossUserExistsError`
- `list_users_in_db() -> list[UserInDB]`

Everything returned from here is a `User`, which has no password or hash.
"""

import datetime
import hashlib
import importlib
import secrets
import uuid
from types import ModuleType
from typing import Any

from pangloss_core import settings as core_settings
from pydantic import ValidationError

from pangloss_users.exceptions import (
    PanglossInvalidUserError,
    PanglossUserDoesNotExistError,
)
from pangloss_users.models import (
    AccessTokenInfo,
    TOKEN_SCOPES,
    AccessTokenRecord,
    User,
    UserCreate,
    UserInDB,
    UserUpdate,
)
from pangloss_users.passwords import (
    hash_password,
    password_needs_rehash,
    verify_password,
)


def _backend() -> ModuleType:
    database = core_settings.SETTINGS.DATABASE_MODULE
    return importlib.import_module(f"{database}.exposed_functions")


def _public(user: UserInDB) -> User:
    return User.model_validate(
        {
            **user.model_dump(exclude={"hashed_password"}),
            "token_generation": user.token_generation,
        }
    )


async def create_user(
    username: str,
    email: str,
    password: str,
    full_name: str | None = None,
    admin: bool = False,
) -> User:
    """Create a user. Raises `PanglossInvalidUserError` for an unacceptable username,
    email or password, and `PanglossUserExistsError` if the username or email is
    taken."""
    try:
        details = UserCreate(
            username=username, email=email, password=password, full_name=full_name
        )
    except ValidationError as error:
        raise PanglossInvalidUserError(str(error)) from error

    user = UserInDB(
        username=details.username,
        email=details.email,
        full_name=details.full_name,
        admin=admin,
        created_when=datetime.datetime.now(datetime.UTC),
        hashed_password=hash_password(details.password),
    )
    await _backend().create_user_in_db(user)
    return _public(user)


async def get_user(username: str) -> User | None:
    user = await _backend().get_user_in_db(username)
    return _public(user) if user else None


async def get_user_by_email(email: str) -> User | None:
    user = await _backend().get_user_in_db_by_email(email)
    return _public(user) if user else None


async def list_users() -> list[User]:
    return [_public(user) for user in await _backend().list_users_in_db()]


async def authenticate(username: str, password: str) -> User | None:
    """The user, if the username and password are right and the user is not disabled;
    otherwise None (without saying which of these was wrong)"""
    backend = _backend()
    user: UserInDB | None = await backend.get_user_in_db(username)

    # (a password is checked even if there is no user, so that it takes as long)
    if not verify_password(password, user.hashed_password if user else None):
        return None
    assert user is not None and user.hashed_password is not None
    if user.disabled:
        return None

    # Keep the hash up to date with the parameters now in use
    if password_needs_rehash(user.hashed_password):
        await backend.update_user_in_db(
            username, {"hashed_password": hash_password(password)}
        )

    return _public(user)


async def _update(username: str, changes: dict[str, Any]) -> User:
    return _public(await _backend().update_user_in_db(username, changes))


async def update_user(username: str, update: UserUpdate) -> User:
    """Change a user's email and/or full name (whatever is set on `update`)"""
    changes = update.model_dump(exclude_unset=True)
    if not changes:
        user = await get_user(username)
        if user is None:
            raise PanglossUserDoesNotExistError(f"There is no user '{username}'")
        return user
    return await _update(username, changes)


async def set_password(username: str, password: str) -> User:
    """Set a password. This ends the user's sessions: tokens made before are no longer good"""
    current = await get_user(username)
    if current is None:
        raise PanglossUserDoesNotExistError(f"There is no user '{username}'")
    return await _update(
        username,
        {
            "hashed_password": hash_password(password),
            "token_generation": current.token_generation + 1,
        },
    )


async def end_sessions(username: str) -> User:
    """Log the user out everywhere: every token made until now stops working"""
    current = await get_user(username)
    if current is None:
        raise PanglossUserDoesNotExistError(f"There is no user '{username}'")
    return await _update(username, {"token_generation": current.token_generation + 1})


async def change_password(username: str, old_password: str, new_password: str) -> User:
    """Change a password, given the old one. Raises `PanglossInvalidUserError` if the
    old one is wrong."""
    if await authenticate(username, old_password) is None:
        raise PanglossInvalidUserError("The password is wrong")
    return await set_password(username, new_password)


async def set_admin(username: str, admin: bool) -> User:
    return await _update(username, {"admin": admin})


async def set_disabled(username: str, disabled: bool) -> User:
    """Disable a user, who can then neither log in nor write; or enable them again.
    Nothing they wrote is affected."""
    return await _update(username, {"disabled": disabled})


# ---------------------------------------------------------------------------
# Revoking a session's token, and personal access tokens
#
# The backend's `exposed_functions` also supply (a backend without them cannot revoke or
# keep access tokens: `is_session_revoked` is then always False):
#
# - `revoke_session_in_db(jti, expires)`, and `is_session_revoked_in_db(jti) -> bool`
# - `create_access_token_in_db(record: AccessTokenRecord)`
# - `get_access_token_in_db_by_hash(token_hash) -> AccessTokenRecord | None`
# - `list_access_tokens_in_db(username) -> list[AccessTokenRecord]`
# - `delete_access_token_in_db(username, id) -> bool`
# ---------------------------------------------------------------------------

ACCESS_TOKEN_PREFIX = "pgl_"


async def revoke_session(jti: str, expires: datetime.datetime) -> None:
    """A token (by its `jti`) stops working, until it would have expired anyway"""
    function = getattr(_backend(), "revoke_session_in_db", None)
    if function is not None:
        await function(jti, expires)


async def is_session_revoked(jti: str) -> bool:
    function = getattr(_backend(), "is_session_revoked_in_db", None)
    return bool(await function(jti)) if function is not None else False


def hash_access_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def create_access_token(
    username: str,
    name: str,
    scope: str = "write",
    expires_days: int | None = None,
) -> tuple[AccessTokenInfo, str]:
    """Make a personal access token for a user: a long-lived, named, revocable token, for
    scripts and for `git`. Returns what can be shown of it, and **the token, which is not
    kept and cannot be found again**."""
    if scope not in TOKEN_SCOPES:
        raise PanglossInvalidUserError(f"The scope of a token is one of {TOKEN_SCOPES}")
    if not name.strip():
        raise PanglossInvalidUserError("A token needs a name")
    if await get_user(username) is None:
        raise PanglossUserDoesNotExistError(f"There is no user '{username}'")

    token = ACCESS_TOKEN_PREFIX + secrets.token_urlsafe(32)
    now = datetime.datetime.now(datetime.UTC)
    record = AccessTokenRecord(
        id=uuid.uuid4().hex,
        name=name.strip(),
        scope=scope,
        created_when=now,
        expires_when=now + datetime.timedelta(days=expires_days) if expires_days else None,
        username=username,
        token_hash=hash_access_token(token),
    )
    await _backend().create_access_token_in_db(record)
    return AccessTokenInfo.model_validate(record.model_dump()), token


async def list_access_tokens(username: str) -> list[AccessTokenInfo]:
    records = await _backend().list_access_tokens_in_db(username)
    return [AccessTokenInfo.model_validate(r.model_dump()) for r in records]


async def revoke_access_token(username: str, id: str) -> bool:
    """Delete one of the user's tokens: False if they have none with that id"""
    return bool(await _backend().delete_access_token_in_db(username, id))


async def authenticate_access_token(token: str) -> tuple[User, str] | None:
    """The user (and the scope of the token) for a personal access token; None if it is
    not one, has been revoked or has expired, or its user is disabled"""
    if not token.startswith(ACCESS_TOKEN_PREFIX):
        return None
    function = getattr(_backend(), "get_access_token_in_db_by_hash", None)
    if function is None:
        return None
    record = await function(hash_access_token(token))
    if record is None:
        return None
    if record.expires_when is not None and record.expires_when <= datetime.datetime.now(
        datetime.UTC
    ):
        return None
    user = await get_user(record.username)
    if user is None or user.disabled:
        return None
    return user, record.scope
