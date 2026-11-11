"""The review state of a document, and its comments"""

import datetime
import enum
from uuid import UUID

from pangloss_models import Creator
from pangloss_models.creators import creators_from
from pydantic import BaseModel, ConfigDict, field_validator
from pydantic.alias_generators import to_camel


class _Camel(BaseModel):
    """(Like the models of the API: camelCase in JSON, either way in Python)"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ReviewStatus(enum.StrEnum):
    UNCHECKED = "unchecked"
    ERRORS_FOUND = "errors_found"
    PUBLISHED = "published"

    @classmethod
    def _missing_(cls, value: object) -> "ReviewStatus | None":
        # (`checked`: what `published` was called until 2026-11-10, still taken wherever a status is given)
        return cls.PUBLISHED if value == "checked" else None

    @property
    def published(self) -> bool:
        """A document is published when it has been checked and no errors were found"""
        return self is ReviewStatus.PUBLISHED


class ReviewState(_Camel):
    id: UUID
    type: str
    label: str | None
    status: ReviewStatus
    published: bool
    created_by: list[Creator] = []
    last_edited_by: str | None

    _creators = field_validator("created_by", mode="before")(creators_from)
    reviewed_by: str | None = None
    reviewed_at: datetime.datetime | None = None
    # Who is to review it (anyone may all the same), who said so, and when
    assigned_to: str | None = None
    assigned_by: str | None = None
    assigned_at: datetime.datetime | None = None
    open_comments: int = 0


class Comment(_Camel):
    id: UUID
    username: str
    at: datetime.datetime
    text: str
    # the id of the part of the document it is about, and what the part was called when it was made
    target_id: UUID | None = None
    target_label: str | None = None
    resolved: bool = False
    resolved_by: str | None = None
    resolved_at: datetime.datetime | None = None


class ReviewDetail(ReviewState):
    """The state of a document, and its comments (the open ones, unless more were asked for)"""

    comments: list[Comment] = []


class QueueItem(_Camel):
    id: UUID
    type: str
    label: str | None
    status: ReviewStatus
    created_by: list[Creator] = []
    changed_when: datetime.datetime | None
    reviewed_by: str | None = None
    assigned_to: str | None = None
    open_comments: int = 0

    _creators = field_validator("created_by", mode="before")(creators_from)


class Queue(_Camel):
    results: list[QueueItem]
    count: int
    page: int
    page_size: int
    next_page: int | None
    previous_page: int | None


# --- tasks that are parts of documents ---------------------------------------------------------------------------


class Ref(_Camel):
    """An item, as a chip shows it"""

    type: str
    id: UUID
    label: str | None = None


class Mention(_Camel):
    """An unreconciled mention (`pangloss_review.models.Unreconciled`): what the source calls it, the entity class
    it would be, the document it is directly in and the head of that"""

    id: UUID
    label: str
    unreconciled_type: str
    uris: list[str] = []
    holder: Ref
    head: Ref
    # (who the document is given to, to review)
    assigned_to: str | None = None
    known: list[Ref] = []
    """(of one asked for by its id) The entities that have one of its URIs as their own: who it is, if the URIs
    are right"""


class SimilarMention(Mention):
    """Another mention that may be of the same thing: how alike the labels are (1 for the same after folding), or
    that it names a URI this one names (`same_uri`: then it is the same, whatever it is called)"""

    score: float
    exact: bool
    same_uri: bool = False


class Mentions(_Camel):
    results: list[Mention]
    count: int
    page: int
    page_size: int
    next_page: int | None
    previous_page: int | None


class Reconciled(_Camel):
    """What reconciling a mention did: the entity now in its place; the URIs the entity was given, and those it was
    not (another entity has them); and how many other mentions are being reconciled in the background"""

    id: UUID
    entity: Ref
    head: Ref
    uris_added: list[str] = []
    uris_taken: list[str] = []
    queued: int = 0


class Candidate(Ref):
    """Who an identification could be, and (among alternatives) how likely, in per cent"""

    percent: int | None = None


class Suggestion(_Camel):
    """An identification that a toolchain suggested (`IdentificationByToolchain`): the toolchain, who it could be,
    the document it is directly in and the head of that"""

    id: UUID
    type: str = "IdentificationByToolchain"
    """Its class: `IdentificationByToolchain`, or a project's subclass of it"""
    becomes: str = "Identification"
    """The class it becomes when it is confirmed (`confirmed_as`)"""
    identified_by: str | None = None
    toolchain_version: str | None = None
    uris: list[str] = []
    candidates: list[Candidate] = []
    holder: Ref
    head: Ref
    assigned_to: str | None = None
    known: list[Ref] = []
    """(of one asked for by its id) The entities that have one of its URIs as their own"""


class SimilarSuggestion(Suggestion):
    """Another suggestion of the same person: it names a URI this one names (`same_uri`: the same, whoever its
    candidates are), or has the same candidates, each about as likely"""

    same_uri: bool = False


class Suggestions(_Camel):
    results: list[Suggestion]
    count: int
    page: int
    page_size: int
    next_page: int | None
    previous_page: int | None


class Confirmed(_Camel):
    """What confirming a suggestion did: the URIs its one candidate was given, and those it was not (another entity
    has them); and how many other suggestions are being given the same identification in the background"""

    id: UUID
    head: Ref
    uris_added: list[str] = []
    uris_taken: list[str] = []
    queued: int = 0


class TaskCounts(_Camel):
    """How many tasks there are of each kind: documents to check, mentions to reconcile, identifications to confirm"""

    documents: int = 0
    reconciliations: int = 0
    identifications: int = 0
