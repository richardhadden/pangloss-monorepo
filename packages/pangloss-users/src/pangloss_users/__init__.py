"""Users of Pangloss: their models, passwords and the `service` functions (implementation_docs/users.md)"""

from contextvars import ContextVar

lazy from pangloss_users.exceptions import (
    PanglossInvalidUserError,
    PanglossUserDoesNotExistError,
    PanglossUserError,
    PanglossUserExistsError,
)
lazy from pangloss_users.models import (
    AccessTokenInfo,
    User,
    UserCreate,
    UserInDB,
    UserItem,
    UserItems,
    UserSummary,
    UserUpdate,
)

__all__ = [
    "AccessTokenInfo",
    "PanglossInvalidUserError",
    "PanglossUserDoesNotExistError",
    "PanglossUserError",
    "PanglossUserExistsError",
    "User",
    "UserCreate",
    "UserInDB",
    "UserItem",
    "UserItems",
    "UserSummary",
    "UserUpdate",
    "current_request_username",
    "see_unpublished",
]

current_request_username = ContextVar(
    "current_request_username", default="pangloss_default_user"
)

# Whether the request may see documents that are not published (`published: false` on the head node;
# see implementation_docs/review.md). True outside a request (scripts, commands, tests); the API sets it false for
# a request that is not logged in.
see_unpublished = ContextVar("see_unpublished", default=True)
