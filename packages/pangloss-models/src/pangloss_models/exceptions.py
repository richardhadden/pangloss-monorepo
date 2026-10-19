class PanglossInitialisationError(Exception):
    pass


class PanglossMetaError(Exception):
    pass


class PanglossAwaitingInitialisation(Exception):
    pass


class PanglossModelError(Exception):
    pass


class PanglossInternalError(Exception):
    pass


class PanglossRuntimeError(Exception):
    pass


class PanglossImportError(ImportError):
    pass


class PanglossWriteError(Exception):
    """A write to the database was rejected, and nothing was written"""


class PanglossNotFoundError(PanglossWriteError):
    """The object being updated does not exist (or is not of the given type)"""


class PanglossReferenceError(PanglossWriteError):
    """An object refers to an existing entity that does not exist, or is not of
    a type allowed in that field"""


class PanglossConflictError(PanglossWriteError):
    """An id given for a new object is already in use, or an object being
    updated includes an id belonging to a different head object"""


class PanglossUserNotFoundError(PanglossWriteError):
    """The user doing the write has no user node in the database"""
