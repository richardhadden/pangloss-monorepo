from collections.abc import Iterable
from dataclasses import dataclass
from difflib import get_close_matches


class PanglossInitialisationError(Exception):
    pass


@dataclass(frozen=True)
class AtString:
    """The string in the source that a refusal is about: the option it is given to (`indexes`), the string itself, and
    the names it could have been (the language server underlines the string, and offers the closest of these)"""

    option: str
    value: str
    candidates: tuple[str, ...] = ()


def did_you_mean(value: str, candidates: Iterable[str]) -> str:
    """` Did you mean 'name'?`, or nothing, to add to a message about a name that is not one of `candidates`"""
    close = get_close_matches(value, list(candidates), n=1, cutoff=0.6)
    return f" Did you mean '{close[0]}'?" if close else ""


class _Refusal(Exception):
    """What a declared class says that Pangloss refuses. `fix`, if the mistake has an obvious mechanical correction
    in the source, names it (a key of `pangloss_models.diagnostics.FIXES`): the language server offers it.
    `at_string` says which string in the source it is about"""

    def __init__(
        self,
        *args: object,
        fix: str | tuple[str, ...] | None = None,
        at_string: AtString | None = None,
    ):
        super().__init__(*args)
        self.fix = fix
        self.at_string = at_string


class PanglossMetaError(_Refusal):
    pass


class PanglossAwaitingInitialisation(Exception):
    pass


class PanglossModelError(_Refusal):
    pass


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


class PanglossMergeError(PanglossWriteError):
    """A merge of two entities (`Entity.merge`), or the undoing of one, that cannot be made: the message says why.
    Nothing was written"""


class PanglossMergeTooLargeError(PanglossMergeError):
    """A merge would write more heads than `MERGE_LIMIT`: it is made only when asked for as a large one
    (`allow_large`), in batches. `heads` is how many, `limit` the limit"""

    def __init__(self, message: str, heads: int = 0, limit: int = 0):
        super().__init__(message)
        self.heads = heads
        self.limit = limit


class PanglossMergeBusyError(PanglossMergeError):
    """A merge gave way to other writes of the same entities and documents too many times: try again when they are
    done (a bulk change of the documents that refer to the entities is the usual cause)"""


class PanglossMergeNotAllowedError(PanglossMergeError):
    """A merge, or the undoing of one, that this user may not make: the one who proposed it cannot be the one who
    verifies it, and one that nobody proposed is made only by those the project lets merge (`MERGE_DIRECTLY`)"""


class PanglossMergedError(PanglossWriteError):
    """A write addressed to an entity that has been merged into another (an update, a delete, an undelete): refused,
    naming the survivor (`merged_into`). Only references to a merged entity are resolved to its survivor"""

    def __init__(self, message: str, id=None, merged_into=None):
        super().__init__(message)
        self.id = id
        self.merged_into = merged_into


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
