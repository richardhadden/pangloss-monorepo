"""What the user endpoints send and receive (a `User` itself never has a password)"""

from typing import Literal

from pangloss_users.models import AccessTokenInfo, CamelCaseModel, UserCreate
from pydantic import BaseModel


# The token endpoints use the names of OAuth2 (RFC 6749), which clients and the
# interactive docs look for: the one place the API is not camelCase.
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


class ChangePassword(CamelCaseModel):
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


class NewAccessToken(CamelCaseModel):
    name: str
    # "read" can only read; "write" does whatever the user can
    scope: Literal["read", "write"] = "write"
    # Days until it expires; without, it does not
    expires_days: int | None = None


class CreatedAccessToken(AccessTokenInfo):
    """The only time the token is shown"""

    token: str
