import datetime
import re

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from pydantic.alias_generators import to_camel

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


def check_username(username: str) -> str:
    if not USERNAME_PATTERN.match(username):
        raise ValueError(
            "A username can only contain letters, numbers, '_', '.' and '-' "
            "(at most 64 characters)"
        )
    return username


class CamelCaseModel(BaseModel):
    """The JSON of the API is camelCase (`fullName`); the names are accepted too"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class User(CamelCaseModel):
    """A user, as it can be shown: it never has the password, or its hash"""

    username: str
    # (users made by hand, such as the default user, may have no email)
    email: EmailStr | None = None
    full_name: str | None = None
    admin: bool = Field(default=False, json_schema_extra={"readOnly": True})
    disabled: bool = Field(default=False, json_schema_extra={"readOnly": True})
    created_when: datetime.datetime | None = None
    # Raised when the sessions of the user are ended (a password change, or "log out
    # everywhere"): a token made at an earlier number is no longer good. Not shown
    token_generation: int = Field(default=0, exclude=True)

    _check_username = field_validator("username")(check_username)


class UserCreate(CamelCaseModel):
    username: str
    email: EmailStr
    password: str
    full_name: str | None = None

    _check_username = field_validator("username")(check_username)


class UserUpdate(CamelCaseModel):
    """What can be changed about a user; whatever is left out is kept"""

    email: EmailStr | None = None
    full_name: str | None = None


class UserInDB(User):
    hashed_password: str | None = None


TOKEN_SCOPES = ("read", "write")


class AccessTokenInfo(CamelCaseModel):
    """A personal access token, as it can be shown: never the token itself"""

    id: str
    name: str
    # "read" tokens can only read; "write" ones do whatever the user can
    scope: str = "write"
    created_when: datetime.datetime
    expires_when: datetime.datetime | None = None


class AccessTokenRecord(AccessTokenInfo):
    """What is stored: the hash of the token (which is long and random, so a plain hash does)"""

    username: str
    token_hash: str
