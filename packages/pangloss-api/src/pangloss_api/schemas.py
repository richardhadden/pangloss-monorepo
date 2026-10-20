"""What the user endpoints send and receive (a `User` itself never has a password)"""

from typing import Literal

from pangloss_users.models import UserCreate
from pydantic import BaseModel


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    # Seconds until the access token expires
    expires_in: int


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class NewUser(UserCreate):
    admin: bool = False


class ChangePassword(BaseModel):
    old_password: str
    new_password: str


class SetPassword(BaseModel):
    password: str


class SetAdmin(BaseModel):
    admin: bool


class SetDisabled(BaseModel):
    disabled: bool


class Message(BaseModel):
    message: str
