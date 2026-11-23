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
import re
from collections.abc import Awaitable, Callable, Generator, Iterable, Mapping
from typing import Any, Literal
from uuid import UUID

logger = logging.getLogger("pangloss.models.hooks")


@dataclasses.dataclass(frozen=True)
class WriteEvent:
    """A committed write to a head node (a Document or an Entity)"""

    # (`computed`: the server wrote what it computes for the head, `Computed()`. Nothing the head says changed: its
    # version is the one it had, and history keeps no record of it)
    op: Literal[
        "create", "update", "delete", "undelete", "merge", "unmerge", "computed"
    ]
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
    # For an update that changed the class of an entity or a document in place (`changing_class_from`): the class
    # it was
    changed_class_from: type | None = None
    # For a write that is part of a merge of two entities, or of the undoing of one (`Entity.merge`): which. The
    # survivor's is an `update` (its fields as the merge wrote them); the absorbed entity's is a `merge` or an
    # `unmerge`, which changes no content (its version is the one it had)
    merge: MergeNote | None = None


@dataclasses.dataclass(frozen=True)
class MergeNote:
    """The merge a write event is part of"""

    id: UUID
    survivor: UUID
    absorbed: UUID
    undone: bool = False


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


# Called before a merge of two entities is made (`Entity.merge`), and before one is previewed: an installed app that
# knows a reason against it raises `PanglossMergeError` with the reason (a typology's types are merged by the
# typology; of two Zotero items the linked one must be the survivor). Each function is given the request, and awaited.
@dataclasses.dataclass(frozen=True)
class MergeRequest:
    survivor: Any
    """The entity that stays, as it is edited (its `EditView`)"""
    absorbed: Any
    survivor_model: type
    absorbed_model: type
    result_model: type
    """The class the survivor will have"""


type BeforeMerge = Callable[[MergeRequest], Awaitable[None]]

before_merge: list[BeforeMerge] = []


async def check_before_merge(request: MergeRequest) -> None:
    for function in before_merge:
        await function(request)


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
# the work (see `pangloss_cypher.pending`). With no function, or none that gives a kind, a write marks nothing. A kind
# whose marking depends on what the one write said is `instructed_work`'s instead (below).
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


# --- the instructions of one write ----------------------------------------------------------------------------------
#
# What a write itself says about the work that is to follow it (`save(instructions={"suggest": False})`, or
# `?suggest=false` of the API's create and update routes): an instruction about **that write**, not a property of what
# is written, so a later write that says nothing is as if it never had. An installed app declares each instruction it
# reads (`declare_write_instruction`, when its module is imported: before the API's routes are made, which take the
# declared names as query parameters, and only those); a write that says one no app declares, or a value its
# declaration does not have, is refused before anything is written (`PanglossInstructionError`, a 422 over the API).
@dataclasses.dataclass(frozen=True)
class WriteInstruction:
    name: str
    """In snake_case (the API takes camelCase too, as for every parameter)"""
    values: tuple[str, ...]
    """What it may say, as text (`("true", "false")`; a `bool` given in Python is `"true"` or `"false"`)"""
    description: str = ""


write_instructions: dict[str, WriteInstruction] = {}

# (the query parameters the model write routes already have: an instruction may not take one's name)
WRITE_PARAMETERS = frozenset(
    {
        "detail",
        "created_by",
        "toolchain",
        "toolchain_version",
        "toolchain_date",
        "acknowledge_citations",
        "published",
        "review_status",
        "review_assigned_to",
    }
)

_SNAKE_CASE = re.compile(r"[a-z][a-z0-9]*(_[a-z0-9]+)*")


def declare_write_instruction(instruction: WriteInstruction) -> WriteInstruction:
    """Declare an instruction that writes may give. The same declaration again is nothing (a module imported twice);
    another of the same name, a name that is not snake_case, one that is a parameter the write routes already have,
    or no values raise `PanglossModelError`"""
    from pangloss_models.exceptions import PanglossModelError

    name = instruction.name
    if not _SNAKE_CASE.fullmatch(name):
        raise PanglossModelError(
            f"The instruction of a write {name!r} is to be named in snake_case"
        )
    if name in WRITE_PARAMETERS:
        raise PanglossModelError(
            f"{name!r} cannot be an instruction of a write: the write routes already have a parameter of that name"
        )
    if not instruction.values or not all(
        isinstance(value, str) for value in instruction.values
    ):
        raise PanglossModelError(
            f"The instruction of a write {name!r} needs the values it may say, as text"
        )
    declared = write_instructions.get(name)
    if declared is not None and declared != instruction:
        raise PanglossModelError(
            f"The instruction of a write {name!r} is declared twice, differently: {declared} and {instruction}"
        )
    write_instructions[name] = instruction
    return instruction


