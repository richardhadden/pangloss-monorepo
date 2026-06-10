from contextvars import ContextVar

current_request_username = ContextVar(
    "current_request_username", default="pangloss_default_user"
)
