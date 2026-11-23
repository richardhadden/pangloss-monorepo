"""What leaves a document for the worker that suggests (`suggesting.py`; step 10.5d of
implementation_docs/similarity-build-plan.md, the least of 10.5e): a mark of the kind `reconcile`
(`pangloss_cypher.pending`), in the write's own transaction, set by what one write says (`suggest=true|false`, an
instruction of the write: `hooks.declare_write_instruction`) or, when it says nothing, by `RECONCILE_SUGGEST_ON_SAVE`.

Only a class of head **that people write and that can hold a stand-in** is marked (`suggestible`, worked out once
from the models after `initialise()`): one that has an `Update`, is not abstract, that `hooks.written_by_people` says
people write (not a derived document), and some relation field of which, at any depth (through nested documents,
reified relations, conjunctions and semantic spaces; never into an entity or a citation), takes a document of
`hooks.stand_ins` that names the class it stands for (`StandIn.named_type`: the only stand-ins that are unknowns,
`pangloss_vectors.unknowns_of`). Asked only by a create and an update of a head (`hooks.instructed_work`):

| The write says | Answer |
|---|---|
| `suggest=true` | marked |
| `suggest=false` | a standing mark taken off (row 7) |
| nothing, `RECONCILE_SUGGEST_ON_SAVE` True | marked |
| nothing, the setting False | nothing: a mark a trigger left stays |

Nothing of the database is imported here: what is kept in the worker's own update is written by `suggesting`, through
`hooks.in_write`, only while the worker says so (`keeping`)."""

import contextlib
import contextvars
from collections.abc import Generator, Mapping
from typing import Any

from pangloss_models import ModelRegistry, hooks

from pangloss_reconcile import settings

# The kind of pending work of the worker that suggests
KIND = "reconcile"

# The instruction of a write that says whether it leaves its document for the worker
NAME = "suggest"
INSTRUCTION = hooks.WriteInstruction(
    NAME,
    ("true", "false"),
    "Whether the worker of pangloss-reconcile suggests who the stand-ins of this document are (true), or not, "
    "taking off what was waiting (false). Not said: as RECONCILE_SUGGEST_ON_SAVE says",
)

# (the names of the classes of head that can be marked, worked out after `initialise()`)
_suggestible: frozenset[str] = frozenset()


def _installed() -> bool:
    from pangloss_core import settings as core_settings

    found = core_settings.__dict__.get("SETTINGS")
    return settings.APP in list(getattr(found, "INSTALLED_APPS", None) or [])


def stand_in_documents() -> frozenset[str]:
    """The names of the documents of the stand-ins that name the class they stand for (`StandIn.named_type`)"""
    return frozenset(
        stand_in.document
        for stand_in in hooks.stand_ins
        if stand_in.named_type is not None
    )


def holds_stand_ins(model: Any, documents: frozenset[str] | None = None) -> bool:
    """Whether some relation field of the class, at any depth, takes one of these documents (the stand-ins': by
    default `stand_in_documents()`), or a class below one: through nested documents, reified relations, conjunctions
    and semantic spaces, never into an entity or a citation"""
    from pangloss_models.field_definitions import (
        RelationFieldDefinition,
        RelationToCitation,
        RelationToDocument,
        RelationToEntity,
        RelationToTypeVar,
    )

    names = stand_in_documents() if documents is None else documents
    if not names:
        return False
    seen: set[Any] = set()

    def is_stand_in(cls: Any) -> bool:
        return any(getattr(base, "__name__", None) in names for base in cls.__mro__)

    def walk(cls: Any) -> bool:
        if cls in seen:
            return False
        seen.add(cls)
        fields = getattr(getattr(cls, "_meta", None), "fields", None) or {}
        return any(
            reaches(option)
            for definition in list(fields.values())
            if isinstance(definition, RelationFieldDefinition)
            for option in definition.type_options
        )

    def reaches(option: Any) -> bool:
        if isinstance(
            option, (RelationToCitation, RelationToEntity, RelationToTypeVar)
        ):
            return False
        target = option.annotated_type
        if isinstance(option, RelationToDocument):
            return isinstance(target, type) and (is_stand_in(target) or walk(target))
        if isinstance(target, type) and walk(target):
            return True
        return any(
            reaches(inner)
            for parameter in (
                getattr(option, "parameter_type_options", None) or {}
            ).values()
            for inner in parameter.type_options
        )

    return walk(model)


