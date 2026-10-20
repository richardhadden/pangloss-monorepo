import datetime

import jwt
import pytest
from pangloss_api.app import create_app
from pangloss_api.tokens import ALGORITHM, TokenError, create_token, decode_token


def test_create_and_decode(settings):
    for kind in ("access", "refresh"):
        claims = decode_token(create_token("john", kind), kind)
        assert claims.username == "john"
        assert claims.type == kind
        assert claims.expires > datetime.datetime.now(datetime.UTC)


def test_the_type_is_checked(settings):
    with pytest.raises(TokenError):
        decode_token(create_token("john", "refresh"), "access")
    with pytest.raises(TokenError):
        decode_token(create_token("john", "access"), "refresh")


def test_expired_token(settings):
    settings.AUTH_ACCESS_TOKEN_EXPIRE_MINUTES = -1
    with pytest.raises(TokenError):
        decode_token(create_token("john", "access"), "access")


def test_tokens_must_be_signed_with_the_secret(settings):
    forged = jwt.encode(
        {"sub": "john", "type": "access", "exp": 9999999999},
        "another secret, also of a decent length",
        algorithm=ALGORITHM,
    )
    with pytest.raises(TokenError):
        decode_token(forged, "access")


def test_unsigned_tokens_are_refused(settings):
    unsigned = jwt.encode(
        {"sub": "john", "type": "access", "exp": 9999999999}, None, algorithm="none"
    )
    with pytest.raises(TokenError):
        decode_token(unsigned, "access")


def test_tokens_need_a_subject_expiry_and_type(settings):
    for claims in (
        {"type": "access", "exp": 9999999999},
        {"sub": "john", "type": "access"},
        {"sub": "john", "exp": 9999999999},
    ):
        token = jwt.encode(claims, settings.AUTHJWT_SECRET_KEY, algorithm=ALGORITHM)
        with pytest.raises(TokenError):
            decode_token(token, "access")


def test_garbage(settings):
    with pytest.raises(TokenError):
        decode_token("not a token", "access")


def test_a_short_secret_key_is_warned_about(settings):
    settings.AUTHJWT_SECRET_KEY = "short"
    with pytest.warns(UserWarning, match="AUTHJWT_SECRET_KEY"):
        create_app()


def test_settings_default_lifetimes(settings):
    assert settings.AUTH_ACCESS_TOKEN_EXPIRE_MINUTES == 30
    assert settings.AUTH_REFRESH_TOKEN_EXPIRE_DAYS == 14
