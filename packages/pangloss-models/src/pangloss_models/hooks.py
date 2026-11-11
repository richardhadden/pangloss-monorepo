"""What happens after a write: a way for an installed app to react to it.

A database module calls `emit_write_event` **after** a write to a head node has committed
(never inside the transaction, which may be run again). Whoever wants to know of writes
(such as `pangloss-history`) adds a function to `after_write`. With none, nothing is done.

A listener is called at once, in the request that made the write, so it must be quick (put
the work on a queue). One that raises is logged and ignored: a listener never fails a write.
"""

import contextlib
import contextvars
import dataclasses
import datetime
import logging
from collections.abc import Awaitable, Callable, Generator, Iterable
from typing import Any, Literal
from uuid import UUID

logger = logging.getLogger("pangloss.models.hooks")


@dataclasses.dataclass(frozen=True)
class WriteEvent:
    """A committed write to a head node (a Document or an Entity)"""

    op: Literal["create", "update", "delete", "undelete"]
    # The model, as `Document` or `Entity` subclass
    model: type
    id: UUID
    # The version of the head node: the one this write made (create is 1, an update is one
    # more than before). A delete or undelete changes no content, and the version is
    # the one it had at the time
    version: int
    user: str
    at: datetime.datetime
    # The validated write form (the `CreateDB` or `UpdateDB` instance), with the ids of
    # everything in it. `None` for delete and undelete
    payload: Any | None = None
    # The entities that this write made, named in a document with `create_new` and not
    # there before: each is the `CreateDB` instance of an entity, and a head node of its own,
    # at version 1
    created_entities: tuple[Any, ...] = ()
    # For an update that put an earlier version back (`history`): the version it came from
    restored_from: int | None = None
    # For an update that changed the class of an entity (`changing_class_from`): the class it was
    changed_class_from: type | None = None


type WriteListener = Callable[[WriteEvent], None]

after_write: list[WriteListener] = []


def emit_write_event(event: WriteEvent) -> None:
    """Tell each of `after_write` of a write. A listener that fails is logged, and the
    others are still told"""
    # (what was written, never what it said)
    logger.info(
        "Write: %s %s %s v%s by %r",
        event.op,
        event.model.__name__,
        event.id,
        event.version,
        event.user,
    )
    for listener in after_write:
        try:
            listener(event)
        except Exception:
            logger.exception(
                "A listener to writes failed for %s %s %s",
                event.op,
                event.model.__name__,
                event.id,
            )


# Properties for a new head node, which an installed app adds (`pangloss-review` writes `published: false` for
# a document that is to be reviewed). Each function is given the class (a `Document` or `Entity` subclass) and
# gives a dict, which may be empty. They are written with the node, in the same transaction as the creation, so
# there is no moment when the node is there without them. An update does not call them (it keeps the
# properties the node has: see `KEPT_PROPERTIES` of the Memgraph backend).
type HeadPropertiesFor = Callable[[type], dict[str, Any]]

new_head_properties: list[HeadPropertiesFor] = []


def properties_for_new_head(model: type) -> dict[str, Any]:
    """What the installed apps want written on a new head node of the class"""
    properties: dict[str, Any] = {}
    for function in new_head_properties:
        properties.update(function(model))
    return properties


# The same for an update: properties that this one update puts on the head node, over those it keeps
# (`pangloss-review` does so when the writer asked for a review status). Usually empty.
updated_head_properties: list[HeadPropertiesFor] = []


def properties_for_updated_head(model: type) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    for function in updated_head_properties:
        properties.update(function(model))
    return properties


# Work that an installed app does later, in the background, after a write (`pangloss-derived` works out again what
# the rules derive from a document). Each function is given the class of a head node that is written (a `Document` or
# `Entity` subclass) and gives the kinds of work its writes need (`["derive"]`), or none. The database marks the head
# node as pending for each kind, in the transaction of the write (create, update, delete, undelete), so that a write
# that is committed is never forgotten, however the server stops; the app's worker claims the pending heads and does
# the work (see `pangloss_cypher.pending`). With no function, or none that gives a kind, a write marks nothing.
type PendingWorkFor = Callable[[type], Iterable[str]]

pending_work: list[PendingWorkFor] = []


def pending_kinds(model: type) -> list[str]:
    """The kinds of work a write of a head node of the class leaves pending"""
    kinds: list[str] = []
    for function in pending_work:
        for kind in function(model):
            if kind not in kinds:
                kinds.append(kind)
    return kinds