def people_write(model: Any) -> bool:
    """Whether people write heads of the class: it has an `Update`, is not abstract, and no installed app says that it
    alone writes them (`hooks.written_by_people`: a derived document is not)"""
    return (
        isinstance(model, type)
        and hasattr(model, "Update")
        and not getattr(getattr(model, "_meta", None), "abstract", False)
        and hooks.written_by_people(model)
    )


def work_out() -> None:
    """(`ModelRegistry.after_finalise`) the classes of head that can be marked, from the models as they are now: none
    unless the app is installed"""
    global _suggestible
    from pangloss_models import Document, Entity

    if not _installed():
        _suggestible = frozenset()
        return
    documents = stand_in_documents()
    _suggestible = frozenset(
        name
        for name, model in list(ModelRegistry._model_dict.items())
        if name.isidentifier()
        and isinstance(model, type)
        and issubclass(model, (Document, Entity))
        and people_write(model)
        and holds_stand_ins(model, documents)
    )


def suggestible(model: Any) -> bool:
    """Whether heads of the class can be left for the worker (as worked out at `initialise()`)"""
    return getattr(model, "__name__", None) in _suggestible


def suggestible_classes() -> frozenset[str]:
    return _suggestible


def instructed(model: type, instructions: Mapping[str, str]) -> Mapping[str, bool]:
    """(`hooks.instructed_work`) the answer for a create or an update of a head (the table above). Reads nothing: a
    setting and what was worked out at `initialise()`"""
    if model.__name__ not in _suggestible:
        return {}
    said = instructions.get(NAME)
    if said == "true":
        return {KIND: True}
    if said == "false":
        return {KIND: False}
    return {KIND: True} if settings.suggest_on_save() else {}


# What the worker keeps in its own update's transaction (`suggesting.write_kept`): the head it is writing, and the
# rows. Set only around that one save
keeping: contextvars.ContextVar[Any] = contextvars.ContextVar(
    "pangloss_reconcile_keeping", default=None
)


@contextlib.contextmanager
def kept_in_write(kept: Any) -> Generator[None]:
    token = keeping.set(kept)
    try:
        yield
    finally:
        keeping.reset(token)


async def in_write(tx: Any, op: str, model: type, id: Any) -> None:
    """(`hooks.in_write`) nothing, unless the worker is writing (`keeping`): then what it keeps, in the transaction of
    its update of that head (`suggesting.write_kept`)"""
    kept = keeping.get()
    if kept is None:
        return
    from pangloss_reconcile.suggesting import write_kept

    await write_kept(tx, op, id, kept)


def woken(event: hooks.WriteEvent) -> None:
    """(`hooks.after_write`) a write of a class that can be marked wakes the worker of this process, if it runs"""
    if event.model.__name__ in _suggestible:
        from pangloss_reconcile.suggesting import worker

        worker.wake()


def marked(model: type) -> None:
    """(`hooks.work_marked`) as `woken`, for what marks without writing"""
    if model.__name__ in _suggestible:
        from pangloss_reconcile.suggesting import worker

        worker.wake()


def install() -> None:
    """(`pangloss_reconcile._install`)"""
    hooks.declare_write_instruction(INSTRUCTION)
    if instructed not in hooks.instructed_work:
        hooks.instructed_work.append(instructed)
    if in_write not in hooks.in_write:
        hooks.in_write.append(in_write)
    if woken not in hooks.after_write:
        hooks.after_write.append(woken)
    if marked not in hooks.work_marked:
        hooks.work_marked.append(marked)
    if work_out not in ModelRegistry.after_finalise:
        ModelRegistry.after_finalise.append(work_out)
