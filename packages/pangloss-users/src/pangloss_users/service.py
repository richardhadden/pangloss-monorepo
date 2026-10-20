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
import importlib
from types import ModuleType
from typing import Any

from pangloss_core import settings as core_settings
from pydantic import ValidationError

from pangloss_users.exceptions import (
    PanglossInvalidUserError,
    PanglossUserDoesNotExistError,
)
from pangloss_users.models import User, UserCreate, UserInDB, UserUpdate
from pangloss_users.passwords import (
    hash_password,
    password_needs_rehash,
    verify_password,
)


def _backend() -> ModuleType:
    database = core_settings.SETTINGS.DATABASE_MODULE
    return importlib.import_module(f"{database}.exposed_functions")


def _public(user: UserInDB) -> User:
    return User.model_validate(user.model_dump(exclude={"hashed_password"}))


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
    return await _update(username, {"hashed_password": hash_password(password)})


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
