"""FastAPI dependencies: who is making the request"""

from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from pangloss_core import settings as core_settings
from pangloss_users import (
    User,
    current_request_is_admin,
    current_request_username,
    see_unpublished,
    service,
)

from pangloss_api.tokens import TokenError, decode_token

ACCESS_COOKIE_NAME = "pangloss_access"
REFRESH_COOKIE_NAME = "pangloss_refresh"
# (the refresh token is only ever read by the session routes: the cookie is not sent anywhere else)
REFRESH_COOKIE_PATH = "/api/users/session"

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
    current_request_is_admin.set(user.admin)
    return user


CROSS_SITE = (
    "This request was made from another site: the session cookie is only used from the API's own site "
    "(or one of BACKEND_CORS_ORIGINS). From elsewhere, send the token in the Authorization header"
)


def origin_is_trusted(request: Request, origin: str) -> bool:
    """Whether `origin` is the API's own (the `Host` the request came to), or one of the frontends that may use it
    (`BACKEND_CORS_ORIGINS`; `*` is not an origin, and does not count: with it, cookies are not for other sites)"""
    origin = origin.strip().rstrip("/").lower()
    if not origin or origin == "null":
        return False
    settings = core_settings.__dict__.get("SETTINGS")
    if origin in getattr(settings, "BACKEND_CORS_ORIGINS", []):
        return True
    return urlsplit(origin).netloc.lower() == request.headers.get("host", "").lower()


async def require_same_site(request: Request) -> None:
    """Refuse (403) a request that a browser made from another site, unless that site is one of
    `BACKEND_CORS_ORIGINS`: what protects a cookie session from a request forged by a page on another
    site, beyond `SameSite`. A browser says where a request is from in `Sec-Fetch-Site`, and in `Origin`
    on anything but a read; a request with neither (a script, curl, the SDK) is let through, as it is
    not a browser carrying someone else's cookies."""
    origin = request.headers.get("origin")
    site = request.headers.get("sec-fetch-site", "").lower()
    if site == "cross-site" or (not site and origin is not None):
        if origin is None or not origin_is_trusted(request, origin):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=CROSS_SITE)


async def get_current_user(
    request: Request,
    bearer: Annotated[str | None, Depends(oauth2_scheme)],
    token: Annotated[str | None, Depends(get_access_token)],
) -> User:
    """The user making the request. Also sets `current_request_username`, so that what
    they write is recorded as theirs. A write that is logged in by the session cookie (not
    the `Authorization` header) has to come from the API's own site, or an allowed origin."""
    if not token:
        raise unauthorised("Not logged in")
    if bearer is None and request.method not in SAFE_METHODS:
        await require_same_site(request)
    return await user_for_token(token, request.method)


async def get_current_admin(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if not user.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not authorised")
    return user


async def set_visibility(
    request: Request, token: Annotated[str | None, Depends(get_access_token)]
) -> None:
    """On every request: a user who is logged in may see documents that are not published, one who is not
    may not (and is not refused for it: reading is open). The token is looked at again by routes that need
    a user."""
    seen = False
    if token:
        try:
            await user_for_token(token, request.method)
            seen = True
        except HTTPException:
            pass
    see_unpublished.set(seen)


CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentAdmin = Annotated[User, Depends(get_current_admin)]