def checked_instructions(said: Mapping[str, Any] | None) -> dict[str, str]:
    """What a write said, checked against what is declared, each value as text (`None`: nothing said, `{}`). Raises
    `PanglossInstructionError` for a name no app declares, or a value its declaration does not have"""
    from pangloss_models.exceptions import PanglossInstructionError

    if not said:
        return {}
    checked: dict[str, str] = {}
    for name, value in said.items():
        instruction = write_instructions.get(name)
        if instruction is None:
            declared = ", ".join(sorted(write_instructions)) or "none is declared"
            raise PanglossInstructionError(
                f"{name!r} is no instruction of a write (the instructions are: {declared})"
            )
        text = ("true" if value else "false") if isinstance(value, bool) else value
        if not isinstance(text, str) or text not in instruction.values:
            raise PanglossInstructionError(
                f"The instruction {name!r} of a write is one of {', '.join(instruction.values)}, not {value!r}"
            )
        checked[name] = text
    return checked


# Work whose being left pending depends on what the write said (`pangloss-reconcile`: whether a save sets its worker
# off is a project setting that a write's instruction overrides either way). Each function is given the class of the
# head written and the instructions of the write, checked (**an empty mapping when the write said none**: the
# function still answers, by its setting), and answers, by kind of work, `True` (the head is marked pending for it, as
# a kind of `pending_work` is: `before` kept if the kind is in `pending_keeps_before`, a kind in the writer's `less`
# left alone) or `False` (**a mark of that kind the head already has is taken off**, in the write's transaction, claimed
# or not: `pangloss_cypher.pending.unmark`); a kind it does not name is left as it is. Applied after the kinds of
# `pending_work`.
#
# It is asked **only by a create and an update of a head** (and, in a create or update, for each entity the write
# makes, by the entity's class, with the same instructions): never by a delete, an undelete, a merge or its undoing, a
# relink, a change of review status or of publication, a computed write, a derived conversion. A restore from history
# is an ordinary update that says no instructions (asked with an empty mapping). An app whose work depends on what a
# write said uses this **instead of** `pending_work` for that kind. With no function, a write runs nothing more. It is
# asked in the write's transaction, which may be run again (a transient error, a lost race): it may be asked twice for
# one write, and must answer the same, quickly, without reading or writing anything itself.
type InstructedWorkFor = Callable[[type, Mapping[str, str]], Mapping[str, bool]]

instructed_work: list[InstructedWorkFor] = []


def instructed_kinds(model: type, instructions: Mapping[str, str]) -> dict[str, bool]:
    """What the functions of `instructed_work` answer for a write of a head of the class with these instructions (of
    two that answer one kind, the later)"""
    answers: dict[str, bool] = {}
    for function in instructed_work:
        answers.update(function(model, instructions))
    return answers


# The kinds of work whose mark keeps what an update took away: the ids of the entities the head's tree referred to
# before the update, and the labels of its nodes (`pangloss_cypher.pending`, "What an update took away"). An update of
# a class that leaves such a kind reads its old tree once more, in its transaction. An app adds its kind here.
pending_keeps_before: set[str] = set()


# Work was marked by something that is not a write (a change of the review status of a document, or of whether it is
# published: `pangloss_cypher.review`, `set_published_in_db`). A write tells `after_write`, which a worker listens to
# so that it starts at once; these tell `work_marked`, after they have committed, with the class of the head. A
# listener must be quick; one that raises is logged.
work_marked: list[Callable[[type], None]] = []


def emit_work_marked(model: type) -> None:
    for listener in work_marked:
        try:
            listener(model)
        except Exception:
            logger.exception("A listener to marked work failed for %s", model.__name__)


# Classes whose references do not count: an entity that only items of such a class refer to is not "referred to"
# (in the count of what uses it, in a list of only what is used, and in the check before it is deleted).
# `pangloss-derived` gives its derived document classes: what they name is what the documents they rest on name, and
# an entity whose last mention a person has removed could otherwise not be deleted until the worker had run. Each
# function gives the names of classes (the labels of their head nodes).
references_not_counted: list[Callable[[], Iterable[str]]] = []


