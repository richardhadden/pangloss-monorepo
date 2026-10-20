"""Access and refresh tokens (JWTs signed with `AUTHJWT_SECRET_KEY`).

Both hold the username as their subject; the `type` claim says which they are, so that
a refresh token cannot be used as an access token, or the other way round.
"""

import dataclasses
import datetime
from typing import Literal

import jwt
from pangloss_core import settings as core_settings

ALGORITHM = "HS256"

TokenType = Literal["access", "refresh"]


class TokenError(Exception):
    """The token is missing, malformed, expired, or of the wrong type"""


@dataclasses.dataclass
class TokenClaims:
    username: str
    type: TokenType
    expires: datetime.datetime


def lifetime(token_type: TokenType) -> datetime.timedelta:
    settings = core_settings.SETTINGS
    if token_type == "access":
        return datetime.timedelta(minutes=settings.AUTH_ACCESS_TOKEN_EXPIRE_MINUTES)
    return datetime.timedelta(days=settings.AUTH_REFRESH_TOKEN_EXPIRE_DAYS)


def create_token(username: str, token_type: TokenType) -> str:
    now = datetime.datetime.now(datetime.UTC)
    return jwt.encode(
        {
            "sub": username,
            "type": token_type,
            "iat": now,
            "exp": now + lifetime(token_type),
        },
        core_settings.SETTINGS.AUTHJWT_SECRET_KEY,
        algorithm=ALGORITHM,
    )


def decode_token(token: str, expected_type: TokenType) -> TokenClaims:
    try:
        claims = jwt.decode(
            token,
            core_settings.SETTINGS.AUTHJWT_SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"require": ["sub", "exp", "type"]},
        )
    except jwt.PyJWTError as error:
        raise TokenError(str(error)) from error

    if claims["type"] != expected_type:
        raise TokenError(f"Not a {expected_type} token")
    return TokenClaims(
        username=claims["sub"],
        type=claims["type"],
        expires=datetime.datetime.fromtimestamp(claims["exp"], datetime.UTC),
    )
