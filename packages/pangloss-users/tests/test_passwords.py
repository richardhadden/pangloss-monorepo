import pytest
from pangloss_users.exceptions import PanglossInvalidUserError
from pangloss_users.models import User, UserCreate
from pangloss_users.passwords import hash_password, verify_password
from pydantic import ValidationError


def test_hash_and_verify():
    hashed = hash_password("correct horse")
    assert hashed != "correct horse"
    assert verify_password("correct horse", hashed)
    assert not verify_password("wrong horse", hashed)


def test_hashes_are_salted():
    assert hash_password("correct horse") != hash_password("correct horse")


def test_a_user_without_a_hash_or_with_a_bad_one_cannot_verify():
    assert not verify_password("correct horse", None)
    assert not verify_password("correct horse", "")
    assert not verify_password("correct horse", "not a hash")


def test_short_passwords_are_refused():
    with pytest.raises(PanglossInvalidUserError):
        hash_password("short")


def test_usernames_are_checked():
    UserCreate(username="john.smith-1_a", email="john@example.com", password="x")
    for bad in ("", "john smith", "john/smith", "a" * 65):
        with pytest.raises(ValidationError):
            UserCreate(username=bad, email="john@example.com", password="x")
        with pytest.raises(ValidationError):
            User(username=bad)


def test_emails_are_checked():
    with pytest.raises(ValidationError):
        UserCreate(username="john", email="not an email", password="x")


def test_a_user_never_shows_a_password_hash():
    assert "hashed_password" not in User.model_fields
    assert "password" not in User.model_fields
