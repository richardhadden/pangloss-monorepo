"""`/api/users`: logging in, and managing users.

Logging in gives tokens (`POST /token`, then `Authorization: Bearer <access_token>`)
or a session, kept in cookies (`POST /session`). `/me` is for the user themselves;
the rest is for admins (who cannot change their own admin or disabled status, so that
the last admin does not lock everyone out).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from pangloss_core import settings as core_settings
from pangloss_users import service
from pangloss_users.exceptions import PanglossUserDoesNotExistError
from pangloss_users.models import User, UserUpdate

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
    Message,
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

router = APIRouter(prefix="/api/users", tags=["Users"])

LoginForm = Annotated[OAuth2PasswordRequestForm, Depends()]


async def authenticated_user(form: OAuth2PasswordRequestForm) -> User:
    user = await service.authenticate(form.username, form.password)
    if user is None:
        raise unauthorised("Incorrect username or password")
    return user


def access_token_for(username: str) -> AccessTokenResponse:
    return AccessTokenResponse(
        access_token=create_token(username, "access"),
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


async def active_user_for_refresh(username: str) -> User:
    user = await service.get_user(username)
    if user is None or user.disabled:
        raise unauthorised("Invalid or expired refresh token")
    return user


# ---------------------------------------------------------------------------
# Logging in: tokens
# ---------------------------------------------------------------------------


@router.post("/token", response_model=TokenResponse)
async def get_tokens(form: LoginForm):
    """Log in with a username and password (as a form, the OAuth2 way)"""
    user = await authenticated_user(form)
    access = access_token_for(user.username)
    return TokenResponse(
        access_token=access.access_token,
        refresh_token=create_token(user.username, "refresh"),
        expires_in=access.expires_in,
    )


@router.post("/token/refresh", response_model=AccessTokenResponse)
async def refresh_token(body: RefreshRequest):
    """A new access token, given a refresh token"""
    claims = refresh_claims(body.refresh_token)
    user = await active_user_for_refresh(claims.username)
    return access_token_for(user.username)


# ---------------------------------------------------------------------------
# Logging in: sessions (cookies)
# ---------------------------------------------------------------------------


@router.post("/session", response_model=Message)
async def start_session(form: LoginForm, response: Response):
    """Log in, keeping the tokens in (HTTP-only) cookies"""
    user = await authenticated_user(form)
    set_cookie(
        response, ACCESS_COOKIE_NAME, create_token(user.username, "access"), "access"
    )
    set_cookie(
        response, REFRESH_COOKIE_NAME, create_token(user.username, "refresh"), "refresh"
    )
    return Message(message="success")


@router.post("/session/refresh", response_model=Message)
async def refresh_session(request: Request, response: Response):
    """A new access cookie, given the refresh cookie"""
    claims = refresh_claims(request.cookies.get(REFRESH_COOKIE_NAME))
    user = await active_user_for_refresh(claims.username)
    set_cookie(
        response, ACCESS_COOKIE_NAME, create_token(user.username, "access"), "access"
    )
    return Message(message="success")


@router.delete("/session", response_model=Message)
async def end_session(response: Response):
    """Log out"""
    response.delete_cookie(ACCESS_COOKIE_NAME)
    response.delete_cookie(REFRESH_COOKIE_NAME)
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
    await service.change_password(user.username, body.old_password, body.new_password)
    return Message(message="success")


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
async def create_user(new_user: NewUser, _: CurrentAdmin):
    return await service.create_user(
        username=new_user.username,
        email=new_user.email,
        password=new_user.password,
        full_name=new_user.full_name,
        admin=new_user.admin,
    )


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
async def set_user_password(username: str, body: SetPassword, _: CurrentAdmin):
    await service.set_password(username, body.password)
    return Message(message="success")


@router.put("/{username}/admin", response_model=User)
async def set_user_admin(username: str, body: SetAdmin, admin: CurrentAdmin):
    not_yourself(admin, username)
    return await service.set_admin(username, body.admin)


@router.put("/{username}/disabled", response_model=User)
async def set_user_disabled(username: str, body: SetDisabled, admin: CurrentAdmin):
    not_yourself(admin, username)
    return await service.set_disabled(username, body.disabled)