def uncounted_classes() -> list[str]:
    """The names of the classes whose references to an entity do not count, sorted"""
    names: set[str] = set()
    for function in references_not_counted:
        names.update(function())
    return sorted(names)


# Whether there are edges between entities that are of no field of the models (`pangloss-derived`: a class with
# `DerivedEdge.Meta(shortcut=True)` keeps one beside each derived edge, marked `derived: true`). The core leaves such
# an edge out of every query that takes any edge between two items (`pangloss_cypher.fragments.model_edge`). Where
# the test would cost something for everybody (a count of all the edges of all the items of a class, which orders
# what is offered while typing), it is made only when a function here says there are such edges.
edges_of_no_field: list[Callable[[], bool]] = []


def has_edges_of_no_field() -> bool:
    return any(function() for function in edges_of_no_field)


# A citation of something that cannot itself be cited (`pangloss-derived`: a derived document, which its worker must
# be free to change and delete): an installed app says what is cited in its place. Each function is given the class
# and the id of what a citation names, and gives None (it is cited as it is) or a `ResolvedCitation`: the documents
# it rests on, which are cited instead, and what to record of what was chosen. The citation is then written as a
# `PGCitedBasis` (`pangloss_models.citations`). `tx`: the transaction of the write, when it is asked again there
# (what a write sends as a basis has to be what this says it is, or one the document has already); None when the
# payload is first read, and it reads for itself. An app that adds a function calls `citations.enable_cited_basis()`.
@dataclasses.dataclass(frozen=True)
class ResolvedCitation:
    targets: tuple[tuple[str, str], ...]
    """What is cited instead: the (class, id) of each document node"""
    rule: str | None = None
    key: str | None = None
    label: str | None = None
    via: tuple[str, UUID] | None = None
    """What is recorded as chosen (class, id), when it is not what the citation named: for a part of something that
    is cited through what it rests on, the whole (so that the basis is found by it when the whole changes or goes).
    Asked again with this, an app must give the same"""


type CitationResolver = Callable[[str, UUID, Any], Awaitable[ResolvedCitation | None]]

resolve_citation: list[CitationResolver] = []


async def resolved_citation(
    type_name: str, id: UUID, tx: Any = None
) -> ResolvedCitation | None:
    for function in resolve_citation:
        found = await function(type_name, id, tx)
        if found is not None:
            return found
    return None


# A cited basis was marked (what it was made of has changed, or is gone: `pangloss_cypher.citations.mark_via`), or
# its mark was cleared because that is back. Each function is told, after the write that marked it has committed,
# of each document that cites through it (`pangloss-review` gives the document a task). One that raises is logged.
@dataclasses.dataclass(frozen=True)
class CitationMark:
    via_id: UUID
    state: str
    """`changed`, `lost`, or `""` (cleared)"""
    head_id: UUID
    """The document that cites through it"""
    head_type: str
    basis_id: UUID


citation_marked: list[Callable[[CitationMark], None]] = []


def emit_citation_marks(marks: Iterable[CitationMark]) -> None:
    for mark in marks:
        for listener in citation_marked:
            try:
                listener(mark)
            except Exception:
                logger.exception(
                    "A listener to marked citations failed for %s", mark.head_id
                )


# Something an installed app says of a document that a person should look at (`pangloss-derived`: it was made from a
# derived document), or of a part of it (a derivation it cites no longer holds). Given in the transaction of the
# write it comes from, so that it is there if and only if the write is; the transaction may be run again, so a
# function does only what can be done twice. `pangloss-review` makes it an open comment on the document, which is
# resolved as any comment is. `clears`: the kinds of notice about the same part that no longer hold.
@dataclasses.dataclass(frozen=True)
class Notice:
    head_id: UUID
    head_type: str
    kind: str
    """What it says, as a name (`derivation_lost`); empty: nothing new is said, and only `clears` is done"""
    text: str = ""
    """What it says, in words"""
    target_id: UUID | None = None
    """The part of the document it is about (None: the document)"""
    target_label: str | None = None
    clears: tuple[str, ...] = ()
    user: str | None = None
    """Who did what it comes from (None: nobody; something working in the background)"""


notices: list[Callable[[Any, Notice], Awaitable[None]]] = []


async def give_notice(tx: Any, notice: Notice) -> None:
    for function in notices:
        await function(tx, notice)


