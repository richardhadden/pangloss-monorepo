from contextvars import ContextVar

current_request_username = ContextVar(
    "current_request_username", default="pangloss_default_user"
)

# Whether the request may see documents that are not published (`published: false` on the head node;
# see docs/review.md). True outside a request (scripts, commands, tests); the API sets it false for
# a request that is not logged in.
see_unpublished = ContextVar("see_unpublished", default=True)
