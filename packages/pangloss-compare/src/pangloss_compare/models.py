"""The models of comparison (implementation_docs/compare.md, "A person's judgement"; the plan's step 6.5).

`EventJudgement` is what a person says of two statements: one event told twice (`agree`, `disagree`), two events
(`two_events`), or of a prescription and what came of it (`carried_out`, `carried_out_otherwise`,
`not_carried_out`, `breach`, `complied`, `permission_used`, `done_not_carried_out`: each the relation of the maths of
that name). A verdict is not checked against the kind of the pair (`complied` may be said of an order): the
interface offers what fits. It is abstract and names no statement class: the package does not know the project's.
The project declares the two citing fields, with these names, the prescription first where there is one:

    class StatementJudgement(EventJudgement):
        statement: Cites[Statement]
        other: Cites[Statement]

(A base with a type parameter, `EventJudgement[T]`, cannot be initialised as a top-level document: the plan's
"Phase 0 as found", 0.5.) Each class below `EventJudgement` that is not abstract is checked at `initialise()`
(`check_judgement_classes`): `statement` and `other` are each a single `Cites[...]` that protects what it cites, of
documents. A judgement is written by the ordinary `POST /api/NAME` of the project's class; the comparison of a
statement reads them (`judgements.py`), and the newest of a pair overrides what is worked out (`compare.py`).

**A judgement is never changed** (`refuse_any_update`, a `@before_update`, run by every write of the models: the
API's `PUT`, a script's `Update(...).save()`, pangloss-history's restore): a person who thinks otherwise later makes
a new judgement, which, being newer, decides, and the old one stays as the record of what was said. Deleting one is
as for any document.

**What a judgement says is checked when it is made** (`check_what_is_judged`, a `@before_create`): it is of two
statements, not of one cited twice; and each of its `fields` is a field of the class of one of the two (as stored),
stored by the name comparison gives it (`resolved`: Python's, a narrowed field as the field it narrows). `fields` is
given as a payload's keys are, camelCase or Python's names (`placeOfBirth`, `place_of_birth`); the route gives them
back in camelCase. No class holds a judgement as a part of it (`check_judgements_not_held`)."""

from typing import Any, Literal

from pangloss_models import (
    Document,
    ModelRegistry,
    PanglossModelError,
    PanglossWriteRefused,
    before_create,
    before_update,
)
from pydantic.alias_generators import to_camel, to_snake

from pangloss_compare.field_names import FieldName

# (D7, widened: what a person may say of a pair; each named as the relation of `maths.RELATIONS` it says, but
# `two_events`, the relation `two`. Not checked against the kind of the pair: the interface offers what fits)
VERDICTS = (
    "agree",
    "disagree",
    "two_events",
    "carried_out",
    "carried_out_otherwise",
    "not_carried_out",
    "breach",
    "complied",
    "permission_used",
    "done_not_carried_out",
)

# The two citing fields a project's class declares, in this order (the prescription first where there is one)
CITING = ("statement", "other")

BASE = "EventJudgement"


class EventJudgement(Document):
    """What a person says of two statements (a pair the comparison found). The project's class below it cites the
    two (`statement` and `other`: the module's docstring)"""

    _meta = Document.Meta(abstract=True)

    verdict: Literal[
        "agree",
        "disagree",
        "two_events",
        "carried_out",
        "carried_out_otherwise",
        "not_carried_out",
        "breach",
        "complied",
        "permission_used",
        "done_not_carried_out",
    ]
    fields: list[FieldName] = []
    """The fields the two disagree on, or of what was carried out otherwise the targets missed: stored as the names
    comparison gives them (Python's, a narrowed field by the name of the field it narrows); in a payload, camelCase,
    Python's, or a narrowed field's own name too (resolved against the two statements' classes when it is made)"""
    note: str = ""

    @before_create
    async def check_what_is_judged(self) -> None:
        await _check_judged(self)

    @before_update
    async def refuse_any_update(self, previous: Any) -> None:
        raise PanglossWriteRefused(
            f"A judgement is not changed once made (this is a {type(self).__name__}): make a new judgement of the "
            "pair, which, being the newest, decides; this one stays as the record of what was said. It can be "
            "deleted"
        )


