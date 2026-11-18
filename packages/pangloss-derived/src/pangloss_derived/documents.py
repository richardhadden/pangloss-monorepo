"""Derived documents: a document class whose documents a rule writes, from what other documents say. See
implementation_docs/derived.md ("Derived documents").

    class DerivedFactoid(Document, DerivedDocument):
        '''What follows from what other factoids say'''
        sources: list[DerivedFrom[Factoid]]       # written by the worker: the documents its justification rests on
        statements: list[Statement]

    @rule(types=[family])
    def siblings(a: Var[Person], b: Var[Person], p: Var[Person]):
        return DerivedFactoid.Derive(statements=[Sibling.Template(people=[a, b])]).when(
            ChildOf.Where(child=a, parent=p),
            ChildOf.Where(child=b, parent=p),
            unordered(a, b),
        )

Here: the trait and its settings, which classes are derived documents, and who may write one (nobody but the worker).
The templates are in `pangloss_derived.templates`, the checks of a rule in `pangloss_derived.check`.
"""

import contextlib
import contextvars
import dataclasses
import uuid
from collections.abc import Generator
from typing import Annotated, Any, ClassVar
from uuid import UUID

from pangloss_models import (
    DBField,
    Document,
    ModelRegistry,
    Trait,
    create_validator,
    register_meta_slot,
    update_validator,
)
from pangloss_models.exceptions import PanglossWriteError
from pangloss_models.field_definitions import (
    RelationFieldDefinition,
    RelationToCitation,
)

from pangloss_derived.registry import PanglossDerivedError

SLOT = "_derived_document_meta"


@dataclasses.dataclass(frozen=True)
class DerivedDocumentMeta:
    """The settings of a derived document class (`_derived_document_meta = DerivedDocumentMeta(...)`); none is needed.

    - `max_per_seed`: the most documents one written document may give for a rule of this class; past it, those of
      that document are not written, and it is logged (a safeguard against a rule, or data, that would fill the
      database: a rule of pairs over a family of 50 is 1,225 documents);
    - `converts_to`: the classes a derived document of this class can be made into ("make this a document of my
      own"); by default, the classes people write that share a parent with it."""

    max_per_seed: int = 2_000
    converts_to: tuple[type, ...] | type | None = None

    def __post_init__(self) -> None:
        if self.max_per_seed < 1:
            raise ValueError("max_per_seed is at least 1")
        if isinstance(self.converts_to, type):
            object.__setattr__(self, "converts_to", (self.converts_to,))
        elif self.converts_to is not None:
            object.__setattr__(self, "converts_to", tuple(self.converts_to))


register_meta_slot(SLOT, DerivedDocumentMeta)


# ---------------------------------------------------------------------------
# Who is writing
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Writing:
    """What the worker is writing a derived document for: the rule, and the labels of what its justification passed
    through (`derived_context`). And what it writes with it: the id of the document (those of the nodes in it are
    worked out from it), whether it is published, and the hash of its content"""

    rule: str
    context: tuple[str, ...] = ()
    id: UUID | None = None
    published: bool | None = None
    content: str | None = None


_writing: contextvars.ContextVar[Writing | None] = contextvars.ContextVar(
    "pangloss_derived_writing", default=None
)


@contextlib.contextmanager
def writing_derived(
    rule: str,
    context: tuple[str, ...] | list[str] = (),
    *,
    id: UUID | None = None,
    published: bool | None = None,
    content: str | None = None,
) -> Generator[None]:
    """Inside the block, derived documents are written: as the worker does, for the rule `rule`. Every write of one
    outside such a block is refused. What is written records the rule and the context (`derived_by`,
    `derived_context`).

    `id`: the id the document is given (and with it the ids of the nodes in it, each worked out from this id and
    where the node is: so a document written again has the nodes it had). `published`: whether it is (None: as a
    document of its class is when made, and as it is when changed). `content`: what the worker keeps on the head to
    know the document by, when it looks again whether anything has changed"""
    token = _writing.set(Writing(rule, tuple(context), id, published, content))
    try:
        yield
    finally:
        _writing.reset(token)


def writing() -> Writing | None:
    return _writing.get()


class PanglossDerivedDocumentError(PanglossWriteError):
    """A write of a derived document by anyone but the worker: it is made, changed and deleted only by what derives
    it"""


# ---------------------------------------------------------------------------
# The trait
# ---------------------------------------------------------------------------


_enabled_here: list[bool] = []


def forget_cited_basis() -> None:
    """(When the models are emptied, as between tests) the cited basis this package asked for goes with the derived
    document classes that asked"""
    from pangloss_models import citations

    if _enabled_here:
        _enabled_here.clear()
        citations._basis_enabled = False


