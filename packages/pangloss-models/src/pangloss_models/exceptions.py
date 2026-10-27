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


class PanglossVersionConflictError(PanglossWriteError):
    """An update was made to a version of an object that is no longer the latest:
    someone else has updated it since it was read. Nothing was written."""

    def __init__(self, message: str, current_version: int | None = None):
        super().__init__(message)
        self.current_version = current_version


class PanglossUserNotFoundError(PanglossWriteError):
    """The user doing the write has no user node in the database"""


class PanglossUserDisabledError(PanglossWriteError):
    """The user doing the write has been disabled"""


class PanglossReadOnlyError(PanglossWriteError):
    """The database is being migrated: it can be read, and not written to, until that is done"""


class PanglossBulkLoadError(Exception):
    """A bulk load could not be started, or left the database needing attention (the message says what)"""


class PanglossBulkRecordError(PanglossBulkLoadError):
    """A record of a bulk upload is not valid, or could not be written. `line` is its line in the file"""

    def __init__(self, line: int, message: str) -> None:
        super().__init__(f"line {line}: {message}")
        self.line = line


class PanglossNotDeletableError(PanglossWriteError):
    """Only head documents can be deleted: this is part of another document"""


class PanglossNotDeletedError(PanglossWriteError):
    """An attempt to undelete something that has not been deleted"""


class PanglossEntityInUseError(PanglossWriteError):
    """An entity that documents (or other entities) refer to cannot be deleted. It
    has been marked for deletion instead (`meta.marked_for_deletion`)."""

    def __init__(self, message: str, entity_id=None, referenced_by=None):
        super().__init__(message)
        self.entity_id = entity_id
        # What refers to it: dicts with `id`, `type` and `label`
        self.referenced_by: list[dict] = referenced_by or []


class PanglossMigrationError(Exception):
    """A migration cannot be applied"""


class PanglossMigrationAnswerNeeded(PanglossMigrationError):
    """A change needs something that only a person can say (a value for existing nodes, what
    to do with what does not convert): it is `None` in the change as `diff` found it"""


class PanglossMigrationIrreversible(PanglossMigrationError):
    """A migration cannot be undone: a change in it has no inverse (or the inverse would not
    bring back the models as they were)"""


class PanglossMigrationNotSupported(PanglossMigrationError):
    """A change that has to be written by hand (`RunCypher`): it is found, but there is no
    general way to apply it"""


class PanglossServerOnly(Exception):
    """A function marked `@server_only` was called on a client of the API (the SDK), which
    does not have its body"""
