"""A backend that keeps users in memory"""

from pangloss_users.exceptions import (
    PanglossUserDoesNotExistError,
    PanglossUserExistsError,
)

USERS: dict = {}


async def create_user_in_db(user):
    if user.username in USERS or any(u.email == user.email for u in USERS.values()):
        raise PanglossUserExistsError("That username or email is already in use")
    USERS[user.username] = user


async def get_user_in_db(username):
    return USERS.get(username)


async def get_user_in_db_by_email(email):
    return next((u for u in USERS.values() if u.email == email), None)


async def list_users_in_db():
    return sorted(USERS.values(), key=lambda u: u.username)


async def update_user_in_db(username, changes):
    if username not in USERS:
        raise PanglossUserDoesNotExistError(f"There is no user '{username}'")
    email = changes.get("email")
    if email and any(
        u.email == email and u.username != username for u in USERS.values()
    ):
        raise PanglossUserExistsError("That email is already in use")
    USERS[username] = USERS[username].model_copy(update=changes)
    return USERS[username]