class DerivedDocument(Trait):
    """Makes a document class one whose documents a rule writes: `class DerivedFactoid(Document, DerivedDocument)`,
    with one field of `DerivedFrom` (`sources: list[DerivedFrom[Factoid]]`). It carries what the worker records on
    each: the rule that made it, and what its justification passed through.

    Nobody writes one but the worker; it is read, listed, searched, labelled and exported as any document."""

    # (read with every reference to one, and so in a list or a search's results: what marks it as derived)
    reference_view_fields: ClassVar[tuple[str, ...]] = ("derived_by", "derived_context")

    derived_by: Annotated[str | None, DBField] = None
    """The name of the rule that made it. (A search for derived documents, or for those of one rule, is by this)"""
    derived_context: Annotated[list[str], DBField] = []
    """The labels of the semantic spaces (and other qualifying wrappers) its justification passed through, which its
    rule allows (`.when(..., allow=[...])`); empty for a plain one"""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # (a derived document can be cited: what is saved is citations of what it rests on, a cited basis. So a
        # project that has a derived document class has the class of one; others are as they were)
        from pangloss_models import citations

        if not citations._basis_enabled:
            citations.enable_cited_basis()
            _enabled_here.append(True)

    @create_validator
    @update_validator
    def record_the_derivation(self):
        # (on the models written to the database: what the worker is writing it for. With none, the write is one
        # that `refuse_other_writers` refuses, in its transaction)
        record_the_derivation(self)


def record_the_derivation(item: Any) -> None:
    current = _writing.get()
    if current is None:
        return
    item.derived_by = current.rule
    item.derived_context = list(current.context)
    if current.id is not None:
        item.id = current.id
        give_ids(item, current.id, "")


# (never changed: the ids of the nodes of every derived document are made with it)
NODE_IDS = uuid.UUID("6f0c7a52-41de-5b61-9d55-0d1b2c0a7e11")


def node_id(document: UUID, path: str) -> UUID:
    """The id of a node of a derived document: of the document's id and where the node is in it (`statements/0`)"""
    return uuid.uuid5(NODE_IDS, f"{document}/{path}")


def give_ids(item: Any, document: UUID, path: str) -> None:
    """Give each node below `item` (a model that is written: the nested documents, the wrappers, the embedded
    objects, the citations) the id worked out from where it is. A template gives no ids, and a rule that reads a
    derived document has the ids of what it matched in the keys of its own justifications: with new ids at each
    write, everything derived from it would be deleted and made again. (A reference to an entity is not a node of
    the document: its id is the entity's)"""
    from pangloss_models.model_bases.base_models import _CreateDBBase, _UpdateDBBase

    def below(value: Any, where: str) -> None:
        if isinstance(value, (list, tuple)):
            for index, member in enumerate(value):
                below(member, f"{where}/{index}")
        elif isinstance(value, (_CreateDBBase, _UpdateDBBase)):
            if getattr(value, "create_new", None):
                return
            value.id = node_id(document, where)
            give_ids(value, document, where)

    for name in type(item).model_fields:
        below(getattr(item, name, None), f"{path}/{name}" if path else name)


def head_properties(model: type) -> dict[str, Any]:
    """(`hooks.new_head_properties`, `hooks.updated_head_properties`) what the worker puts on the head of a derived
    document it writes, in the transaction of the write: whether it is published, and the hash of its content"""
    current = _writing.get()
    if current is None or not is_derived_document(model):
        return {}
    properties: dict[str, Any] = {}
    if current.published is not None:
        properties["published"] = current.published
    if current.content is not None:
        properties[CONTENT] = current.content
    return properties


# The property of the head of a derived document that keeps the hash of what the worker wrote
CONTENT = "pg_derived_content"


def is_derived_document(model: Any) -> bool:
    """Whether the class is a derived document class (a document class with the trait)"""
    return (
        isinstance(model, type)
        and issubclass(model, DerivedDocument)
        and issubclass(model, Document)
    )


def derived_document_classes() -> list[type]:
    """The derived document classes of the models (concrete or abstract), in the order declared"""
    return [m for m in ModelRegistry._models if is_derived_document(m)]


def concrete_class_names() -> list[str]:
    """The names of the derived document classes that documents are of"""
    classes: list[Any] = derived_document_classes()
    return [m.__name__ for m in classes if not m._meta.abstract]


def settings_of(model: type) -> DerivedDocumentMeta:
    meta = getattr(model, SLOT, None)
    return meta if isinstance(meta, DerivedDocumentMeta) else DerivedDocumentMeta()


def source_fields(model: Any) -> dict[str, RelationToCitation]:
    """The fields of the class that are of `DerivedFrom` (a citation that does not protect), each with what it says
    of what it takes"""
    found: dict[str, RelationToCitation] = {}
    for name, definition in model._meta.fields.items():
        if not isinstance(definition, RelationFieldDefinition):
            continue
        if not is_derived_from(definition.annotated_type):
            continue
        for option in definition.type_options:
            if isinstance(option, RelationToCitation) and not option.protect:
                found[name] = option
    return found


