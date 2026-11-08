class PanglossInitialisationError(Exception):
    pass


class PanglossMetaError(Exception):
    pass


class PanglossAwaitingInitialisation(Exception):
    pass


class PanglossModelError(Exception):
    """A declared class says what the models cannot be made from. `fix`, if the mistake has an obvious mechanical
    correction in the source, names it (a key of `pangloss_models.diagnostics.FIXES`): the language server offers it"""

    def __init__(self, *args: object, fix: str | tuple[str, ...] | None = None):
        super().__init__(*args)
        self.fix = fix


class PanglossModelWarning(UserWarning):
    """A declared class says something the generated models cannot carry (a method, a `model_config`, a
    `@computed_field`): the models are made, and this says what was left behind. `model` and `member` say where in
    the source it is, and `fix` (see `PanglossModelError`) what would correct it"""

    def __init__(
        self,
        *args: object,
        model: type | None = None,
        member: str | None = None,
        fix: str | tuple[str, ...] | None = None,
    ):
        super().__init__(*args)
        self.model = model
        self.member = member
        self.fix = fix


class PanglossInternalError(Exception):
    pass


class PanglossRuntimeError(Exception):
    pass


class PanglossImportError(ImportError):
    pass


# What importing and initialising the models can raise when they are declared wrongly: a command that loads the models
# reports these as a message, not a traceback
MODEL_ERRORS = (
    PanglossInitialisationError,
    PanglossImportError,
    PanglossModelError,
    PanglossMetaError,
)


class PanglossWriteError(Exception):
    """A write to the database was rejected, and (unless the error says otherwise)
    nothing was written"""


class PanglossWriteRefused(PanglossWriteError):
    """A `@before_create` or `@before_update` of the class refused the write (a 422 over the API). `field`, if
    given, is the field the reason is about; `path`, set when it is raised, is where that is in what was written
    (`("clauses", 0, "text")` for a nested document's)"""

    def __init__(self, message: str, field: str | None = None):
        super().__init__(message)
        self.field = field
        self.path: tuple[str | int, ...] = (field,) if field else ()


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


class PanglossNotCreatableError(PanglossWriteError):
    """A document of a class with `create_directly=False` can only be made as part of another document"""


class PanglossNotDeletedError(PanglossWriteError):
    """An attempt to undelete something that has not been deleted"""


class PanglossClassChangeError(PanglossWriteError):
    """A change of an entity's class (`changing_class_from`) that cannot be made: the node is not of the class it is
    said to be changed from, or something refers to it by a relation that cannot hold the new class"""


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


class PanglossUnknownTypeError(Exception):
    """A type named in a search is not a model that can be searched"""


class PanglossSearchError(Exception):
    """A structured search that cannot be made: a field that does not exist, an operator that does not
    fit the field, a value of the wrong type, or something not supported yet"""


class PanglossSearchTimeoutError(Exception):
    """A structured search took longer than the time allowed for it (`SEARCH_TIMEOUT_SECONDS`). It is not
    tried again: a search that is too big for the time is that every time"""