# A stand-in was resolved: an entity was put in its place (`pangloss-review` reconciling an `Unreconciled`;
# `pangloss-criteria` resolving a `MatchesCriteria`, once for each place it fills). Raised by a package that has a route
# of its own for putting an entity in a stand-in's place, **after** the write of the document has returned, outside any
# transaction: so a listener may write to the database (which a listener of `after_write` may not). A write that
# failed raises nothing. Each function is awaited in turn, in the request (or the background work) that made the
# write: a slow one slows it, so keep it to one small write. One that raises is logged, and the others are still told;
# the caller never fails for it.
#
# `direct`: whether it is the stand-in the person had open, or one resolved along with it (the other mentions
# reconciled in one go, another place of the same one).
#
# It tells of resolutions made through a package's own route, and of nothing else: an edit of a form that replaces a
# stand-in, a restore from history, an update through the SDK or by a toolchain raise nothing. A listener must not rely
# on hearing of every stand-in that goes.
@dataclasses.dataclass(frozen=True)
class Resolution:
    stand_in_id: UUID
    stand_in_type: str
    """The class of the stand-in's node (`Unreconciled`, or the use of a generic wrapper as its node names it)"""
    head_id: UUID
    head_type: str
    entity_id: UUID
    entity_type: str
    user: str
    at: datetime.datetime
    direct: bool
    label: str | None = None
    """The stand-in's label, if it has one"""
    stood_for: str | None = None
    """The class it stood for, if it says (the property `StandIn.named_type` names)"""


resolved: list[Callable[[Resolution], Awaitable[None]]] = []


async def tell_resolved(resolution: Resolution) -> None:
    """Tell each of `resolved` that a stand-in was resolved. A listener that fails is logged, and the others are
    still told"""
    for listener in list(resolved):
        try:
            await listener(resolution)
        except Exception:
            logger.exception(
                "A listener to resolved stand-ins failed for %s in %s %s",
                resolution.stand_in_id,
                resolution.head_type,
                resolution.head_id,
            )


# What an installed app does in the transaction of a write of a head node, with what the write did (create, update,
# delete, undelete): so that it is done if and only if the write is (`pangloss-derived` marks the citations made
# through a derived document when its worker changes or deletes it). Awaited, in the transaction, which may be run
# again: it must do only what can be done twice. One that raises fails the write.
type InWrite = Callable[[Any, str, type, UUID], Awaitable[None]]

in_write: list[InWrite] = []

_class_changed_from: contextvars.ContextVar[type | None] = contextvars.ContextVar(
    "pangloss_class_changed_from", default=None
)


def class_changed_from() -> type | None:
    """For a function of `in_write`: the class the head was, if this update changes its class in place
    (`changing_class_from`); `model` is the class it is now. None for any other write"""
    return _class_changed_from.get()


async def run_in_write(
    tx: Any, op: str, model: type, id: UUID, changed_class_from: type | None = None
) -> None:
    token = _class_changed_from.set(changed_class_from)
    try:
        for function in in_write:
            await function(tx, op, model, id)
    finally:
        _class_changed_from.reset(token)


# Properties of a head node that an update keeps as they are, besides those the database keeps itself (whether it is
# published, its review state): the names an installed app gives. One is kept only by an update that does not itself
# write a property of that name: so what a class writes of its own (a `DBField`) is written, and stays on the node
# when its class is changed to one that has no such field (`pangloss-derived`: the rule that made a document that a
# person has since made their own).
kept_head_properties: list[str] = []


# Classes that people do not write: a class whose items something else makes and keeps (`pangloss-derived`: a derived
# document, which its worker writes from what a rule finds). Each function is given a model class, and says whether it
# is one of them. Such a class is read, listed and searched as any other; the API gives it no `POST`, and the export
# says it is not created directly, so that the interface offers no "New" (`written_by_people`). Refusing a write that
# a person makes all the same is the package's own to do (in `in_write`, where it knows who is writing).
type NotWrittenByPeople = Callable[[type], bool]

not_written_by_people: list[NotWrittenByPeople] = []


def written_by_people(model: type) -> bool:
    """Whether people make items of the class (no installed app says that it alone does)"""
    return not any(function(model) for function in not_written_by_people)