def python_name(name: str) -> str:
    """Where no class can be read to resolve it against (`resolved`): a field's name in camelCase as Python's, by
    pydantic's conversion; one without a capital as it is"""
    return to_snake(name) if any(c.isupper() for c in name) else name


def resolved(name: str, classes: list[type]) -> str | None:
    """A name a judgement gives (camelCase as a payload's keys are, `to_camel` of a field's; or Python's) as the field
    of one of the statements' classes it names, by the name comparison gives that field: an identifying field or
    one narrowing another by the name it counts as (`reading.Known.shape`: `picture_made` as `made`), any other by
    its own. The first class that has it decides. None: a field of none of them"""
    from pangloss_compare.reading import Known

    known = Known()
    for model in classes:
        for field in getattr(model, "model_fields", {}):
            if name in (field, to_camel(field)):
                return known.shape(model.__name__).fields.get(field, field)
    return None


# The class of each document of these ids, as stored
CLASSES_QUERY = """
    UNWIND $ids AS nid
    MATCH (n:PGIndexableNode {id: nid})
    WHERE n:Document
    RETURN n.id AS id, n.type AS type
"""


async def _stored_classes(ids: list[str]) -> dict[str, type]:
    from pangloss_core import backend

    database = backend.current().database()

    @database.read_transaction
    async def read(tx: Any) -> dict[str, str]:
        result = await tx.run(CLASSES_QUERY, ids=ids)
        return {str(r["id"]): str(r["type"]) async for r in result}

    found = await read()
    models = ModelRegistry._model_dict
    return {
        id: models[name]
        for id, name in found.items()
        if isinstance(models.get(name), type)
    }


async def _check_judged(judgement: Any) -> None:
    """(`EventJudgement.check_what_is_judged`) A judgement cites two statements, not one twice; each of its `fields`
    is a field of the class of one of the two, as they are stored, and is written as `resolved` names it (the
    write's own `fields` replaced: what is stored is what the check gives). What a citation does not name (a cited
    basis, an app's), or names that is not there, is left to the citation's own check, which refuses what cannot be
    cited; with no class to read, the names are only made Python's (`python_name`)"""
    cited = [
        getattr(getattr(judgement, field, None), "target_id", None) for field in CITING
    ]
    if cited[0] is not None and cited[0] == cited[1]:
        raise PanglossWriteRefused(
            f"A judgement is of two statements: `statement` and `other` both cite {cited[0]}",
            field="other",
        )
    fields = list(getattr(judgement, "fields", None) or [])
    ids = sorted({str(id) for id in cited if id is not None})
    if not fields or not ids:
        return
    classes = await _stored_classes(ids)
    if not classes:
        judgement.fields = [FieldName(python_name(name)) for name in fields]
        return
    ordered = [classes[id] for id in (str(c) for c in cited if c is not None) if id in classes]  # fmt: skip
    found = {name: resolved(name, ordered) for name in fields}
    unknown = [name for name, field in found.items() if field is None]
    if unknown:
        names = sorted({model.__name__ for model in classes.values()})
        raise PanglossWriteRefused(
            f"{', '.join(repr(name) for name in unknown)} "
            f"{'is not a field' if len(unknown) == 1 else 'are not fields'} of {' or '.join(names)}: a judgement's "
            "fields are those of the two statements it cites",
            field="fields",
        )
    judgement.fields = [FieldName(name) for name in dict.fromkeys(str(found[name]) for name in fields)]  # fmt: skip


def _why_not(definition: Any) -> str | None:
    """Why a field is not a single citation that protects what it cites, of documents; None if it is"""
    from pangloss_models.field_definitions import (
        RelationFieldDefinition,
        RelationToCitation,
    )

    if not isinstance(definition, RelationFieldDefinition):
        return "is not a citation"
    if definition.wrapper is not None:
        return "is a list: a judgement is of one pair"
    if definition.optional:
        return "may be None: a judgement is of a pair, both there"
    from pangloss_models.citations import BASIS

    # (beside a citation, a cited basis: an installed app's way of citing what cannot itself be cited, which a
    # statement can; never the one option)
    options = [
        o
        for o in definition.type_options
        if getattr(o.annotated_type, "__name__", None) != BASIS
    ]
    if not options or not all(isinstance(o, RelationToCitation) for o in options):
        return "is not a citation"
    if not all(o.protect for o in options if isinstance(o, RelationToCitation)):
        return (
            "is a citation that does not protect what it cites: a judgement has to know when a statement it judges "
            "has changed"
        )
    return None


