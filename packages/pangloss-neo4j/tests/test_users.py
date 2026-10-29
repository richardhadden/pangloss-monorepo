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
    return run(db_driver, "MATCH (u:PGUser {username: $u}) RETURN u", u=username)[0][
        "u"
    ]


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
    assert (
        await service.authenticate("pangloss_default_user", "anything at all") is None
    )
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
        r["label"]
        for r in run(db_driver, "MATCH (s:Statement) RETURN s.label AS label")
    }
    assert labels == {"One", "Three"}


# --- revoked sessions, sessions ended, personal access tokens ----------------------------


async def test_a_password_change_and_logout_everywhere_raise_the_token_generation(
    db_driver, clear_database
):
    user = await make_user()
    assert user.token_generation == 0

    assert (await service.set_password("john", "another horse")).token_generation == 1
    assert (await service.end_sessions("john")).token_generation == 2
    assert (await service.get_user("john")).token_generation == 2  # type: ignore[union-attr]
    assert stored(db_driver, "john")["token_generation"] == 2


async def test_a_revoked_session_is_remembered_until_it_would_have_expired(
    db_driver, clear_database
):
    import datetime

    now = datetime.datetime.now(datetime.UTC)
    assert not await service.is_session_revoked("abc")

    await service.revoke_session("abc", now + datetime.timedelta(hours=1))
    await service.revoke_session("abc", now + datetime.timedelta(hours=1))  # (once)
    assert await service.is_session_revoked("abc")
    assert not await service.is_session_revoked("other")
    assert len(run(db_driver, "MATCH (r:PGRevokedSession) RETURN r")) == 1

    # (one that has expired is cleared out when the next is revoked)
    await service.revoke_session("old", now - datetime.timedelta(hours=1))
    await service.revoke_session("new", now + datetime.timedelta(hours=1))
    assert not await service.is_session_revoked("old")
    assert await service.is_session_revoked("abc")


async def test_personal_access_tokens_are_kept_hashed_and_found_by_the_token(
    db_driver, clear_database
):
    await make_user()
    await make_user("jane", "jane@example.com")

    info, token = await service.create_access_token(
        "john", "scripts", "read", expires_days=7
    )
    assert token.startswith("pgl_")
    assert info.scope == "read" and info.expires_when is not None

    node = run(db_driver, "MATCH (t:PGAccessToken) RETURN t")[0]["t"]
    assert node["token_hash"] == service.hash_access_token(token)
    assert token not in str(dict(node))

    found = await service.authenticate_access_token(token)
    assert found is not None and found[0].username == "john" and found[1] == "read"
    assert await service.authenticate_access_token(token + "x") is None
    assert await service.authenticate_access_token("not a token") is None

    # (using it is noted, once in a while)
    listed = await service.list_access_tokens("john")
    assert [t.id for t in listed] == [info.id]
    assert listed[0].last_used_when is not None
    assert await service.list_access_tokens("jane") == []
    assert not await service.revoke_access_token("jane", info.id)
    assert await service.revoke_access_token("john", info.id)
    assert await service.authenticate_access_token(token) is None
    assert not await service.revoke_access_token("john", info.id)


async def test_a_token_of_a_disabled_user_is_not_good(db_driver, clear_database):
    await make_user()
    _, token = await service.create_access_token("john", "scripts")
    await service.set_disabled("john", True)
    assert await service.authenticate_access_token(token) is None
