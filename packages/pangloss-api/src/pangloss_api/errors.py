"""How errors from the database and models are reported to a client"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pangloss_models.exceptions import (
    PanglossConflictError,
    PanglossEntityInUseError,
    PanglossNotDeletableError,
    PanglossNotDeletedError,
    PanglossNotFoundError,
    PanglossReferenceError,
    PanglossUserDisabledError,
    PanglossUserNotFoundError,
    PanglossVersionConflictError,
    PanglossWriteError,
)
from pangloss_users.exceptions import (
    PanglossInvalidUserError,
    PanglossUserDoesNotExistError,
    PanglossUserError,
    PanglossUserExistsError,
)

# (an error is given the status of the first of these it is an instance of)
STATUS_FOR_ERROR: list[tuple[type[Exception], int]] = [
    (PanglossUserExistsError, 409),
    (PanglossUserDoesNotExistError, 404),
    (PanglossInvalidUserError, 422),
    (PanglossUserError, 400),
    (PanglossNotFoundError, 404),
    (PanglossVersionConflictError, 412),
    (PanglossEntityInUseError, 409),
    (PanglossConflictError, 409),
    (PanglossNotDeletedError, 409),
    (PanglossNotDeletableError, 400),
    (PanglossReferenceError, 422),
    (PanglossUserDisabledError, 403),
    (PanglossUserNotFoundError, 403),
    (PanglossWriteError, 400),
]


def status_for(error: Exception) -> int:
    return next(
        (code for kind, code in STATUS_FOR_ERROR if isinstance(error, kind)), 500
    )


async def error_handler(request: Request, error: Exception) -> JSONResponse:
    content: dict = {"detail": str(error)}
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
    return JSONResponse(status_code=status_for(error), content=content, headers=headers)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(PanglossUserError, error_handler)
    app.add_exception_handler(PanglossWriteError, error_handler)
