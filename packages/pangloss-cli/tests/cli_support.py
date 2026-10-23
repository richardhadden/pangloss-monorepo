import textwrap
from pathlib import Path

PACKAGES = ("fakedb", "fakeapp", "brokenapp", "plainapp", "myproject")


def write(root: Path, name: str, content: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content))


FAKE_DB_SETUP = """
    CALLS = []

    def create_database(settings):
        CALLS.append("create_database")

    async def connect():
        CALLS.append("connect")

    async def disconnect():
        CALLS.append("disconnect")

    async def setup_database():
        CALLS.append("setup_database")
        return ["created: something"]
"""

FAKE_DB_EXPOSED = """
    from pangloss_users.exceptions import (
        PanglossUserDoesNotExistError,
        PanglossUserExistsError,
    )

    USERS = {}

    # (what `initialise()` binds to the models)
    def _unused(*args, **kwargs):
        pass

    get_document = get_entity = get_entity_for_edit = _unused
    delete_document = delete_entity = _unused
    undelete_document = undelete_entity = list_items = _unused
    create_head_node = update_head_node = _unused

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
        USERS[username] = USERS[username].model_copy(update=changes)
        return USERS[username]

    TOKENS = {}

    async def create_access_token_in_db(record):
        TOKENS[record.id] = record

    async def list_access_tokens_in_db(username):
        return [t for t in TOKENS.values() if t.username == username]

    async def delete_access_token_in_db(username, id):
        record = TOKENS.get(id)
        if record is None or record.username != username:
            return False
        del TOKENS[id]
        return True
"""

SETTINGS = """
    from pangloss_core.settings import BaseSettings, DatabaseSettings
    from pydantic import AnyHttpUrl

    class Settings(BaseSettings[DatabaseSettings]):
        PROJECT_NAME: str = "Test"
        BACKEND_CORS_ORIGINS: list = []
        INSTALLED_APPS: list[str] = {apps}
        DATABASE_MODULE: str = "{database}"
        DATABASE: DatabaseSettings = DatabaseSettings()
        INTERFACE_LANGUAGES: list[str] = []
        AUTHJWT_SECRET_KEY: str = "secret"
        ENTITY_BASE_URL: AnyHttpUrl = AnyHttpUrl("http://test.com/")

    Settings()
"""
