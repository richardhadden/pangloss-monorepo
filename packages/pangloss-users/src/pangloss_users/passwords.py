"""Hashing and checking passwords (Argon2id)"""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from pangloss_users.exceptions import PanglossInvalidUserError

MIN_PASSWORD_LENGTH = 8

_hasher = PasswordHasher()

# Hashed and checked against when there is no user to check, so that finding no user
# takes as long as a wrong password
_DUMMY_HASH = _hasher.hash("pangloss-no-such-user")


def check_password_acceptable(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise PanglossInvalidUserError(
            f"A password must be at least {MIN_PASSWORD_LENGTH} characters long"
        )


def hash_password(plain_password: str) -> str:
    check_password_acceptable(plain_password)
    return _hasher.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str | None) -> bool:
    """Whether the password matches the hash. (A user with no hash cannot log in.)"""
    if not hashed_password:
        _verify(plain_password, _DUMMY_HASH)
        return False
    return _verify(plain_password, hashed_password)


def _verify(plain_password: str, hashed_password: str) -> bool:
    try:
        return _hasher.verify(hashed_password, plain_password)
    except VerificationError, InvalidHashError:
        return False


def password_needs_rehash(hashed_password: str) -> bool:
    """Whether the hash was made with weaker parameters than are now used"""
    return _hasher.check_needs_rehash(hashed_password)
