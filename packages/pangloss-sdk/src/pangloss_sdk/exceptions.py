"""What can go wrong on the client, beyond the errors the models already have.

The errors the server's database module raises (`PanglossNotFoundError`,
`PanglossVersionConflictError`, ...) are raised here too, from the server's answer, so
that the same `except` clauses work. These are the ones that only a client has.
"""


class PanglossSdkError(Exception):
    """Base class of what only a client of the API can raise"""


class PanglossConnectionError(PanglossSdkError):
    """The server could not be reached, or did not answer in time"""


class PanglossServerError(PanglossSdkError):
    """The server failed (5xx) or answered with something that is not understood"""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class PanglossAuthenticationError(PanglossSdkError):
    """The server refused the login or the token (401)"""


class PanglossAuthenticationRequired(PanglossAuthenticationError):
    """A login is needed, and there is no way to ask for one (no credentials are set, and
    there is no terminal)"""


class PanglossPermissionError(PanglossSdkError):
    """The user is logged in but may not do this (403)"""


class PanglossRequestError(PanglossSdkError):
    """The server did not accept the request as the SDK made it (400 or 422 that is not
    one of the errors of a write). Usually the SDK is out of date with the server"""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class PanglossNotConnected(PanglossSdkError):
    """A model function was used before `connect()`"""