# Stand-ins: a document that a relation takes in the place of an entity. A package says which document class may stand
# in for which entity classes, and every relation that takes such an entity takes the document too (`pangloss-review`:
# an `Unreconciled`, for someone a source names who has not been identified, where a `Person` goes). The core knows
# only this: the option is added when the fields are analysed (`build_relation_options`), with the names of the entity
# classes it stands for there (`RelationToDocument.stands_in_for`, exported as `standsInFor`), and a value given for
# it is checked against them (`check`, on `Create` and `Update`).
#
# A stand-in may also be a **generic wrapper** with one type variable (`pangloss-criteria`: `MatchesCriteria[T]`, a
# reified relation). The relation then takes the use of it with the entity classes it stands for as its parameter: a
# relation to `Agent` (a `Person` or a `Group`) takes `MatchesCriteria[Group | Person]`, an option as it would be had
# the annotation said it, with the edge model of the relation. That use is made when the fields are analysed. A field
# whose annotation writes a use of the wrapper out has that one alone. There is no `stands_in_for` and no `check`
# for it: the wrapper's own validators know what its parameter stands for (`classes_stood_for`).
#
# Nothing is given in the place of an entity of a computed relation, nor of what a type variable stands for that
# only computed relations are of (the candidates of a `MatchesCriteria[Person]` are people), nor of what a generic
# stand-in itself holds.
@dataclasses.dataclass(frozen=True)
class StandIn:
    # The name of the class, a document or a generic wrapper (found among the declared models when the fields are
    # analysed: none of that name, no stand-in)
    document: str
    # Whether it may stand in for this entity class
    stands_for: Callable[[type], bool]
    # Called with a value of the document given for a relation, and the names of the entity classes it stands for
    # there: raises `ValueError` if the value cannot stand for any of them
    check: Callable[[Any, frozenset[str]], None] | None = None
    # A field with a marker of this class (`Annotated[Person, NoUnreconciled()]`) does not take the stand-in
    refused_by: type | None = None
    # The name of a property of the document that holds the name of the one entity class a value stands for
    # (`pangloss-review`'s `unreconciled_type`); None if the document does not say (it stands for whatever its field
    # takes). For a package that works from a write plan and must know what each stand-in in it stands for
    named_type: str | None = None


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


# --- migrations: what an app keeps that a change of the models makes wrong ------------------------------------------
#
# An app may keep, in the database, data that names classes and fields (`pangloss-criteria`: the stored search pattern
# of a description). A migration that renames a field has to rename it there too. The backend that applies the
# migrations gives each change of the data to `migration_changes`, **in the transaction that makes it**: so the app's
# rewrite is done if and only if the change is, whether the migration is one transaction or many (it is not always
# one: a change of an index or a constraint is made between transactions, and a migration in batches is many).
# A change made in batches is given once, after its last batch, in a transaction of its own; a change to the
# database itself (an index, a constraint) is not given.
#
# A function is awaited with the backend's transaction and a `MigrationStep`. It may be run again for the same change
# (a transaction that is retried, a batched migration that stopped just after): it must do only what can be done
# twice. One that raises fails the migration. The models of the code are those of the END of the migrations, not of
# this change: read `step.before` and `step.after` (the snapshots), not the classes.
@dataclasses.dataclass(frozen=True)
class MigrationStep:
    change: Any
    """The change (`pangloss_models.migrations.changes`). Of a migration that is undone, the change that undoes"""
    before: dict[str, Any]
    """The snapshot of the models before the change"""
    after: dict[str, Any]
    """And after it"""
    migration: str | None = None
    """`app.name` of the migration it is of (None: changes applied on their own)"""
    undoing: bool = False
    """Whether the migration is being undone"""
    dry_run: bool = False
    """Whether the transaction will be rolled back (`migrate --dry-run`)"""


type InMigration = Callable[[Any, MigrationStep], Awaitable[None]]

migration_changes: list[InMigration] = []


async def run_in_migration(tx: Any, step: MigrationStep) -> None:
    for function in migration_changes:
        await function(tx, step)


# After `pangloss migrate` has applied or undone migrations (and they have committed): what an app checks or works
# out again of its own data, with the models as they now are. `complete` says whether the database is now where the
# code's models are (nothing left to apply, nothing undone): only then do the classes of the code describe the data.
# Awaited with the database connected, outside any transaction. One that raises is reported, and the migrations stay
# applied.
@dataclasses.dataclass(frozen=True)
class Migrated:
    migrations: tuple[str, ...]
    """`app.name` of each, in the order they were applied (or undone)"""
    changes: tuple[Any, ...]
    """Their changes, in order"""
    affected: tuple[str, ...]
    """The names of the models whose stored data the changes could have altered"""
    complete: bool
    undone: bool = False


after_migrate: list[Callable[[Migrated], Awaitable[None]]] = []


async def run_after_migrate(migrated: Migrated) -> None:
    for function in after_migrate:
        await function(migrated)
