"""Who may get the SDK: `SDK_ACCESS` is `"admin"` (the default), `"user"` (any logged-in user)
or `"public"`. A login is a token (`Authorization: Bearer`, or the session cookie), or **HTTP
Basic**, which is what `pip` and `git` send: a username and a password (or an access token as
the password)."""

import base64
import binascii
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from pangloss_api.dependencies import get_access_token, get_current_user
from pangloss_api.tokens import TokenError, decode_token
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
    try:
        username, _, password = base64.b64decode(header[6:]).decode().partition(":")
    except (binascii.Error, UnicodeDecodeError):
        raise needs_login("Invalid credentials") from None

    user = await service.authenticate(username, password)
    if user is None:
        # (an access token may be given as the password)
        try:
            claims = decode_token(password, "access")
        except TokenError:
            raise needs_login("Invalid username or password") from None
        found = await service.get_user(claims.username)
        if claims.username != username or found is None or found.disabled:
            raise needs_login("Invalid username or password")
        user = found
    current_request_username.set(user.username)
    return user


async def sdk_access(
    request: Request, token: Annotated[str | None, Depends(get_access_token)]
) -> User | None:
    level = config.setting("SDK_ACCESS", "admin")
    if level == "public":
        return None

    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("basic "):
        user = await basic_user(authorization)
    elif token:
        user = await get_current_user(token)
    else:
        raise needs_login()

    if level == "admin" and not user.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not authorised")
    return user
