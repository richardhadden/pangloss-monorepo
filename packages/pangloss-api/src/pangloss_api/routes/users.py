"""`/api/users`: logging in, and managing users.

Logging in gives tokens (`POST /token`, then `Authorization: Bearer <access_token>`)
or a session, kept in cookies (`POST /session`). `/me` is for the user themselves;
the rest is for admins (who cannot change their own admin or disabled status, so that
the last admin does not lock everyone out).
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from pangloss_core import settings as core_settings
from pangloss_users import service
from pangloss_users.exceptions import (
    PanglossInvalidUserError,
    PanglossUserDoesNotExistError,
)
from pangloss_users.models import AccessTokenInfo, User, UserUpdate

from pangloss_api import throttle
from pangloss_api.dependencies import (
    ACCESS_COOKIE_NAME,
    REFRESH_COOKIE_NAME,
    CurrentAdmin,
    CurrentUser,
    unauthorised,
)
from pangloss_api.schemas import (
    AccessTokenResponse,
    ChangePassword,
    CreatedAccessToken,
    Message,
    NewAccessToken,
    NewUser,
    RefreshRequest,
    SetAdmin,
    SetDisabled,
    SetPassword,
    TokenResponse,
)
from pangloss_api.tokens import (
    TokenError,
    create_token,
    decode_token,
    lifetime,
)

logger = logging.getLogger("pangloss.api.auth")

router = APIRouter(prefix="/api/users", tags=["Users"])

LoginForm = Annotated[OAuth2PasswordRequestForm, Depends()]


def client_address(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def authenticated_user(
    form: OAuth2PasswordRequestForm, request: Request, via: str
) -> User:
    throttle.check(form.username)
    user = await service.authenticate(form.username, form.password)
    if user is None:
        throttle.failed(form.username)
        logger.warning(
            "Login failed for user %r from %s (%s)",
            form.username,
            client_address(request),
            via,
        )
        raise unauthorised("Incorrect username or password")
    throttle.succeeded(form.username)
    logger.info("Login: %r from %s (%s)", user.username, client_address(request), via)
    return user


def access_token_for(user: User) -> AccessTokenResponse:
    return AccessTokenResponse(
        access_token=create_token(user.username, "access", user.token_generation),
        expires_in=int(lifetime("access").total_seconds()),
    )


def set_cookie(response: Response, name: str, value: str, token_type) -> None:
    settings = core_settings.SETTINGS
    response.set_cookie(
        name,
        value,
        max_age=int(lifetime(token_type).total_seconds()),
        httponly=True,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        secure=settings.AUTH_COOKIE_SECURE or settings.AUTH_COOKIE_SAMESITE == "none",
    )


def refresh_claims(token: str | None):
    if not token:
        raise unauthorised("No refresh token")
    try:
        return decode_token(token, "refresh")
    except TokenError as error:
        raise unauthorised("Invalid or expired refresh token") from error


async def active_user_for_refresh(claims) -> User:
    """The user of a refresh token that is still good: not revoked, and not made before
    the user's sessions were ended"""
    user = await service.get_user(claims.username)
    if (
        user is None
        or user.disabled
        or claims.generation < user.token_generation
        or (claims.jti and await service.is_session_revoked(claims.jti))
    ):
        raise unauthorised("Invalid or expired refresh token")
    return user


async def revoke(token: str | None) -> None:
    """Revoke a token (of either kind) that is good, until it would have expired. One that
    is not good, or not there, is ignored: it cannot be used anyway"""
    if not token:
        return
    for token_type in ("access", "refresh"):
        try:
            claims = decode_token(token, token_type)  # type: ignore[arg-type]
        except TokenError:
            continue
        if claims.jti:
            await service.revoke_session(claims.jti, claims.expires)
        return


# ---------------------------------------------------------------------------
# Logging in: tokens
# ---------------------------------------------------------------------------


@router.post("/token", response_model=TokenResponse)
async def get_tokens(form: LoginForm, request: Request):
    """Log in with a username and password (as a form, the OAuth2 way)"""
    user = await authenticated_user(form, request, "token")
    access = access_token_for(user)
    return TokenResponse(
        access_token=access.access_token,
        refresh_token=create_token(user.username, "refresh", user.token_generation),
        expires_in=access.expires_in,
    )


@router.post("/token/refresh", response_model=AccessTokenResponse)
async def refresh_token(body: RefreshRequest):
    """A new access token, given a refresh token"""
    claims = refresh_claims(body.refresh_token)
    user = await active_user_for_refresh(claims)
    logger.info("Token refreshed for %r", user.username)
    return access_token_for(user)


