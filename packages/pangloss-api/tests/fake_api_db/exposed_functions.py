"""A backend that keeps users in memory"""

from pangloss_users.exceptions import (
    PanglossUserDoesNotExistError,
    PanglossUserExistsError,
)

USERS: dict = {}


# (what `initialise()` binds to the models; tests replace the ones they use)
def _unused(*args, **kwargs):
    raise NotImplementedError


get_document = get_entity = get_entity_for_edit = _unused
delete_document = delete_entity = undelete_document = undelete_entity = _unused
list_items = create_head_node = update_head_node = _unused


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


REVOKED: dict = {}
ACCESS_TOKENS: dict = {}


async def revoke_session_in_db(jti, expires):
    REVOKED[jti] = expires


async def is_session_revoked_in_db(jti):
    return jti in REVOKED


async def create_access_token_in_db(record):
    ACCESS_TOKENS[record.id] = record


async def get_access_token_in_db_by_hash(token_hash):
    return next((r for r in ACCESS_TOKENS.values() if r.token_hash == token_hash), None)


async def list_access_tokens_in_db(username):
    return sorted(
        (r for r in ACCESS_TOKENS.values() if r.username == username),
        key=lambda r: r.created_when,
    )


async def delete_access_token_in_db(username, id):
    record = ACCESS_TOKENS.get(id)
    if record is None or record.username != username:
        return False
    del ACCESS_TOKENS[id]
    return True


async def touch_access_token_in_db(id, when):
    ACCESS_TOKENS[id] = ACCESS_TOKENS[id].model_copy(update={"last_used_when": when})
