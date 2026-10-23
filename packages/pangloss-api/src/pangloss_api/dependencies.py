"""FastAPI dependencies: who is making the request"""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from pangloss_users import current_request_username, service
from pangloss_users.models import User

from pangloss_api.tokens import TokenError, decode_token

ACCESS_COOKIE_NAME = "pangloss_access"
REFRESH_COOKIE_NAME = "pangloss_refresh"

TOKEN_URL = "/api/users/token"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=TOKEN_URL, auto_error=False)


def unauthorised(message: str) -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        detail=message,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_access_token(
    request: Request, bearer: Annotated[str | None, Depends(oauth2_scheme)]
) -> str | None:
    """The access token: from the `Authorization: Bearer` header, or the session cookie"""
    return bearer or request.cookies.get(ACCESS_COOKIE_NAME)


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


async def user_for_token(token: str, method: str = "GET") -> User:
    """The user a token is for, or 401. A token is a **personal access token** (`pgl_...`),
    or an access token (a JWT) that has not expired, has not been revoked, and is of the
    user's current `token_generation`. A `read` access token is refused (403) for a method
    that changes things."""
    if token.startswith(service.ACCESS_TOKEN_PREFIX):
        found = await service.authenticate_access_token(token)
        if found is None:
            raise unauthorised("Invalid or expired token")
        user, scope = found
        if scope == "read" and method not in SAFE_METHODS:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, detail="This token can only read"
            )
        current_request_username.set(user.username)
        return user

    try:
        claims = decode_token(token, "access")
    except TokenError as error:
        raise unauthorised("Invalid or expired token") from error

    # (looked up each time, so that a disabled user is refused at once)
    user = await service.get_user(claims.username)
    if (
        user is None
        or user.disabled
        or claims.generation < user.token_generation
        or (claims.jti and await service.is_session_revoked(claims.jti))
    ):
        raise unauthorised("Invalid or expired token")

    current_request_username.set(user.username)
    return user


async def get_current_user(
    request: Request,
    token: Annotated[str | None, Depends(get_access_token)],
) -> User:
    """The user making the request. Also sets `current_request_username`, so that what
    they write is recorded as theirs."""
    if not token:
        raise unauthorised("Not logged in")
    return await user_for_token(token, request.method)


async def get_current_admin(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if not user.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not authorised")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentAdmin = Annotated[User, Depends(get_current_admin)]