# Stand-ins: a document that a relation takes in the place of an entity. A package says which document class may stand
# in for which entity classes, and every relation that takes such an entity takes the document too (`pangloss-review`:
# an `Unreconciled`, for someone a source names who has not been identified, where a `Person` goes). The core knows
# only this: the option is added when the fields are analysed (`build_relation_options`), with the names of the entity
# classes it stands for there (`RelationToDocument.stands_in_for`, exported as `standsInFor`), and a value given for
# it is checked against them (`check`, on `Create` and `Update`).
@dataclasses.dataclass(frozen=True)
class StandIn:
    # The name of the document class (found among the declared models when the fields are analysed: none of that
    # name, no stand-in)
    document: str
    # Whether it may stand in for this entity class
    stands_for: Callable[[type], bool]
    # Called with a value of the document given for a relation, and the names of the entity classes it stands for
    # there: raises `ValueError` if the value cannot stand for any of them
    check: Callable[[Any, frozenset[str]], None] | None = None
    # A field with a marker of this class (`Annotated[Person, NoUnreconciled()]`) does not take the stand-in
    refused_by: type | None = None


stand_ins: list[StandIn] = []


# What an installed app adds to the JSON of a head node read by the API (`GET /api/Person/{id}`): each function is
# given the class and the view, and gives a dict of keys to add (`pangloss-derived` gives `_derived`, what the rules
# derive about it), or none. Awaited. Only the API's response has them: a view read in Python (`Person.get`) does not.
type HeadViewExtras = Callable[[type, Any], Awaitable[dict[str, Any]]]

head_view_extras: list[HeadViewExtras] = []


# What an installed app gives the interface's translation files besides the models and enums (`pangloss-derived`
# gives its derived classes): each function gives a list of `TranslatableModel`, put under "models" as a model is, in
# the file of the app whose module it is.
@dataclasses.dataclass(frozen=True)
class TranslatableModel:
    name: str
    module: str
    kind: str
    description: str = ""
    # field name -> (name, help) in the default language
    fields: dict[str, tuple[str, str]] = dataclasses.field(default_factory=dict)
    # names of the things others call it, as a model's incoming relations are
    incoming: tuple[str, ...] = ()


translatable_models: list[Callable[[], Iterable[TranslatableModel]]] = []


# The review status that a write asks for (`save(review_status="published")`, or `?review_status=` of the API),
# for data that is known to be right when it is loaded. The core does not know what it means: `pangloss-review`
# reads it in its functions above, for documents of the classes it reviews. None: nothing asked.
requested_review_status: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "requested_review_status", default=None
)


# (until 2026-11-10 the status of a published document was called `checked`: still taken, wherever a status is given)
REVIEW_STATUS_SYNONYMS = {"checked": "published"}


def review_status_name(status: str | None) -> str | None:
    """A review status as it is stored: `checked`, its earlier name, is `published`"""
    return REVIEW_STATUS_SYNONYMS.get(status, status) if status is not None else None


def review_status_asked(
    published: bool | None = None, review_status: str | None = None
) -> str | None:
    """`published=True` is `published` and `published=False` is `unchecked`; `review_status` says it in full.
    Both may not be given (they could disagree)."""
    if published is not None and review_status is not None:
        raise ValueError("Give published or review_status, not both")
    if published is not None:
        return "published" if published else "unchecked"
    return review_status_name(review_status)


@contextlib.contextmanager
def requesting_review_status(status: str | None) -> Generator[None]:
    """The writes made inside the block ask for this review status (None leaves what is asked outside it)"""
    if status is None:
        yield
        return
    token = requested_review_status.set(review_status_name(status))
    try:
        yield
    finally:
        requested_review_status.reset(token)


# Who a write asks to review the new document (`save(review_assigned_to="ann")`, `?review_assigned_to=` of the API):
# as with the status, the core does not know what it means, and `pangloss-review` reads it for the classes it reviews.
requested_review_assignee: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "requested_review_assignee", default=None
)


@contextlib.contextmanager
def requesting_review_assignee(username: str | None) -> Generator[None]:
    """The documents created inside the block are assigned to this user to review (None leaves what is asked
    outside it)"""
    if username is None:
        yield
        return
    token = requested_review_assignee.set(username)
    try:
        yield
    finally:
        requested_review_assignee.reset(token)


# What the database returns, made into what the models read.
#
# A database returns its own types (Memgraph's driver, `neo4j.time.DateTime`). The models do
# not know which database they have: the database module adds a function here that
# converts a value it knows of, and the models call `convert_from_database` on what they are
# made from. With none, the data is as it is.
#
# `convert_from_database` walks the dicts and lists itself and gives each converter the values
# in them (a converter that walks on its own account is given nothing to walk). What it has been
# through is marked, so that the models nested in a document, each of which converts what it is
# made from, do not walk their subtree again: a read of a document nested 60 deep took a second,
# nearly all of it converting the same values over and over (O(nodes x depth)).
type FromDatabaseConverter = Callable[[Any], Any]

from_database: list[FromDatabaseConverter] = []


class _Converted(dict):
    """A dict that `convert_from_database` has been through, with everything in it"""


def convert_from_database(data: Any) -> Any:
    if not from_database or isinstance(data, _Converted):
        return data
    return _convert(data)


def _convert(data: Any) -> Any:
    if isinstance(data, _Converted):
        return data
    if isinstance(data, dict):
        return _Converted((key, _convert(value)) for key, value in data.items())
    if isinstance(data, list):
        return [_convert(value) for value in data]
    for converter in from_database:
        data = converter(data)
    return data
