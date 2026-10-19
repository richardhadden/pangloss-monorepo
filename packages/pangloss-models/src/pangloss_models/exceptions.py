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
    """A write to the database was rejected, and (unless the error says otherwise)
    nothing was written"""


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


class PanglossNotDeletableError(PanglossWriteError):
    """Only head documents can be deleted: this is part of another document"""


class PanglossEntityInUseError(PanglossWriteError):
    """An entity that documents (or other entities) refer to cannot be deleted. It
    has been marked for deletion instead (`meta.marked_for_deletion`)."""

    def __init__(self, message: str, entity_id=None, referenced_by=None):
        super().__init__(message)
        self.entity_id = entity_id
        # What refers to it: dicts with `id`, `type` and `label`
        self.referenced_by: list[dict] = referenced_by or []
