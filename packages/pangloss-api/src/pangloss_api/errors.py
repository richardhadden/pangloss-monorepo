"""How errors from the database and models are reported to a client"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pangloss_models import (
    PanglossClassChangeError,
    PanglossConflictError,
    PanglossEntityInUseError,
    PanglossNotDeletableError,
    PanglossNotDeletedError,
    PanglossNotFoundError,
    PanglossReadOnlyError,
    PanglossReferenceError,
    PanglossSearchTimeoutError,
    PanglossUserDisabledError,
    PanglossUserNotFoundError,
    PanglossVersionConflictError,
    PanglossWriteError,
)
from pangloss_users import (
    PanglossInvalidUserError,
    PanglossUserDoesNotExistError,
    PanglossUserError,
    PanglossUserExistsError,
)
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from pangloss_api.migration_watch import moved_after_failure, refusal
from pangloss_api.validation import validation_error_handler

logger = logging.getLogger("pangloss.api.errors")

# (an error is given the status of the first of these it is an instance of)
STATUS_FOR_ERROR: list[tuple[type[Exception], int]] = [
    (PanglossUserExistsError, 409),
    (PanglossUserDoesNotExistError, 404),
    (PanglossInvalidUserError, 422),
    (PanglossUserError, 400),
    (PanglossNotFoundError, 404),
    (PanglossVersionConflictError, 412),
    (PanglossEntityInUseError, 409),
    (PanglossClassChangeError, 409),
    (PanglossConflictError, 409),
    (PanglossNotDeletedError, 409),
    (PanglossNotDeletableError, 400),
    (PanglossReferenceError, 422),
    (PanglossUserDisabledError, 403),
    (PanglossUserNotFoundError, 403),
    (PanglossReadOnlyError, 503),
    (PanglossSearchTimeoutError, 504),
    (PanglossWriteError, 400),
]


def status_for(error: Exception) -> int:
    return next(
        (code for kind, code in STATUS_FOR_ERROR if isinstance(error, kind)), 500
    )


async def error_handler(request: Request, error: Exception) -> JSONResponse:
    # (`error` is the class, for a client to raise the same one: see `pangloss-sdk`)
    content: dict = {"detail": str(error), "error": type(error).__name__}
    if isinstance(error, PanglossEntityInUseError):
        # What refers to the entity (it has been marked for deletion)
        content["referencedBy"] = [
            {key: str(value) for key, value in item.items()}
            for item in error.referenced_by
        ]
    headers = {}
    if isinstance(error, PanglossVersionConflictError) and error.current_version:
        # (what the version is now: to load again, and see what has been changed)
        content["currentVersion"] = error.current_version
        headers["ETag"] = f'"{error.current_version}"'
    if isinstance(error, PanglossReadOnlyError):
        headers["Retry-After"] = "30"  # (a migration takes a while: look again soon)
    code = status_for(error)
    where = f"{request.method} {request.url.path}" if request else "(no request)"
    if isinstance(error, PanglossVersionConflictError):
        logger.warning(
            "Conflict on %s: %s (now version %s)", where, error, error.current_version
        )
    elif isinstance(error, PanglossReadOnlyError):
        logger.warning("Write refused during a migration: %s", where)
    else:
        logger.debug("%s -> %s %s", where, code, type(error).__name__)
    return JSONResponse(status_code=code, content=content, headers=headers)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(PanglossUserError, error_handler)
    app.add_exception_handler(PanglossWriteError, error_handler)
    app.add_exception_handler(PanglossSearchTimeoutError, error_handler)


class ServerErrorResponder:
    """Answer a bug (an unhandled exception) with a `500` from inside the middleware.

    Starlette answers it from outside all middleware, so the response would not pass
    through `CORSMiddleware` and has no CORS headers: a browser then reports a CORS
    error instead of the status. This has to be added before `CORSMiddleware`, so
    that it is inside it."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = False

        async def send_tracking_start(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, send_tracking_start)
        except Exception:
            if started:
                raise  # (too late to change the response)
            logger.exception("Unhandled error in %s %s", scope["method"], scope["path"])
            # (data the models do not fit is what a migration made under the server looks like: say that)
            moved = await moved_after_failure(scope)
            response = (
                refusal(moved)
                if moved is not None
                else JSONResponse(
                    status_code=500, content={"detail": "Internal server error"}
                )
            )
            await response(scope, receive, send)
