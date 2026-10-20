class PanglossUserError(Exception):
    """Base class for errors about users"""


class PanglossUserExistsError(PanglossUserError):
    """The username or email is already taken"""


class PanglossUserDoesNotExistError(PanglossUserError):
    """There is no such user"""


class PanglossInvalidUserError(PanglossUserError):
    """The details given for a user are not acceptable (e.g. a short password)"""