def check_judgement_classes() -> None:
    """(`ModelRegistry.after_finalise`) Every class below `EventJudgement` that is not abstract has the fields
    `statement` and `other`, each a single `Cites[...]` (one that protects what it cites). A `PanglossModelError`
    naming the class and what to write"""
    models = ModelRegistry._model_dict
    base = models.get(BASE)
    if not isinstance(base, type):
        return
    for name, model in sorted(models.items()):
        if (
            not name.isidentifier()
            or not isinstance(model, type)
            or model is base
            or not issubclass(model, base)
            or getattr(model._meta, "abstract", False)
        ):
            continue
        fields = model._meta.fields
        for field in CITING:
            definition = fields.get(field) if fields is not None else None
            why = (
                "is missing" if definition is None else _why_not(definition)
            )  # fmt: skip
            if why is None:
                continue
            raise PanglossModelError(
                f"{name}: an EventJudgement cites the two statements it judges, and its field {field!r} {why}. "
                f"Declare both on {name}, with your class of statements: "
                "`statement: Cites[Statement]` and `other: Cites[Statement]` (the prescription first, where one of "
                "the two is)"
            )


def _held_documents(options: Any) -> set[type]:
    """The classes of documents relations of these options hold as parts of what holds them (not what they cite),
    through every wrapper's parameters (a space's `contents`, a reified relation's `target`), each with the concrete
    classes below it"""
    from pangloss_models.field_definitions import (
        RelationToCitation,
        RelationToDocument,
    )
    from pangloss_models.utils import get_concrete_types

    found: set[type] = set()
    for option in options:
        if isinstance(option, RelationToCitation):
            continue
        if isinstance(option, RelationToDocument) and isinstance(
            option.annotated_type, type
        ):
            found.add(option.annotated_type)
            found.update(
                t
                for t in get_concrete_types(option.annotated_type)
                if isinstance(t, type)
            )
        for parameter in (
            getattr(option, "parameter_type_options", None) or {}
        ).values():
            found |= _held_documents(parameter.type_options)
    return found


def check_judgements_not_held() -> None:
    """(`ModelRegistry.after_finalise`) No class holds a judgement as a part of it: a judgement is never updated
    (`EventJudgement.refuse_any_update`), and a `@before_update` runs on every node of a head written again, so a
    document holding one could never be saved again. A `PanglossModelError` naming the class and the field"""
    models = ModelRegistry._model_dict
    base = models.get(BASE)
    if not isinstance(base, type):
        return
    for name, model in sorted(ModelRegistry.all_models().items()):
        fields = getattr(getattr(model, "_meta", None), "fields", None)
        if not fields:
            continue
        for field, definition in fields.relation_fields.items():
            held = sorted(
                t.__name__
                for t in _held_documents(definition.type_options)
                if issubclass(t, base)
            )
            if held:
                raise PanglossModelError(
                    f"{name}.{field} holds {', '.join(held)}, a judgement, as a part of it: a judgement is a document "
                    "of its own, never changed once made, so what held it could never be saved again. Cite it "
                    f"instead (`{field}: Cites[{held[0]}]`), or make it on its own"
                )


def _registered_once(hooks: list, check: Any) -> None:
    # (once, though the tests run this module again for a fresh registry)
    hooks[:] = [
        hook
        for hook in hooks
        if getattr(hook, "__qualname__", None) != check.__qualname__
        or getattr(hook, "__module__", None) != __name__
    ] + [check]


_registered_once(ModelRegistry.after_finalise, check_judgement_classes)
_registered_once(ModelRegistry.after_finalise, check_judgements_not_held)