def is_derived_from(annotation: Any) -> bool:
    """Whether a field's annotation is of `DerivedFrom[...]` (alone, in a list, or with `None`): not of another
    citation that does not protect, which a project may have of its own and people may write"""
    import types
    import typing

    from pangloss_models.citations import cites_origin

    from pangloss_derived.declare import DerivedFrom

    origin = cites_origin(annotation)
    if origin is not None:
        return issubclass(origin, DerivedFrom)
    if typing.get_origin(annotation) in (list, tuple, typing.Union, types.UnionType):
        return any(is_derived_from(a) for a in typing.get_args(annotation))
    return False


def source_field(model: type) -> tuple[str, RelationToCitation]:
    """The one `DerivedFrom` field of a derived document class (after `check_classes`)"""
    ((name, option),) = source_fields(model).items()
    return name, option


def check_classes() -> None:
    """A derived document class is a document class with the trait and one list of `DerivedFrom`; a class with one
    and not the other is a mistake. And it is never reviewed: its status is the worker's to set"""
    for model in ModelRegistry._models:
        if not (isinstance(model, type) and issubclass(model, Document)):
            continue
        if getattr(model, "__metatype__", None) != "Document":
            continue
        sources = source_fields(model)
        if not is_derived_document(model):
            if sources:
                raise PanglossDerivedError(
                    f"{model.__name__}.{next(iter(sources))} is a DerivedFrom, which only the worker writes: so "
                    f"{model.__name__} must be a derived document class (class {model.__name__}(Document, "
                    "DerivedDocument)). For a document people write, cite with Cites[...]"
                )
            continue
        if model._meta.abstract and not sources:
            # (an abstract parent may leave the field to its subclasses)
            continue
        if len(sources) != 1:
            found = ", ".join(sources) or "none"
            raise PanglossDerivedError(
                f"{model.__name__}: a derived document class has one field of DerivedFrom, which the worker fills "
                f"with the documents each rests on (sources: list[DerivedFrom[Factoid]]); this has {found}"
            )
        name = next(iter(sources))
        definition: Any = model._meta.fields[name]
        if definition.wrapper is not list or len(definition.type_options) != 1:
            raise PanglossDerivedError(
                f"{model.__name__}.{name}: the DerivedFrom field of a derived document class is a list of them, and "
                f"of nothing else (list[DerivedFrom[...]]): a derivation rests on one document or on several"
            )
        if not model._meta.create_directly:
            raise PanglossDerivedError(
                f"{model.__name__}: a derived document is a document of its own, which the worker makes: not "
                "create_directly=False (nobody else can make one anyway)"
            )
        settings = settings_of(model)
        targets: Any = settings.converts_to or ()
        for target in targets:
            if not (isinstance(target, type) and issubclass(target, Document)):
                raise PanglossDerivedError(
                    f"{model.__name__}: converts_to names document classes, not {target!r}"
                )
            if is_derived_document(target):
                raise PanglossDerivedError(
                    f"{model.__name__}: converts_to names classes that people write: {target.__name__} is a derived "
                    "document class too"
                )
        never_reviewed(model)


def never_reviewed(model: Any) -> None:
    """A derived document is not checked by a reviewer before it is published (its status follows what it rests on):
    a `ReviewMeta(reviewable=True)` it has from a parent (`AbstractFactoid`) is turned off for it. `pangloss-review`
    is not imported: the slot is its own, and may not be there"""
    meta = getattr(model, "_review_meta", None)
    if meta is None or not getattr(meta, "reviewable", False):
        return
    from pangloss_models.meta_slots import OWN, declared_slots

    if "_review_meta" in declared_slots(model):
        raise PanglossDerivedError(
            f"{model.__name__}: a derived document class is not reviewable (its documents are published when what "
            "they rest on is): take reviewable=True from its _review_meta"
        )
    model._review_meta = dataclasses.replace(meta, reviewable=False)
    setattr(model, OWN, declared_slots(model) | {"_review_meta"})


# ---------------------------------------------------------------------------
# Who may write one
# ---------------------------------------------------------------------------


def not_written_by_people(model: type) -> bool:
    """(`hooks.not_written_by_people`) no `POST` and no "New" for a derived document class"""
    return is_derived_document(model)


async def refuse_other_writers(tx: Any, op: str, model: type, id: UUID) -> None:
    """(`hooks.in_write`) a create, update, delete or undelete of a derived document by anyone but the worker is
    refused, in its transaction: nothing is written. (A restore of a version, by `pangloss-history`, is an update.)"""
    if not is_derived_document(model) or _writing.get() is not None:
        return
    done = {
        "create": "made",
        "update": "changed",
        "delete": "deleted",
        "undelete": "undeleted",
    }.get(op, "written")
    raise PanglossDerivedDocumentError(
        f"A {model.__name__} is derived: it is not {done} by hand, but by the rule that derives it from other "
        "documents (change those, and it follows). To have a document of your own that says what it says, convert it"
    )