@router.post("/token/revoke", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_token(body: RefreshRequest):
    """Log out: the refresh token (given by whoever has it) stops working, so no more access
    tokens can be got with it. (An access token already made lasts until it expires; to end
    those too, `POST /me/logout-all`.)"""
    await revoke(body.refresh_token)
    logger.info("Refresh token revoked")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Logging in: sessions (cookies)
# ---------------------------------------------------------------------------


@router.post("/session", response_model=Message)
async def start_session(form: LoginForm, request: Request, response: Response):
    """Log in, keeping the tokens in (HTTP-only) cookies"""
    user = await authenticated_user(form, request, "session")
    set_cookie(
        response,
        ACCESS_COOKIE_NAME,
        create_token(user.username, "access", user.token_generation),
        "access",
    )
    set_cookie(
        response,
        REFRESH_COOKIE_NAME,
        create_token(user.username, "refresh", user.token_generation),
        "refresh",
    )
    return Message(message="success")


@router.post("/session/refresh", response_model=Message)
async def refresh_session(request: Request, response: Response):
    """A new access cookie, given the refresh cookie"""
    claims = refresh_claims(request.cookies.get(REFRESH_COOKIE_NAME))
    user = await active_user_for_refresh(claims)
    logger.info("Session refreshed for %r", user.username)
    set_cookie(
        response,
        ACCESS_COOKIE_NAME,
        create_token(user.username, "access", user.token_generation),
        "access",
    )
    return Message(message="success")


@router.delete("/session", response_model=Message)
async def end_session(request: Request, response: Response):
    """Log out: the cookies are cleared, and the tokens in them stop working"""
    await revoke(request.cookies.get(REFRESH_COOKIE_NAME))
    await revoke(request.cookies.get(ACCESS_COOKIE_NAME))
    response.delete_cookie(ACCESS_COOKIE_NAME)
    response.delete_cookie(REFRESH_COOKIE_NAME)
    logger.info("Session ended")
    return Message(message="success")


# ---------------------------------------------------------------------------
# The current user
# ---------------------------------------------------------------------------


@router.get("/me", response_model=User)
async def read_me(user: CurrentUser):
    return user


@router.patch("/me", response_model=User)
async def update_me(update: UserUpdate, user: CurrentUser):
    """Change your own email and/or full name"""
    return await service.update_user(user.username, update)


@router.put("/me/password", response_model=Message)
async def change_my_password(body: ChangePassword, user: CurrentUser):
    """Change your password. This ends every session (this one too: log in again)"""
    await service.change_password(user.username, body.old_password, body.new_password)
    logger.info("Password changed by %r (all sessions ended)", user.username)
    return Message(message="success")


@router.post("/me/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_everywhere(user: CurrentUser):
    """End every session of yours: every token made until now stops working (personal
    access tokens are not tokens of a session, and go on: revoke them one by one)"""
    await service.end_sessions(user.username)
    logger.info("All sessions ended by %r", user.username)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Personal access tokens: long-lived, named and revocable, for scripts and for git
# ---------------------------------------------------------------------------


def not_with_an_access_token(request: Request) -> None:
    """A personal access token cannot make more of them"""
    header = request.headers.get("authorization", "")
    if header.removeprefix("Bearer ").startswith(service.ACCESS_TOKEN_PREFIX):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Personal access tokens are made when logged in, not with another",
        )


@router.post(
    "/me/tokens", response_model=CreatedAccessToken, status_code=status.HTTP_201_CREATED
)
async def create_access_token(
    body: NewAccessToken, user: CurrentUser, request: Request
):
    """Make a personal access token. The token is in the answer **once**: it is not kept,
    and cannot be shown again. Use it as `Authorization: Bearer <token>`, or as the password
    of HTTP Basic (with your username). `scope` `read` can only read"""
    not_with_an_access_token(request)
    try:
        info, token = await service.create_access_token(
            user.username, body.name, body.scope, body.expires_days
        )
    except PanglossInvalidUserError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))
    logger.info(
        "Personal access token %r (scope %s) made by %r",
        body.name,
        body.scope,
        user.username,
    )
    return CreatedAccessToken(**info.model_dump(), token=token)


@router.get("/me/tokens", response_model=list[AccessTokenInfo])
async def list_access_tokens(user: CurrentUser):
    """Your personal access tokens (not the tokens themselves)"""
    return await service.list_access_tokens(user.username)


@router.delete("/me/tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_access_token(token_id: str, user: CurrentUser):
    if not await service.revoke_access_token(user.username, token_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="There is no such token")
    logger.info("Personal access token %s revoked by %r", token_id, user.username)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Managing users (admin)
# ---------------------------------------------------------------------------


def not_yourself(admin: User, username: str) -> None:
    if admin.username == username:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="You cannot change your own admin or disabled status",
        )


@router.get("", response_model=list[User])
async def list_users(_: CurrentAdmin):
    return await service.list_users()


@router.post("", response_model=User, status_code=status.HTTP_201_CREATED)
async def create_user(new_user: NewUser, admin: CurrentAdmin):
    created = await service.create_user(
        username=new_user.username,
        email=new_user.email,
        password=new_user.password,
        full_name=new_user.full_name,
        admin=new_user.admin,
    )
    logger.info(
        "User %r made by %r (admin: %s)",
        new_user.username,
        admin.username,
        new_user.admin,
    )
    return created


@router.get("/{username}", response_model=User)
async def read_user(username: str, current: CurrentUser):
    """A user (your own, or, as an admin, anyone's)"""
    if username != current.username and not current.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not authorised")
    user = await service.get_user(username)
    if user is None:
        raise PanglossUserDoesNotExistError(f"There is no user '{username}'")
    return user


@router.patch("/{username}", response_model=User)
async def update_user(username: str, update: UserUpdate, _: CurrentAdmin):
    return await service.update_user(username, update)


@router.put("/{username}/password", response_model=Message)
async def set_user_password(username: str, body: SetPassword, admin: CurrentAdmin):
    await service.set_password(username, body.password)
    logger.info("Password of %r set by %r", username, admin.username)
    return Message(message="success")


@router.put("/{username}/admin", response_model=User)
async def set_user_admin(username: str, body: SetAdmin, admin: CurrentAdmin):
    not_yourself(admin, username)
    user = await service.set_admin(username, body.admin)
    logger.info("Admin of %r set to %s by %r", username, body.admin, admin.username)
    return user


@router.put("/{username}/disabled", response_model=User)
async def set_user_disabled(username: str, body: SetDisabled, admin: CurrentAdmin):
    not_yourself(admin, username)
    user = await service.set_disabled(username, body.disabled)
    logger.info(
        "Disabled of %r set to %s by %r", username, body.disabled, admin.username
    )
    return user
