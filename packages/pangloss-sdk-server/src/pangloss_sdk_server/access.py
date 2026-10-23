"""Who may get the SDK: `SDK_ACCESS` is `"admin"` (the default), `"user"` (any logged-in user)
or `"public"`. A login is a token (`Authorization: Bearer`, or the session cookie), or **HTTP
Basic**, which is what `pip` and `git` send: a username and a password (or an access token as
the password)."""

import base64
import binascii
from fastapi import HTTPException, Request, status
from pangloss_api.dependencies import ACCESS_COOKIE_NAME, user_for_token
from pangloss_users import current_request_username, service
from pangloss_users.models import User

from pangloss_sdk_server import config


def needs_login(message: str = "Not logged in") -> HTTPException:
    # (`Basic`, so that `pip` and a browser ask for a username and password)
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        detail=message,
        headers={"WWW-Authenticate": 'Basic realm="Pangloss SDK"'},
    )


async def basic_user(header: str) -> User:
    """The user of HTTP Basic credentials: a username and a password, or a personal access
    token or an access token as the password (what a script, `pip` and `git` can keep)"""
    try:
        username, _, password = base64.b64decode(header[6:]).decode().partition(":")
    except (binascii.Error, UnicodeDecodeError):
        raise needs_login("Invalid credentials") from None

    if password.startswith(service.ACCESS_TOKEN_PREFIX):
        # (any method: this is for reading the SDK)
        try:
            user = await user_for_token(password)
        except HTTPException:
            raise needs_login("Invalid username or password") from None
        if user.username != username:
            raise needs_login("Invalid username or password")
        return user

    user = await service.authenticate(username, password)
    if user is None:
        # (an access token may be given as the password)
        try:
            user = await user_for_token(password)
        except HTTPException:
            raise needs_login("Invalid username or password") from None
        if user.username != username:
            raise needs_login("Invalid username or password")
    current_request_username.set(user.username)
    return user


def bearer_of(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:]
    return request.cookies.get(ACCESS_COOKIE_NAME)


async def authorise(request: Request) -> User | None:
    """The user, for a request to the SDK, or raise 401 or 403 by `SDK_ACCESS`. (A plain
    function, as git's endpoint is not a FastAPI route.)"""
    level = config.setting("SDK_ACCESS", "admin")
    if level == "public":
        return None

    authorization = request.headers.get("authorization", "")
    token = bearer_of(request)
    if authorization.lower().startswith("basic "):
        user = await basic_user(authorization)
    elif token:
        user = await user_for_token(token, "GET")
    else:
        raise needs_login()

    if level == "admin" and not user.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not authorised")
    return user


async def sdk_access(request: Request) -> User | None:
    return await authorise(request)
