"""Users: creating, finding, changing, and logging in"""

import pytest
from pangloss_models import initialise
from pangloss_models.exceptions import PanglossUserDisabledError
from pangloss_models.model_bases.document import Document
from pangloss_users import current_request_username, service
from pangloss_users.exceptions import (
    PanglossInvalidUserError,
    PanglossUserDoesNotExistError,
    PanglossUserExistsError,
)
from pangloss_users.models import UserUpdate

from .helpers import run

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def make_user(username="john", email="john@example.com", **kwargs):
    return await service.create_user(
        username=username, email=email, password="correct horse", **kwargs
    )


def stored(db_driver, username) -> dict:
    return run(
        db_driver, "MATCH (u:PGUser {username: $u}) RETURN u", u=username
    )[0]["u"]


async def test_create_and_get_a_user(db_driver, clear_database):
    user = await make_user(full_name="John Smith")
    assert user.username == "john"
    assert user.email == "john@example.com"
    assert user.full_name == "John Smith"
    assert user.admin is False
    assert user.disabled is False
    assert user.created_when is not None

    assert await service.get_user("john") == user
    assert (await service.get_user_by_email("john@example.com")) == user
    assert await service.get_user("nobody") is None
    assert await service.get_user_by_email("nobody@example.com") is None

    # The password is stored only as a hash, and is never given back
    node = stored(db_driver, "john")
    assert node["hashed_password"].startswith("$argon2")
    assert "correct horse" not in str(node)
    assert "hashed_password" not in user.model_dump()


async def test_username_and_email_must_be_unique(db_driver, clear_database):
    await make_user()
    with pytest.raises(PanglossUserExistsError):
        await make_user(email="other@example.com")
    with pytest.raises(PanglossUserExistsError):
        await make_user(username="jane")


async def test_invalid_details_are_refused(db_driver, clear_database):
    with pytest.raises(PanglossInvalidUserError):
        await service.create_user("john", "not an email", "correct horse")
    with pytest.raises(PanglossInvalidUserError):
        await service.create_user("john smith", "john@example.com", "correct horse")
    with pytest.raises(PanglossInvalidUserError):
        await service.create_user("john", "john@example.com", "short")
    assert await service.get_user("john") is None


async def test_authenticate(db_driver, clear_database):
    user = await make_user()
    assert await service.authenticate("john", "correct horse") == user
    assert await service.authenticate("john", "wrong horse") is None
    assert await service.authenticate("nobody", "correct horse") is None


async def test_a_user_with_no_password_cannot_log_in(db_driver, clear_database):
    # (as the default user, made by hand, has none)
    assert await service.authenticate("pangloss_default_user", "") is None
    assert await service.authenticate("pangloss_default_user", "anything at all") is None
    user = await service.get_user("pangloss_default_user")
    assert user is not None and user.email is None


async def test_update_a_user(db_driver, clear_database):
    await make_user()
    await make_user("jane", "jane@example.com")

    updated = await service.update_user(
        "john", UserUpdate(full_name="John Smith", email="js@example.com")
    )
    assert updated.full_name == "John Smith"
    assert updated.email == "js@example.com"

    # Only what is given is changed
    updated = await service.update_user("john", UserUpdate(full_name="J. Smith"))
    assert updated.full_name == "J. Smith"
    assert updated.email == "js@example.com"
    assert (await service.update_user("john", UserUpdate())).full_name == "J. Smith"

    with pytest.raises(PanglossUserExistsError):
        await service.update_user("john", UserUpdate(email="jane@example.com"))
    with pytest.raises(PanglossUserDoesNotExistError):
        await service.update_user("nobody", UserUpdate(full_name="Nobody"))


async def test_change_password(db_driver, clear_database):
    await make_user()

    with pytest.raises(PanglossInvalidUserError):
        await service.change_password("john", "wrong horse", "a new password")
    await service.change_password("john", "correct horse", "a new password")
    assert await service.authenticate("john", "correct horse") is None
    assert await service.authenticate("john", "a new password") is not None

    with pytest.raises(PanglossInvalidUserError):
        await service.set_password("john", "short")
    await service.set_password("john", "set by an admin")
    assert await service.authenticate("john", "set by an admin") is not None
    with pytest.raises(PanglossUserDoesNotExistError):
        await service.set_password("nobody", "set by an admin")


async def test_admin_and_disabled(db_driver, clear_database):
    await make_user()

    assert (await service.set_admin("john", True)).admin is True
    assert (await service.get_user("john")).admin is True
    assert (await service.set_admin("john", False)).admin is False

    assert (await service.set_disabled("john", True)).disabled is True
    assert await service.authenticate("john", "correct horse") is None
    assert (await service.set_disabled("john", False)).disabled is False
    assert await service.authenticate("john", "correct horse") is not None

    admin = await make_user("root", "root@example.com", admin=True)
    assert admin.admin is True


async def test_list_users(db_driver, clear_database):
    await make_user("john", "john@example.com")
    await make_user("alice", "alice@example.com")
    users = await service.list_users()
    assert [u.username for u in users] == ["alice", "john", "pangloss_default_user"]


async def test_a_disabled_user_cannot_write(db_driver, clear_database):
    class Statement(Document):
        pass

    initialise()

    await make_user()
    token = current_request_username.set("john")
    try:
        await Statement.Create(label="One").save()

        await service.set_disabled("john", True)
        with pytest.raises(PanglossUserDisabledError):
            await Statement.Create(label="Two").save()

        await service.set_disabled("john", False)
        await Statement.Create(label="Three").save()
    finally:
        current_request_username.reset(token)

    # What the user wrote while enabled is still there
    labels = {
        r["label"] for r in run(db_driver, "MATCH (s:Statement) RETURN s.label AS label")
    }
    assert labels == {"One", "Three"}
